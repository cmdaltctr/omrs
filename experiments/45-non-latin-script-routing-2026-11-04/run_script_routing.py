"""Experiment 45: apply the shipped script detector to stored evidence (steps S1 to S4).

Run from the repository root:

    uv run --no-sync python experiments/45-non-latin-script-routing-2026-11-04/run_script_routing.py

Reads stored files and the 40 PDFs only. It makes no OCR call, no model call and no
network call (precondition P5). The detector is imported from the shipped module
``omrs.integrations.pdf.script_routing``; this file holds no copy of its rule.

Writes ``output/verdicts.json`` atomically (``.tmp`` then rename) and appends one line
to ``output/run-records.jsonl``. The run is short and has no checkpoint: a restart
starts again from S1 and appends a new run record.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import shlex
import sys
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))  # for experiments/_lib

import omrs.integrations.pdf.script_routing as script_routing  # noqa: E402
from _lib.run_record import record_run_start  # noqa: E402
from omrs.core.settings import EffectiveSettings  # noqa: E402
from omrs.integrations.pdf.page_routing import page_evidence  # noqa: E402
from omrs.integrations.pdf.script_routing import is_non_latin  # noqa: E402

PLAN = json.loads((HERE / "plan.json").read_text(encoding="utf-8"))
OUT = HERE / "output"
EXP33 = PLAN["inputs"]["exp33_dir"].removeprefix("experiments/")
EXP37 = PLAN["inputs"]["exp37_dir"].removeprefix("experiments/")
ROOTS = [
    REPO / "experiments",
    Path.home() / "Development/DATA/omrs/experiments",
    REPO.parent / "omrs-v3" / "experiments",  # read-only sibling checkout,
]
NON_LATIN_DOCS = ("io01", "io02", "io03", "io07")


class Stop(RuntimeError):
    """A precondition failed. The run stops before any score."""


def shown(path: Path) -> str:
    """A path without the user name: relative to the worktree, or `~`-based."""
    path = Path(path).resolve()
    for base, prefix in ((REPO, ""), (Path.home(), "~/")):
        try:
            return prefix + path.relative_to(base).as_posix()
        except ValueError:
            continue
    return path.as_posix()


def say(message: str) -> None:
    print(message, flush=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: Path) -> tuple[str, int]:
    """SHA-256 of the sorted `<file sha>  <relative path>` lines (plan.json method)."""
    files = sorted(
        (p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix()
    )
    text = "".join(f"{sha256_file(p)}  {p.relative_to(root).as_posix()}\n" for p in files)
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), len(files)


def find(relative: str) -> Path:
    """First root that holds *relative*. Nothing is written to any root."""
    for root in ROOTS:
        candidate = root / relative
        if candidate.exists():
            return candidate
    raise Stop(f"input not found in any root: {relative}")


def check_frozen() -> dict[str, Path]:
    """P1: every frozen input matches its SHA-256. Returns the resolved paths."""
    paths: dict[str, Path] = {}
    for entry in PLAN["frozen"]:
        relative = entry["file"].removeprefix("experiments/").rstrip("/")
        path = find(relative)
        if "tree_sha256" in entry:
            found, count = tree_sha256(path)
            expected, expected_count = entry["tree_sha256"], entry["files"]
            if found != expected or count != expected_count:
                raise Stop(f"P1 tree mismatch {relative}: {found} ({count}) != {expected}")
        else:
            found = sha256_file(path)
            if found != entry["sha256"]:
                raise Stop(f"P1 hash mismatch {relative}: {found} != {entry['sha256']}")
        paths[relative] = path
        say(f"P1 ok  {relative}  <- {shown(path)}")
    return paths


def check_detector() -> dict[str, object]:
    """P3: the module is the shipped one and the constants equal the plan's."""
    expected = PLAN["detector"]["expected_constants"]
    found = {
        "SCRIPT_DETECTOR_VERSION": script_routing.SCRIPT_DETECTOR_VERSION,
        "minimum_letters": script_routing.MIN_LETTERS,
        "non_latin_share": script_routing.NON_LATIN_SHARE,
    }
    if found != expected:
        raise Stop(f"P3 constants differ: {found} != {expected}")
    module_file = Path(script_routing.__file__).resolve()
    shipped = (REPO / "src/omrs/integrations/pdf/script_routing.py").resolve()
    if module_file != shipped:
        raise Stop(f"P3 module is not this worktree's shipped file: {module_file}")
    return {**found, "module_file": shown(module_file), "module_sha256": sha256_file(module_file)}


def check_cut() -> float:
    """The 0.9 cut is the default of the shipped settings model."""
    cut = EffectiveSettings.model_fields["ocr_local_min_confidence"].default
    if cut != PLAN["cut"]["ocr_local_min_confidence"]:
        raise Stop(f"cut differs: {cut}")
    return float(cut)


def page_class(doc: str, page: int, non_latin_pages: set[tuple[str, int]]) -> str:
    if (doc, page) in non_latin_pages:
        return "non_latin"
    return "unclassified" if doc in NON_LATIN_DOCS else "latin"


def load_class(paths: dict[str, Path]) -> set[tuple[str, int]]:
    """P2: the 129-page class from the Exp 37 E-script list equals the stored rows of the four documents."""
    state = json.loads(paths[f"{EXP37}/output/ocr_state_dots-mocr.json"].read_text("utf-8"))
    members = {
        (item.split(":")[0], int(item.split(":")[1]))
        for item in state["page_lists"]["E-script"]
        if item.split(":")[0] in NON_LATIN_DOCS
    }
    rows = json.loads(paths[f"{EXP33}/output/local_ocr/pages.json"].read_text("utf-8"))["rows"]
    stored = {(r["doc_id"], r["page"]) for r in rows if r["doc_id"] in NON_LATIN_DOCS}
    sizes = Counter(doc for doc, _ in members)
    expected_sizes = {"io01": 48, "io02": 16, "io03": 5, "io07": 60}
    if len(members) != 129 or dict(sizes) != expected_sizes:
        raise Stop(f"P2 class size differs: {len(members)} {dict(sizes)}")
    if members != stored:
        raise Stop("P2 class differs from the stored rows of the four documents")
    return members


def flag_scan(corpus: Path, non_latin_pages: set[tuple[str, int]]) -> list[dict]:
    """S2: flagged pages of each PDF, with the shipped point-1 verdict on the text items."""
    import pdf_inspector

    rows: list[dict] = []
    pdfs = sorted(corpus.glob("*.pdf"))
    for index, pdf in enumerate(pdfs, start=1):
        doc = pdf.stem
        evidence = page_evidence(pdf)
        flagged = sorted(e.page for e in evidence if e.needs_ocr)
        reasons = {e.page: e.reason for e in evidence}
        by_page: dict[int, list[str]] = {}
        if flagged:
            # The call the shipped `_text_layer_verdicts` makes (pages and TextItem.page from 1).
            for item in pdf_inspector.extract_text_with_positions(str(pdf), flagged):
                by_page.setdefault(item.page, []).append(item.text)
            shipped_set = script_routing._text_layer_verdicts(pdf, flagged)  # noqa: SLF001
        else:
            shipped_set = frozenset()
        mine = set()
        for page in flagged:
            items = by_page.get(page, [])
            verdict = is_non_latin(" ".join(items))
            if verdict is True:
                mine.add(page)
            rows.append(
                {
                    "doc_id": doc,
                    "page": page,
                    "page_class": page_class(doc, page, non_latin_pages),
                    "ocr_reason": reasons.get(page),
                    "text_items": len(items),
                    "verdict": verdict,
                }
            )
        if mine != set(shipped_set):
            raise Stop(f"S2 cross-check failed for {doc}: {sorted(mine)} != {sorted(shipped_set)}")
        say(f"S2 {index}/{len(pdfs)} {doc}: pages={len(evidence)} flagged={len(flagged)} non_latin={len(mine)}")
    return rows


def script_letters(text: str) -> Counter:
    """Descriptive only: letters per Unicode script word (first word of the character name)."""
    counter: Counter = Counter()
    for char in text:
        if char.isalpha():
            counter[unicodedata.name(char, "UNKNOWN").split()[0]] += 1
    return counter


def stored_rows(paths: dict[str, Path], cut: float, non_latin_pages: set[tuple[str, int]]):
    """S3: stored local OCR rows, the shipped escalation reasons, and the shipped verdict."""
    rows = json.loads(paths[f"{EXP33}/output/local_ocr/pages.json"].read_text("utf-8"))["rows"]
    text_dir = paths[f"{EXP33}/output/.local_ocr_text"]
    out: list[dict] = []
    scripts: dict[str, Counter] = {doc: Counter() for doc in NON_LATIN_DOCS}
    for row in rows:
        doc, page = row["doc_id"], row["page"]
        text = (text_dir / doc / f"p{page:03d}.md").read_text(encoding="utf-8")
        confidence = row["confidence"]
        reasons: list[str] = []
        if row["error_class"]:
            reasons.append("error")
        if not text.strip():
            reasons.append("empty_text")
        if confidence is None or confidence < cut:
            reasons.append("low_confidence")
        if row["hosted_recommended"]:
            reasons.append("hosted_recommended")
        verdict = is_non_latin(text)
        if doc in NON_LATIN_DOCS:
            scripts[doc].update(script_letters(text))
        out.append(
            {
                "doc_id": doc,
                "page": page,
                "page_class": page_class(doc, page, non_latin_pages),
                "confidence": confidence,
                "doc_seconds_share": row["doc_seconds_share"],
                "doc_over_soft_timeout": row["doc_over_soft_timeout"],
                "reasons": reasons,
                "kept_by_cut": not reasons,
                "verdict": verdict,
            }
        )
    say(f"S3 {len(out)} stored rows scored")
    return out, {doc: dict(counter.most_common(6)) for doc, counter in scripts.items()}


def engine_rows(paths: dict[str, Path], non_latin_pages: set[tuple[str, int]]) -> list[dict]:
    """S4: the shipped detector on the Experiment 37 dots.mocr page text."""
    root = paths[f"{EXP37}/output/dots-mocr"]
    out: list[dict] = []
    for file in sorted(root.glob("*/p*.md")):
        doc, page = file.parent.name, int(file.stem[1:])
        verdict = is_non_latin(file.read_text(encoding="utf-8"))
        out.append(
            {
                "doc_id": doc,
                "page": page,
                "page_class": page_class(doc, page, non_latin_pages),
                "verdict": verdict,
            }
        )
    say(f"S4 {len(out)} engine page files scored")
    return out


def write_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    detector = check_detector()
    command = shlex.join(sys.argv) + f" # detector_sha256={detector['module_sha256']}"
    record_run_start(HERE, command=command)
    say("S1 preconditions")
    paths = check_frozen()
    non_latin_pages = load_class(paths)
    say(f"P2 ok  class of {len(non_latin_pages)} pages equals the stored rows of {NON_LATIN_DOCS}")
    say(f"P3 ok  {detector}")
    version = importlib.metadata.version("pdf-inspector")
    if version != PLAN["engine"]["pdf_inspector"]:
        raise Stop(f"P4 pdf-inspector {version} != {PLAN['engine']['pdf_inspector']}")
    say(f"P4 ok  pdf-inspector {version}")
    cut = check_cut()
    say(f"cut ok {cut}")

    corpus = paths[f"{EXP33}/corpus/natural"]
    flag_rows = flag_scan(corpus, non_latin_pages)
    local_rows, scripts = stored_rows(paths, cut, non_latin_pages)
    engine = engine_rows(paths, non_latin_pages)

    write_atomic(
        OUT / "verdicts.json",
        {
            "meta": {
                "detector": detector,
                "cut": cut,
                "pdf_inspector": version,
                "inputs": {key: shown(path) for key, path in paths.items()},
                "script_letters_stored_local_text_descriptive": scripts,
            },
            "flag_rows": flag_rows,
            "local_rows": local_rows,
            "engine_rows": engine,
        },
    )
    say("wrote output/verdicts.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Stop as stop:
        print(f"STOP: {stop}", file=sys.stderr, flush=True)
        sys.exit(2)
