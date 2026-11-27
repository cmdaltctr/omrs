"""Inputs of the Exp 35 pod sessions: what mac_watch35.py sends, and what it refuses.

The data root and the files pod_setup35.sh checks come from plan.json through
datasets35.py. A file that looks like a secret, or resolves outside the data root or
into ~/.config or ~/.ssh, never goes into the inputs tarball. The checked local side of
a session (``Plan``, ``prepare``) and the inputs folder (``build_inputs``) live here. A
``--resume`` session reuses the inputs folder of its earlier session.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import runpod_ssh35
import watch_modes35
import watch_zai35

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
REPO = EXP.parent.parent
PLAN = EXP / "plan.json"
_SECRET_PARTS = (".env", "secrets", ".config", ".ssh")
POD_ID_FILE = "pod-id.txt"  # written when a session starts; --resume needs the same pod id
INPUTS_TGZ, EXAMPLES, STAGES = (
    "exp35-inputs.tgz",
    "classify-examples.json",
    "test_session_stages.txt",
)


def sha256(path: Path) -> str:
    """Return the SHA-256 of a file as lower-case hex."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def inputs() -> tuple[Path, list[str]]:
    """Return the data root and the files pod_setup35.sh checks (Legal stays out, D1)."""
    sys.path[:0] = [p for p in (str(EXP), str(REPO)) if p not in sys.path]
    import datasets35 as ds

    root, plan = ds.data_root(), json.loads(PLAN.read_text(encoding="utf-8"))
    rels = [r for n in ("financebench", "freshstack", "bioasq") for r in ds.input_hashes(n, plan)]
    manifest = next(r for r in rels if r.endswith("PDFS_MANIFEST.json"))
    names = json.loads((root / manifest).read_text(encoding="utf-8"))["files"]
    rels += ds.pdf_hashes(root, [Path(f"{name}.pdf") for name in names])
    corpus = ds._FS_CORPUS
    rels += [f"{corpus}/{n}" for n in ["download.json", *ds.freshstack_pin(plan)["corpus_files"]]]
    return root, sorted(set(rels))


def unsafe(rel: str, root: Path) -> str | None:
    """Return why *rel* must not go into the tarball, or ``None`` when it may."""
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        return "is not a plain relative path"
    if any(p.startswith(_SECRET_PARTS) for p in path.parts) or path.suffix in (".key", ".pem"):
        return "looks like a secret"
    real, home = (root / path).resolve(), Path.home().resolve()
    private = real.is_relative_to(home / ".config") or real.is_relative_to(home / ".ssh")
    if private or not real.is_relative_to(root):
        return f"resolves to {real}: outside the data root, or under ~/.config or ~/.ssh"
    target = real.relative_to(root)  # a link to root/.env passes the name checks above
    if any(p.startswith(_SECRET_PARTS) for p in target.parts) or target.suffix in (".key", ".pem"):
        return f"resolves to {real}, which looks like a secret"
    return None if real.is_file() else "is missing"


@dataclass
class Plan:
    """The checked local side of one session."""

    commit: str
    key: Path
    examples: Path
    stages: str = STAGES
    extra: Path | None = None  # --extra-input: one more file for the pod's inputs folder
    keep: bool = False  # --keep-pod-on-fail
    resume: bool = False  # --resume: reuse the folder and the stage tarballs of an earlier try
    resume_from: str = ""  # --resume-from-commit: the old commit whose finished stages stay valid
    attach: bool = False  # --attach: join the chain that still runs; reuse the folder
    seed_from: str = (
        ""  # --seed-from: an earlier results folder whose stage tarballs seed a new pod
    )
    repo_url: str = ""
    root: Path = Path()
    folder: Path = Path()
    rels: list[str] = field(default_factory=list)

    @property
    def reuse(self) -> bool:
        """Whether the session reuses the results folder of an earlier try."""
        return self.resume or self.attach

    def sent(self) -> list[str]:
        """Name the inputs that go to the pod and have their SHA-256 checked there."""
        return [INPUTS_TGZ, EXAMPLES, *([self.extra.name] if self.extra else [])]


def resume_folder(root: Path, exp: str, stem: str) -> Path | None:
    """Return the newest results folder ``<stem>-<date>`` of an earlier session, or ``None``."""
    found = (root / "experiments" / exp).glob(f"{stem}-*")
    return max(
        (p for p in found if re.fullmatch(rf"{stem}-\d{{4}}-\d\d-\d\d", p.name)), default=None
    )


def pod_mismatch(folder: Path, pod_id: str) -> str:
    """Return why *folder* is not the folder of pod *pod_id*, or ``""`` when it is."""
    record = folder / POD_ID_FILE
    seen = record.read_text(encoding="utf-8").strip() if record.is_file() else ""
    if seen == pod_id:
        return ""
    return (
        f"{folder} records pod {seen}, not {pod_id}" if seen else f"{folder} has no {POD_ID_FILE}"
    )


def prepare(args: argparse.Namespace) -> tuple[list[str], Plan]:
    """Check every local input; return the problems and the plan. Writes nothing."""
    plan = Plan(args.commit, args.ssh_key.expanduser(), args.examples.expanduser(), args.stages)
    plan.extra = args.extra_input.expanduser() if args.extra_input else None
    plan.keep, plan.resume, plan.resume_from = (
        args.keep_pod_on_fail,
        args.resume,
        args.resume_from_commit,
    )
    plan.attach, plan.seed_from = args.attach, args.seed_from
    problems = watch_modes35.problems(plan.attach, plan.resume, plan.seed_from)
    if plan.resume_from and not (plan.resume or plan.seed_from):
        problems.append("--resume-from-commit needs --resume (or --seed-from)")
    if plan.resume_from and not re.fullmatch(r"[0-9a-f]{40}", plan.resume_from):
        problems.append(
            "--resume-from-commit must be the full 40-character commit SHA (lower-case)"
        )
    if not (args.stages.endswith("_stages.txt") and (HERE / Path(args.stages).name).is_file()):
        problems.append(f"--stages {args.stages} is not a *_stages.txt file in {HERE}")
    if plan.extra and not plan.extra.is_file():
        problems.append(f"--extra-input {plan.extra} is not a file")
    elif plan.extra and plan.extra.name.lower() in (INPUTS_TGZ, f"{INPUTS_TGZ}.sha256", EXAMPLES):
        problems.append(f"--extra-input {plan.extra.name} has the name of a generated input")
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):  # it goes unquoted into pod commands
        problems.append("--commit must be the full 40-character commit SHA")
    problems += runpod_ssh35.arg_problems(args.ssh_host, args.ssh_port)
    if not plan.key.is_file():
        problems.append(f"SSH key {plan.key} not found")
    try:
        json.loads(plan.examples.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        problems.append(f"--examples {plan.examples} is not a JSON file ({type(error).__name__})")
    git = ["git", "-C", str(REPO), "remote", "get-url", "origin"]
    origin = subprocess.run(git, capture_output=True, text=True, check=False)  # noqa: S603
    plan.repo_url = args.repo_url or (origin.stdout.strip() if origin.returncode == 0 else "")
    if not plan.repo_url:
        problems.append("no --repo-url, and this checkout has no origin remote")
    try:
        plan.root, plan.rels = inputs()
        stem = plan.stages.removesuffix("_stages.txt").replace("_", "-")
        plan.folder = plan.root / "experiments" / EXP.name / f"{stem}-{datetime.now(UTC):%Y-%m-%d}"
        if plan.reuse:
            plan.folder = resume_folder(plan.root, EXP.name, stem) or plan.folder
    except Exception as error:  # noqa: BLE001 - any failure here is a refusal with its reason
        return [*problems, f"cannot list the inputs: {type(error).__name__}: {error}"], plan
    missing = [n for n in plan.sent() if not (plan.folder / "inputs" / n).is_file()]
    flag = "--attach" if plan.attach else "--resume"
    if plan.reuse and missing:
        problems.append(
            f"{flag}: no earlier {stem} folder with the inputs {missing} ({plan.folder})"
        )
    elif plan.reuse and (why := pod_mismatch(plan.folder, args.pod_id)):
        problems.append(f"{flag}: {why}")
    elif plan.folder.exists() and not plan.reuse:
        problems.append(f"results folder {plan.folder} already exists; it is never overwritten")
    problems += [f"input {rel} {why}" for rel in plan.rels if (why := unsafe(rel, plan.root))]
    problems += watch_zai35.problems()
    return problems, plan


def build_inputs(plan: Plan, say: Callable[[str], None]) -> dict[str, str]:
    """Write the inputs folder (tarball, .sha256, examples, extra); return SHA-256 by name.

    A resumed or attached session writes nothing: it returns the hashes of the earlier inputs.
    """
    folder = plan.folder / "inputs"
    if plan.reuse:
        return {name: sha256(folder / name) for name in plan.sent()}
    folder.mkdir()
    tgz = folder / INPUTS_TGZ
    with tarfile.open(tgz, "w:gz", compresslevel=6) as tar:
        for rel in plan.rels:
            tar.add((plan.root / rel).resolve(), arcname=rel, recursive=False)
    digest = sha256(tgz)
    (folder / f"{INPUTS_TGZ}.sha256").write_text(f"{digest}  {INPUTS_TGZ}\n", encoding="utf-8")
    shutil.copyfile(plan.examples, folder / EXAMPLES)
    if plan.extra:
        shutil.copyfile(plan.extra, folder / plan.extra.name)
    say(f"  {tgz}: {len(plan.rels)} files, {tgz.stat().st_size / 1e6:.1f} MB, SHA-256 {digest}")
    return {n: digest if n == INPUTS_TGZ else sha256(folder / n) for n in plan.sent()}
