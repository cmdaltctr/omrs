"""Shared paths, hashing, atomic writes and plan guards for Experiment 43."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
OUTPUT = EXP_DIR / "output"
RENDERS = OUTPUT / ".renders"
TEXTS = OUTPUT / ".rescue_text"
EXPERIMENTS = EXP_DIR.parent
EXP33 = EXPERIMENTS / "33-ocr-routing-natural-positive-2026-09-17"
EXP38 = EXPERIMENTS / "38-rescue-quality-signal-2026-09-30"
JUNK_DOCS = ("rf06", "rf07")
MIN_FREE_MEMORY = 15


def sha256(path: Path) -> str:
    """Hash a file in 1 MiB blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def text_sha256(text: str) -> str:
    """Hash UTF-8 text (the Experiment 38 page-text hash)."""
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


def plan() -> dict:
    """Read plan.json and require every operator decision to be approved and dated."""
    current = read_json(EXP_DIR / "plan.json")
    if any(
        not r["status"].startswith("APPROVED") or not r.get("date")
        for r in current["decision_register"]
    ):
        raise RuntimeError("every operator decision must be approved before running")
    return current


def hosted_approved(current: dict) -> bool:
    """True when a dated approval names TypeSafe and both named-person documents."""
    return any(
        r["status"].startswith("APPROVED")
        and r.get("date")
        and r.get("provider") == "TypeSafe"
        and all(doc in r.get("documents", "") for doc in JUNK_DOCS)
        for r in current["decision_register"]
    )


def load_module(path: Path, name: str) -> ModuleType:
    """Import a source-experiment module by path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_memory_percent() -> int:
    """Return macOS system-wide free memory percentage (memory_pressure)."""
    out = subprocess.run(  # noqa: S603
        ["/usr/bin/memory_pressure", "-Q"], capture_output=True, text=True, check=False
    ).stdout
    match = re.search(r"free percentage:\s*(\d+)%", out)
    return int(match.group(1)) if match else 100


def check_memory() -> None:
    """Stop when free memory falls under the plan limit."""
    free = free_memory_percent()
    if free < MIN_FREE_MEMORY:
        raise SystemExit(f"free memory {free}% is under {MIN_FREE_MEMORY}%: stop")


def git_clean(path: Path) -> bool:
    """True when *path* has no uncommitted change."""
    out = subprocess.run(  # noqa: S603, S607
        ["git", "status", "--porcelain", "--", str(path)],
        capture_output=True,
        text=True,
        check=True,
        cwd=EXP_DIR,
    ).stdout
    return not out.strip()


def log(message: str) -> None:
    """Print one progress line, flushed."""
    print(message, flush=True)
    sys.stdout.flush()
