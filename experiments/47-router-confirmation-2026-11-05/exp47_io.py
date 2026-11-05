"""Shared paths, hashing, atomic writes and run guards for Experiment 47.

Committed files hold hashes, counts, scores and labels only. Page text, page
images, reference transcriptions, logs and lock files go under the private
folder ``output/.private/``. That folder carries its own ``.gitignore`` (``*``),
written before the first private file, so a fresh clone keeps it out of git.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
EXPERIMENTS = EXP_DIR.parent
OUTPUT = EXP_DIR / "output"
#: Gitignored input folder (root ``.gitignore``: ``experiments/**/corpus/``).
CORPUS = EXP_DIR / "corpus"
MANIFEST = EXP_DIR / "corpus_manifest.json"
#: Every private (gitignored) file lives below this folder. protocol.md section 8
#: names each sub-folder for cleanup; a test keeps the two in step.
PRIVATE = OUTPUT / ".private"
PRIVATE_DIRS = {
    "text": PRIVATE / "text",
    "renders": PRIVATE / "renders",
    "references": PRIVATE / "references",
    "logs": PRIVATE / "logs",
    "locks": PRIVATE / "locks",
}
INPUTS = OUTPUT / "inputs.json"
LABELS = OUTPUT / "labels.json"
LABEL_REVIEW = OUTPUT / "label_review.json"
REFERENCE_STATE = OUTPUT / "reference_state.json"
ARMS = ("clef_router", "jev_router")
MIN_FREE_MEMORY = 15

if str(EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTS))

from _lib.run_safety import RunStop  # noqa: E402


def sha256(path: Path) -> str:
    """Hash a file in 1 MiB blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Hash bytes."""
    return hashlib.sha256(data).hexdigest()


def text_sha256(text: str) -> str:
    """Hash UTF-8 text (the page-text hash of Experiments 38 and 43)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    """Read a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: Any) -> None:
    """Write JSON through a .tmp file and a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def private_path(kind: str, *parts: str) -> Path:
    """Return a path in a private sub-folder; make sure the folder is gitignored first."""
    PRIVATE.mkdir(parents=True, exist_ok=True)
    ignore = PRIVATE / ".gitignore"
    if not ignore.is_file():
        ignore.write_text("*\n", encoding="utf-8")
    path = PRIVATE_DIRS[kind].joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_private_bytes(kind: str, data: bytes, *parts: str) -> Path:
    """Write bytes to a private file through a .tmp file and a rename."""
    path = private_path(kind, *parts)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


def plan(path: Path | None = None, *, require_approved: bool = True) -> dict:
    """Read plan.json; by default require every decision to be approved and dated.

    The plan holds DRAFT entries until the operator approves them, so no run
    step can start before approval. The optional hosted reference arm has its
    own entry, which only :func:`hosted_approved` reads.
    """
    current = read_json(path or EXP_DIR / "plan.json")
    if require_approved:
        pending = [
            r["item"][:60]
            for r in current["decision_register"]
            if r.get("scope") != "hosted_reference_arm"
            and (not str(r.get("status", "")).startswith("APPROVED") or not r.get("date"))
        ]
        if pending:
            raise SystemExit(f"plan.json has decisions without a dated approval: {pending}")
    return current


def hosted_approved(current: dict, provider: str) -> bool:
    """True when a dated approval names *provider* for the hosted reference arm."""
    return any(
        str(r.get("status", "")).startswith("APPROVED")
        and r.get("date")
        and r.get("provider") == provider
        and r.get("scope") == "hosted_reference_arm"
        for r in current["decision_register"]
    )


def git_clean(path: Path) -> bool:
    """True when *path* is tracked and has no uncommitted change."""
    tracked = subprocess.run(  # noqa: S603
        ["git", "ls-files", "--error-unmatch", str(path)],  # noqa: S607
        capture_output=True,
        cwd=EXP_DIR,
        check=False,
    )
    if tracked.returncode:
        return False
    out = subprocess.run(  # noqa: S603
        ["git", "status", "--porcelain", "--", str(path)],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        cwd=EXP_DIR,
    ).stdout
    return not out.strip()


def load_module(path: Path, name: str) -> ModuleType:
    """Import a module of another experiment by path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_file(current: dict, item: str) -> Path:
    """Return the repository path of frozen entry *item* after checking its SHA-256."""
    entry = next(f for f in current["frozen"] if f["item"] == item)
    path = EXPERIMENTS.parent / entry["path"]
    if sha256(path) != entry["sha256"]:
        raise SystemExit(f"frozen file differs from plan: {entry['path']}")
    return path


def score_files() -> list[Path]:
    """Return the router score checkpoints that exist."""
    return [
        OUTPUT / f"scores_{arm}.json" for arm in ARMS if (OUTPUT / f"scores_{arm}.json").exists()
    ]


def log(message: str) -> None:
    """Print one progress line, flushed."""
    print(message, flush=True)


# ---------------------------------------------------------------- run guards
#
# Nothing below re-implements the router. RecordingJudge passes every call to the
# shipped PageJudge unchanged and only writes down what it returned. The other
# functions refuse a run before any request when a planned condition is not met
# (issue #171, points 4, 7, 8 and 10).

ROUTER_WORDS = Path("web/src/settings/routerWords.ts")
EXP43_PLAN_ITEM = "Experiment 43 plan.json (thresholds)"


class RecordingJudge:
    """Pass each call to the shipped judge; record what it returned.

    On a resume, a saved answer for the same text head is given back without a
    new request, so no page is scored twice. A saved failure (``None``) is
    asked again.
    """

    def __init__(self, inner: Any, replay: list[dict], on_call: Callable[[dict], None]) -> None:
        self._inner = inner
        self._replay = list(replay)
        self._on_call = on_call

    @property
    def status(self) -> str | None:
        """The shipped judge's status (runs its checks once)."""
        return self._inner.status

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def judge(self, text: str, image: bytes | None) -> float | None:
        """Return the shipped judge's P(yes) for one page, and record it."""
        head = text_sha256(text)
        saved = self._replay.pop(0) if self._replay else None
        if saved is not None and saved["head_sha256"] != head:
            raise RunStop("a saved answer belongs to another page text: inputs changed, stop")
        if saved is not None and saved["p_yes"] is not None:
            call = {**saved, "replayed": True}
        else:
            start = time.perf_counter()
            p_yes = self._inner.judge(text, image)
            call = {
                "head_sha256": head,
                "p_yes": p_yes,
                "seconds": round(time.perf_counter() - start, 6),
            }
        call["image_sha256"] = sha256_bytes(image) if image is not None else None
        self._on_call(call)
        return call["p_yes"]

    def unused(self) -> int:
        """Saved answers that no page asked for."""
        return len(self._replay)


@dataclass(frozen=True)
class StopRules:
    """The time, cost and failure stop rules of plan.json, enforced in code (point 7)."""

    max_hours: float
    max_usd: float
    usd_per_page: float
    warmup_pages: int
    max_failed_pages: int

    @classmethod
    def from_plan(cls, current: dict) -> StopRules:
        """Read the rules from plan.json ``stop_rules``."""
        rules = current["stop_rules"]
        return cls(
            rules["max_hours"],
            rules["max_usd"],
            rules["usd_per_hosted_page"],
            rules["warmup_pages"],
            rules["max_failed_pages"],
        )

    def before_start(self, hosted: bool, pages_left: int) -> None:
        """Hosted arm: stop before the first request when the projected cost is over."""
        projected = pages_left * self.usd_per_page
        if hosted and projected > self.max_usd:
            raise RunStop(f"projected cost USD {projected:.2f} is over USD {self.max_usd}: stop")

    def after_call(self, hosted: bool, seconds: list[float], pages_left: int, sent: int) -> None:
        """Stop when the projected time or the cost so far passes its limit."""
        if hosted and sent * self.usd_per_page > self.max_usd:
            raise RunStop(f"cost so far is over USD {self.max_usd}: stop")
        timed = seconds[self.warmup_pages :]
        if timed:
            hours = (sum(timed) / len(timed)) * pages_left / 3600
            if hours > self.max_hours:
                raise RunStop(
                    f"projected {hours:.1f} h for the pages left is over {self.max_hours} h: stop"
                )

    def after_failure(self, failed_pages: int) -> None:
        """Stop when too many pages are left without a score (INCONCLUSIVE)."""
        if failed_pages > self.max_failed_pages:
            raise RunStop(
                f"{failed_pages} pages failed, over {self.max_failed_pages}: stop (INCONCLUSIVE)"
            )


def check_threshold(current: dict, arm: str, clean: Callable[[Path], bool] = git_clean) -> float:
    """Every scoring run: the threshold is the frozen value and plan.json is committed (point 8).

    There is no fit phase in this experiment, so every phase checks.
    """
    frozen = current["frozen_thresholds"][arm]
    source = read_json(frozen_file(current, EXP43_PLAN_ITEM))["thresholds"][frozen["source_key"]]
    if source["input_sha256"] != frozen["input_sha256"]:
        raise RunStop(f"{arm}: the Experiment 43 threshold input changed: stop")
    if round(source["value"], 3) != frozen["value"]:
        raise RunStop(f"{arm}: the frozen threshold does not round from Experiment 43: stop")
    if current["arms"][arm]["threshold"] != frozen["value"]:
        raise RunStop(
            f"{arm}: threshold {current['arms'][arm]['threshold']} is not the "
            f"frozen {frozen['value']}: stop"
        )
    if not clean(EXP_DIR / "plan.json"):
        raise RunStop("commit plan.json before any score: stop")
    return frozen["value"]


def check_template(current: dict, repo_root: Path) -> None:
    """The router recipe in the plan is the shipped template (web) and smoke question."""
    from omrs.core.providers.decision.checks import SMOKE_QUESTION

    router = current["router"]
    words = (repo_root / ROUTER_WORDS).read_text(encoding="utf-8")
    wanted = [
        f'question: "{router["question"]}"',
        f"threshold: {current['arms']['clef_router']['threshold']},",
        f"images: {str(router['images']).lower()},",
        f"max_chars: {router['max_chars']},",
    ]
    missing = [w for w in wanted if w not in words]
    if missing or SMOKE_QUESTION != router["question"]:
        raise RunStop(f"the plan recipe differs from the shipped template: {missing}")


def check_identity(current: dict, arm: str) -> dict:
    """What a runtime check record must match: plan, inputs, labels, model and runner."""
    spec = current["arms"][arm]
    return {
        "arm": arm,
        "plan_sha256": sha256(EXP_DIR / "plan.json"),
        "inputs_sha256": sha256(INPUTS),
        "labels_sha256": sha256(LABELS),
        "model": spec.get("model_sha256") or spec["model"],
        "runner_sha256": sha256(EXP_DIR / "score_router.py"),
    }


def require_check(arm: str, identity: dict, *, local: bool) -> dict:
    """Refuse scoring without a passing runtime check record for this identity (point 10)."""
    path = OUTPUT / f"runtime_check_{arm}.json"
    if not path.exists():
        raise RunStop(f"no {path.name}: run --check first")
    record = read_json(path)
    if record.get("identity") != identity:
        raise RunStop(f"{path.name} was made for another plan, input, model or runner: run --check")
    needed = ["R4_shipped_checks"] + (["R5_no_projector"] if local else [])
    failed = [k for k in needed if not record.get("checks", {}).get(k, {}).get("pass")]
    if not record.get("passed") or failed:
        raise RunStop(f"{path.name} did not pass {failed or 'every check'}: stop")
    return record
