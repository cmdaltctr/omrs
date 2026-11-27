"""Modes of mac_watch35.py for a Mac that was away: ``--attach`` and ``--seed-from``.

``--attach``: the chain still runs in tmux on the pod. The watcher joins it and skips the
inputs copy, ``session.env`` and the launch. ``--seed-from <results folder>``: the old pod
and its volume are gone. The new pod gets every stage tarball of the earlier folder (each
SHA-256 checked on the Mac first) and the chain resumes from them. The record of the seed
is ``seed-from.txt`` in the new results folder.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shlex
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

_TGZ = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.tgz")  # also what the pod's shell accepts
SEED_RECORD = "seed-from.txt"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add ``--attach`` and ``--seed-from`` to the watcher's parser."""
    parser.add_argument("--attach", action="store_true", help="join the chain that still runs")
    parser.add_argument("--seed-from", default="", help="earlier results folder for a NEW pod")
    parser.add_argument("--no-offsite", action="store_true", help="no R2 copy, no R2 check")


def _sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def seed_tarballs(seed: Path) -> list[Path]:
    """Return the stage tarballs of the earlier results folder, by name."""
    return sorted((seed / "stage-out").glob("*.tgz"))


def problems(attach: bool, resume: bool, seed_from: str) -> list[str]:
    """Name each problem of the mode flags and of the seed folder. Writes nothing."""
    found = []
    if attach and resume:
        found.append("--attach and --resume cannot be used together")
    if seed_from and (attach or resume):
        found.append("--seed-from cannot be used with --resume or --attach")
    if not seed_from:
        return found
    seed = Path(seed_from)
    if not seed.is_absolute():
        return [*found, f"--seed-from {seed_from} must be an absolute path"]
    if not (seed / "stage-out").is_dir():
        return [*found, f"--seed-from {seed} has no stage-out folder"]
    if not (tarballs := seed_tarballs(seed)):
        return [*found, f"--seed-from {seed} holds no stage tarballs"]
    for tgz in tarballs:
        record = tgz.with_name(f"{tgz.name}.sha256")
        want = record.read_text(encoding="utf-8").split()[:1] if record.is_file() else []
        if not _TGZ.fullmatch(tgz.name):
            found.append(f"--seed-from: {tgz.name} is not a plain stage tarball name")
        elif want != [_sha(tgz)]:
            found.append(f"--seed-from: {tgz.name} does not match its SHA-256 file in {seed}")
    return found


def dry_lines(attach: bool, seed_from: str) -> list[str]:
    """Return the dry-run lines of the mode (none for a normal or --resume session)."""
    if attach:
        return [
            "--attach: join the running chain; no inputs copy, no session.env, no launch; "
            "check that the tmux session exists, then watch and pull as usual"
        ]
    if seed_from:
        return [
            f"--seed-from: copy {len(seed_tarballs(Path(seed_from)))} stage tarballs from "
            f"{seed_from} (each SHA-256 checked first) to the pod and the new results folder "
            f"after the inputs copy; write {SEED_RECORD} and RESUME=1 into session.env"
        ]
    return []


def attach_refusal(pod: Any, session: str) -> str:
    """Return why the watcher cannot join the chain, or ``""`` when the tmux session runs."""
    found = pod.ssh(f"tmux has-session -t {session} 2>/dev/null")
    if found is not None and found.returncode == 0:
        return ""
    return (
        f"--attach: no tmux session {session} runs on the pod. The pod and its stage "
        "tarballs are untouched. Use --resume to launch the chain again"
    )


def seed(pod: Any, plan: Any, remote_dir: str, say: Callable[[str], None]) -> bool:
    """Copy the stage tarballs to the pod and the new results folder; write the record."""
    seed_dir, tarballs = Path(plan.seed_from), seed_tarballs(Path(plan.seed_from))
    say(f"step 4b: --seed-from {seed_dir}: {len(tarballs)} stage tarballs to {remote_dir}")
    if not pod.ok(f"mkdir -p {shlex.quote(remote_dir)}"):
        return False
    lines = [f"seed folder: {seed_dir}"]
    new = plan.folder / "stage-out"
    new.mkdir(parents=True, exist_ok=True)
    for tgz in tarballs:
        commit = tgz.with_name(f"{tgz.name}.commit")
        files = [tgz, *([commit] if commit.is_file() else []), tgz.with_name(f"{tgz.name}.sha256")]
        dest = pod.remote(f"{remote_dir}/")
        sources = [str(f) for f in files]
        if not (pod.copy(sources, dest) or pod.copy(sources, dest)):
            return False
        for f in files:  # the .sha256 file last: it is the ready signal
            shutil.copyfile(f, new / f.name)
        word = commit.read_text(encoding="utf-8").strip() if commit.is_file() else "none"
        lines.append(f"{tgz.name} {_sha(tgz)} {word}")
    (plan.folder / SEED_RECORD).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return pod.ok(f"cd {shlex.quote(remote_dir)} && sha256sum -c --quiet *.tgz.sha256")
