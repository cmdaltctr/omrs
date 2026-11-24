"""Inputs of the Exp 35 pod sessions: what mac_watch35.py sends, and what it refuses.

The data root and the files pod_setup35.sh checks come from plan.json through
datasets35.py. A file that looks like a secret, or resolves outside the data root or
into ~/.config or ~/.ssh, never goes into the inputs tarball.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
REPO = EXP.parent.parent
PLAN = EXP / "plan.json"
_SECRET_PARTS = (".env", "secrets", ".config", ".ssh")


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
    return None if real.is_file() else "is missing"
