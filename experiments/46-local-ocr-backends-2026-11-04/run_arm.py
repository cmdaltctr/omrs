"""Experiment 46: check the inputs, draw the page sample, and run one OCR arm.

Run from the repository root. Three commands:

    uv run --no-sync python experiments/46-local-ocr-backends-2026-11-04/run_arm.py check
    uv run --no-sync python experiments/46-local-ocr-backends-2026-11-04/run_arm.py sample
    <arm python> experiments/46-local-ocr-backends-2026-11-04/run_arm.py --arm <b|d> --resume

``check`` runs preconditions P1 to P5 (protocol section 5, step 1). ``sample`` writes
``pages.json`` from seed 46. An arm run reads one page image at a time and appends one row
to ``output/arm_<id>.jsonl`` (text, lines, page confidence, seconds, error). The control
(arm A) is read from stored Experiment 33 output by ``summarise.py`` and runs no OCR here.

This module holds the pure rules and imports only the standard library, so each arm can run
in its own scratch environment. The heavy OCR packages are imported inside the engine
functions. Outputs are written atomically (``.tmp`` then rename).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shlex
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "output"
PAGES = HERE / "pages.json"

EXP33 = "33-ocr-routing-natural-positive-2026-09-17"
EXP37 = "37-dots-mocr-routing-acceptance-2026-09-30"
ROOTS = [
    REPO / "experiments",
    Path.home() / "Development/DATA/omrs/experiments",
    REPO.parent / "omrs-v3" / "experiments",  # read-only sibling checkout
]

sys.path.insert(0, str(REPO / "experiments" / EXP33))
from build_labels import recall, tokens  # noqa: E402  (Experiment 33 tokeniser, standard library)

SEED = 46
SCRIPTS = {"io01": "devanagari", "io02": "arabic", "io03": "arabic", "io07": "bengali"}
LATIN_STRATA = (  # (stratum, documents, pages drawn); the order is part of the rule
    ("print", ("io04", "io05"), 30),
    ("old_print", ("io06",), 35),
    ("handwriting", ("rf06", "rf07"), 35),
)
WARMUP_PAGES = 3  # the first pages of an arm are not timed
STOP_AFTER_TIMED = 20  # stop rule: a median above STOP_SECONDS over the first 20 timed pages
STOP_SECONDS = 15.0
ARM_LANGUAGES = {"arabic": "ar-SA", "devanagari": "hi-IN", "latin": "en-US"}  # arm D oracle
MIN_LONG_LINE = 10
CONFIDENT_AT = 0.8


class Stop(RuntimeError):
    """A precondition failed. The run stops before any score."""


def say(message: str) -> None:
    print(message, flush=True)


# --- pure rules ----------------------------------------------------------------------------


def draw_latin_sample(eligible: dict[str, list[int]], seed: int = SEED) -> list[dict[str, Any]]:
    """Draw the Latin pages: 30 print, 35 old print, 35 handwriting, same on every call.

    Args:
        eligible: Document id to its eligible page numbers.
        seed: The seed of the draw.

    Returns:
        Dicts with ``doc``, ``page`` and ``stratum``, sorted by document and page.

    Raises:
        Stop: A stratum has fewer eligible pages than its draw.
    """
    rng = random.Random(seed)  # noqa: S311  (a seeded sample, not a secret)
    drawn: list[dict[str, Any]] = []
    for stratum, docs, count in LATIN_STRATA:
        pool = sorted((doc, page) for doc in docs for page in eligible.get(doc, []))
        if len(pool) < count:
            raise Stop(f"P3 stratum {stratum} has {len(pool)} eligible pages, needs {count}")
        drawn += [{"doc": d, "page": p, "stratum": stratum} for d, p in rng.sample(pool, count)]
    return sorted(drawn, key=lambda page: (page["doc"], page["page"]))


def page_recall(text: str | None, reference: list[str]) -> float:
    """Token recall of *text* against *reference*. A page with no output scores 0."""
    if text is None or not text.strip():
        return 0.0
    return recall(text, reference)


def _line_characters(text: str) -> int:
    return len("".join(text.split()))


def page_confidence(lines: list[tuple[str, float]]) -> float | None:
    """Mean line confidence weighted by characters (design D5). None without characters."""
    weighted = [(_line_characters(text), conf) for text, conf in lines]
    total = sum(n for n, _ in weighted)
    return sum(n * conf for n, conf in weighted) / total if total else None


def min_confidence_long_lines(lines: list[tuple[str, float]]) -> float | None:
    """Exploratory: the lowest confidence over lines of 10 or more characters."""
    values = [conf for text, conf in lines if _line_characters(text) >= MIN_LONG_LINE]
    return min(values) if values else None


def share_confident_characters(lines: list[tuple[str, float]]) -> float | None:
    """Exploratory: the share of characters on lines at 0.8 confidence or above."""
    total = sum(_line_characters(text) for text, _ in lines)
    if not total:
        return None
    return sum(_line_characters(t) for t, conf in lines if conf >= CONFIDENT_AT) / total


def should_stop(timed_seconds: list[float]) -> bool:
    """Stop rule: the first 20 timed pages have a median above 15 s."""
    return len(timed_seconds) >= STOP_AFTER_TIMED and (
        statistics.median(timed_seconds[:STOP_AFTER_TIMED]) > STOP_SECONDS
    )


# --- files ---------------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: Path) -> tuple[str, int]:
    """SHA-256 of the sorted ``<file sha>  <relative path>`` lines, and the file count."""
    files = sorted(
        (p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix()
    )
    text = "".join(f"{sha256_file(p)}  {p.relative_to(root).as_posix()}\n" for p in files)
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), len(files)


def find(relative: str) -> Path:
    """The first root that holds *relative*. Nothing is written to any root."""
    for root in ROOTS:
        if (root / relative).exists():
            return root / relative
    raise Stop(f"input not found in any root: {relative}")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_plan() -> dict[str, Any]:
    return json.loads((HERE / "plan.json").read_text(encoding="utf-8"))


def stored_rows() -> list[dict[str, Any]]:
    """The 464 stored PP-OCRv6 rows of Experiment 33."""
    path = find(f"{EXP33}/output/local_ocr/pages.json")
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def stored_text(doc: str, page: int) -> str:
    """The stored PP-OCRv6 text of a page. Empty when the page has no text file."""
    path = find(f"{EXP33}/output/.local_ocr_text") / doc / f"p{page:03d}.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def page_image(doc: str, page: int) -> Path:
    return find(f"{EXP33}/output/.pages") / doc / f"p{page:03d}.png"


def split_reference(doc: str, page: int) -> list[str] | None:
    """Reference tokens from the split body text. None when no split transcript exists."""
    path = find(f"{EXP37}/corpus/exp33_transcripts_split") / doc / f"p{page:03d}.json"
    if not path.is_file():
        return None
    return tokens(json.loads(path.read_text(encoding="utf-8")).get("body_text") or "")


def reference_tokens(doc: str, page: int) -> list[str]:
    """Split body text when it exists, else the first transcription (Experiment 33 rule)."""
    split = split_reference(doc, page)
    if split is not None:
        return split
    path = find(f"{EXP37}/corpus/exp33_transcripts") / doc / f"p{page:03d}.json"
    return tokens(json.loads(path.read_text(encoding="utf-8")).get("transcription") or "")


# --- steps ---------------------------------------------------------------------------------


def eligible_latin(rows: list[dict[str, Any]]) -> dict[str, list[int]]:
    """Pages with a stored row, a split transcript and at least one reference token."""
    pools: dict[str, list[int]] = {}
    for _, docs, _ in LATIN_STRATA:
        for doc in docs:
            pools[doc] = sorted(
                r["page"]
                for r in rows
                if r["doc_id"] == doc and (split_reference(doc, r["page"]) or [])
            )
    return pools


def check() -> int:
    """P1 to P5. Returns 2 when only fill-in values are missing from plan.json."""
    plan, missing = load_plan(), 0
    for entry in plan["frozen"]:
        relative = entry["file"].removeprefix("experiments/").rstrip("/")
        if relative.startswith("46-"):
            continue  # pages.json is hashed after the sample step
        path = find(relative)
        if "tree_sha256" in entry:
            found, count = tree_sha256(path)
            if entry["tree_sha256"].startswith("fill"):
                say(f"FILL  {relative}  tree_sha256={found}  files={count}")
                missing += 1
            elif (found, count) != (entry["tree_sha256"], entry.get("files", count)):
                raise Stop(f"P1 tree mismatch {relative}: {found} ({count})")
        else:
            found = sha256_file(path)
            if found != entry["sha256"]:
                raise Stop(f"P1 hash mismatch {relative}: {found}")
        say(f"P1 ok {relative}")
    rows = stored_rows()
    non_latin = [r for r in rows if r["doc_id"] in SCRIPTS]
    if len(non_latin) != 129:
        raise Stop(f"P2 non-Latin class has {len(non_latin)} stored rows, expected 129")
    say("P2 ok 129 non-Latin rows")
    pools = eligible_latin(rows)
    sample = draw_latin_sample(pools)
    say(f"P3 ok pools { {d: len(p) for d, p in pools.items()} } draw {len(sample)}")
    pages = [(r["doc_id"], r["page"]) for r in non_latin] + [(s["doc"], s["page"]) for s in sample]
    absent = [k for k in pages if not page_image(*k).is_file()]
    if absent:
        raise Stop(f"P4 {len(absent)} page images missing, first {absent[:3]}")
    say("P4 ok every page has a PNG")
    by_key = {(r["doc_id"], r["page"]): r for r in rows}
    worst = 0.0
    for doc, page in pages:
        reference = reference_tokens(doc, page)
        diff = abs(
            page_recall(stored_text(doc, page), reference) - by_key[(doc, page)]["body_recall"]
        )
        worst = max(worst, diff)
    if worst > 0.0005:
        raise Stop(f"P5 tokeniser does not reproduce stored body_recall: worst {worst:.4f}")
    say(f"P5 ok tokeniser reproduces stored body_recall on {len(pages)} pages (worst {worst:.4f})")
    return 2 if missing else 0


def sample() -> int:
    """Write pages.json: 129 non-Latin pages and the 100-page Latin draw."""
    rows = stored_rows()
    pages = [
        {"doc": r["doc_id"], "page": r["page"], "script": SCRIPTS[r["doc_id"]], "stratum": None}
        for r in rows
        if r["doc_id"] in SCRIPTS
    ]
    pages += [{**s, "script": "latin"} for s in draw_latin_sample(eligible_latin(rows), SEED)]
    pages.sort(key=lambda p: (p["doc"], p["page"]))
    write_json(PAGES, {"seed": SEED, "pages": pages})
    say(f"pages.json {len(pages)} pages sha256 {sha256_file(PAGES)}")
    return 0


def record_run(command: str) -> None:
    """Append a run record. An arm environment has no omrs, so the repository python does it."""
    code = (
        "import sys; sys.path.insert(0, 'experiments'); from pathlib import Path; "
        "from _lib.run_record import record_run_start; "
        f"record_run_start(Path({str(HERE)!r}), command={command!r})"
    )
    subprocess.run(["uv", "run", "--no-sync", "python", "-c", code], cwd=REPO, check=True)  # noqa: S603, S607


def append_row(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_done(path: Path) -> set[tuple[str, int]]:
    if not path.is_file():
        return set()
    rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line)
    return {(r["doc"], r["page"]) for r in rows}


Lines = list[tuple[str, float]]  # (line text, line confidence)


class Engine(NamedTuple):
    """One arm: which pages it reads, and a loader that returns ``read(png, script)``."""

    runs: Callable[[dict[str, Any]], bool]
    load: Callable[[], Callable[[Path, str], Lines]]


def _load_indra() -> Callable[[Path, str], Lines]:
    """Arm B: Indra OCR 1.1.2 on ONNX Runtime, CPU, default threads, no script hint.

    The weights folder comes from ``INDRA_OCR_MODEL_DIR`` (set it to the downloaded snapshot),
    so the run does no network call and the weights match the hash in ``plan.json``.
    """
    from indra_ocr import OrtOCR, model_dir  # noqa: PLC0415
    from indra_ocr.pipeline import read_images  # noqa: PLC0415

    ocr = OrtOCR(model_dir())

    def read(png: Path, script: str) -> Lines:
        page = ocr(read_images(png)[0])
        return [(line.text, float(line.conf)) for line in page.lines]

    return read


def _load_vision() -> Callable[[Path, str], Lines]:
    """Arm D: Apple Vision through ocrmac, accurate level, with the oracle language."""
    from ocrmac import ocrmac  # noqa: PLC0415

    def read(png: Path, script: str) -> Lines:
        found = ocrmac.OCR(
            str(png), recognition_level="accurate", language_preference=[ARM_LANGUAGES[script]]
        ).recognize()
        return [(text, float(conf)) for text, conf, _box in found]

    return read


ENGINES = {
    "b": Engine(runs=lambda page: True, load=_load_indra),  # Indra reads all 229 pages
    "d": Engine(runs=lambda page: page["script"] != "bengali", load=_load_vision),  # no Bengali
}


def run_arm(arm: str, resume: bool) -> int:
    """Read the arm's pages one at a time and append one row per page."""
    spec = ENGINES[arm]
    pages = [p for p in json.loads(PAGES.read_text(encoding="utf-8"))["pages"] if spec.runs(p)]
    target = OUT / f"arm_{arm}.jsonl"
    done = read_done(target)
    if done and not resume:
        raise Stop(f"{target.name} has rows; pass --resume to continue it")
    record_run(" ".join(shlex.quote(a) for a in [sys.executable, *sys.argv]))
    started = time.perf_counter()
    engine = spec.load()
    write_json(OUT / f"arm_{arm}.load.json", {"seconds": round(time.perf_counter() - started, 3)})
    timed: list[float] = []
    for index, page in enumerate(pages):
        if (page["doc"], page["page"]) in done:
            continue
        began = time.perf_counter()
        try:
            lines, error = engine(page_image(page["doc"], page["page"]), page["script"]), None
        except Exception as exc:  # noqa: BLE001  (one bad page must not end the arm)
            lines, error = [], f"{type(exc).__name__}: {exc}"
        seconds = time.perf_counter() - began
        is_timed = index >= WARMUP_PAGES
        text = "\n".join(t for t, _ in lines)
        append_row(
            target,
            {
                "arm": arm,
                **{k: page[k] for k in ("doc", "page", "script", "stratum")},
                "text": text,
                "lines": [[t, c] for t, c in lines],
                "page_confidence": page_confidence(lines),
                "min_conf_long_lines": min_confidence_long_lines(lines),
                "share_confident_chars": share_confident_characters(lines),
                "seconds": round(seconds, 4),
                "timed": is_timed,
                "error": error,
            },
        )
        say(f"{arm} {page['doc']} p{page['page']:03d} {seconds:.2f}s")
        if is_timed:
            timed.append(seconds)
        if should_stop(timed):
            write_json(
                OUT / f"arm_{arm}.stopped.json", {"median_first_20": statistics.median(timed[:20])}
            )
            say("STOP rule: median of the first 20 timed pages is above 15 s. G4 fails.")
            return 0
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("step", nargs="?", choices=("check", "sample"))
    parser.add_argument("--arm", choices=("b", "d"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    try:
        if args.step == "check":
            return check()
        if args.step == "sample":
            return sample()
        if args.arm:
            return run_arm(args.arm, args.resume)
        parser.error("give a step (check or sample) or --arm")
    except Stop as stop:
        say(f"STOP {stop}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
