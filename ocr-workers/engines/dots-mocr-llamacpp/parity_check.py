#!/usr/bin/env python3
"""Parity check for the dots-mocr-llamacpp engine (task 3.3; design D9 item 1).

Parses 22 pages through the app's OCR path (``build_ocr_routes``, primary engine
``dots-mocr-llamacpp``, so the host's RuntimeManager starts the ``llama-server``)
and compares each page with two Experiment 41 references: arm D4 (this engine's
GGUF Q8_0 build in the Experiment 41 harness) and the T-control text (shipped
PyTorch backend, ``T-D0``; eq01:3 was not re-timed, so it takes the Experiment 37
``dots-mocr`` text, the same backend). The pages are the 21 of ``T-D0`` (warm-up
eq01:2 and the 20 T-control pages) plus eq01:3. Pass rules:

1. every page has Dice >= 0.99 against D4;
2. at least 18 of 22 pages are identical to D4 (outer whitespace trimmed);
3. the median Dice against the T-control text is >= 0.99.

Dice is Experiment 41's (``analysis.py``, Experiment 33 ``tokens``).

Usage::

    python3 ocr-workers/engines/dots-mocr-llamacpp/parity_check.py          # plan only
    uv run --no-sync python ocr-workers/engines/dots-mocr-llamacpp/parity_check.py --run

Without ``--run`` the script prints the plan and touches nothing. ``--run`` uses a
scratch ``OMRS_STATE_DIR`` and ``OMRS_CONFIG_DIR`` (never ``~/.omrs``) and writes
``smoke_evidence/parity.json`` after every page. ``--resume`` keeps finished pages.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import os
import statistics
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ENGINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = ENGINE_DIR.parents[2]
ENGINE_NAME = "dots-mocr-llamacpp"
EVIDENCE_DIR = ENGINE_DIR / "smoke_evidence"
RESULT_PATH = EVIDENCE_DIR / "parity.json"
EXPERIMENTS = REPO_ROOT / "experiments"
EXP41_DIR = EXPERIMENTS / "41-ocr-runtimes-2026-10-30"
EXP37_D0 = "omrs-v3/experiments/37-dots-mocr-routing-acceptance-2026-09-30/output/dots-mocr"
DEFAULT_EXP37_D0 = REPO_ROOT.parent / EXP37_D0
DEFAULT_EXP41_OUTPUT = Path.home() / "Development/DATA/omrs/experiments" / EXP41_DIR.name / "output"
EXP33_BUILD_LABELS = EXPERIMENTS / "33-ocr-routing-natural-positive-2026-09-17/build_labels.py"
BUILD_LABELS_SHA256 = "4d9faa5437ee02d3de256a0fea156f9b02942e1798e2784a4f022497ac1ba2fa"

#: The 21 pages of Experiment 41 ``T-D0`` (warm-up eq01:2, 20 T-control pages), then eq01:3.
PAGES = (
    "eq01:2", "mp05:13", "io04:49", "io01:13", "io01:17", "io01:24", "io01:26",
    "io01:39", "io02:2", "io02:3", "io07:28", "io07:34", "io07:56", "io07:63",
    "rf06:29", "rf06:46", "rf06:50", "rf06:86", "rf07:6", "rf07:47", "rf07:49",
    "eq01:3",
)  # fmt: skip
DICE_FLOOR = MEDIAN_FLOOR = 0.99
MIN_IDENTICAL = 18


@dataclass(frozen=True)
class References:
    """The two reference texts of one page and where the T-control text came from."""

    d4: str
    tcontrol: str
    tcontrol_source: str


@functools.cache
def exp33_tokens() -> Callable[[str], list[str]]:
    """Import ``tokens`` from the Experiment 33 file, after a SHA-256 check."""
    digest = hashlib.sha256(EXP33_BUILD_LABELS.read_bytes()).hexdigest()
    if digest != BUILD_LABELS_SHA256:
        raise SystemExit("Experiment 33 build_labels.py changed: not the frozen tokeniser")
    spec = importlib.util.spec_from_file_location("exp33_build_labels", EXP33_BUILD_LABELS)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.tokens


def text_dice(a: str, b: str) -> float:
    """Return Experiment 41's token Dice of two texts (1.0 when both have no tokens)."""
    left, right = exp33_tokens()(a), exp33_tokens()(b)
    if not left and not right:
        return 1.0
    return 2 * sum((Counter(left) & Counter(right)).values()) / (len(left) + len(right))


def page_file(folder: Path, key: str) -> Path:
    """Return where Experiment 41 stored page *key* under *folder* (``<doc>/p<NNN>.md``)."""
    doc, page = key.split(":")
    return folder / doc / f"p{int(page):03d}.md"


def load_references(key: str, exp41_output: Path, exp37_d0: Path) -> References:
    """Read the D4 and T-control texts of page *key* (``T-D0``, else Experiment 37 D0).

    Raises:
        SystemExit: The D4 text, or both T-control texts, are missing. Nothing is invented.
    """
    d4 = page_file(exp41_output / "D4", key)
    if not d4.is_file():
        raise SystemExit(f"no D4 text for {key}: {d4}")
    for source, folder in (("T-D0", exp41_output / "T-D0"), ("exp37-D0", exp37_d0)):
        path = page_file(folder, key)
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            return References(d4.read_text(encoding="utf-8"), text, source)
    raise SystemExit(f"no T-control text for {key} in T-D0 or the Experiment 37 folder")


def evaluate_rules(entries: Sequence[dict[str, Any]], expected: int = len(PAGES)) -> dict[str, Any]:
    """Apply the three pass rules; an error entry counts as Dice 0.0, not identical.

    Returns:
        One result per rule, ``complete`` and ``pass``. An unfinished run never passes.
    """
    keys = [f"{e['doc']}:{e['page']}" for e in entries]
    d4 = [e.get("dice_d4") or 0.0 for e in entries]
    tc = [e["dice_tcontrol"] for e in entries if e.get("dice_tcontrol") is not None]
    failing = [k for k, v in zip(keys, d4, strict=True) if v < DICE_FLOOR]
    same = sum(bool(e.get("identical_d4")) for e in entries)
    median = statistics.median(tc) if tc else 0.0
    rules = {
        "rule1_dice_d4_min": {
            "rule": f"every page Dice >= {DICE_FLOOR} against D4",
            "min": min(d4, default=0.0),
            "failing": failing,
            "pass": not failing and bool(entries),
        },
        "rule2_identical_d4": {
            "rule": f"at least {MIN_IDENTICAL} of {expected} pages identical to D4",
            "identical": same,
            "pass": same >= MIN_IDENTICAL,
        },
        "rule3_median_dice_tcontrol": {
            "rule": f"median Dice against the T-control text >= {MEDIAN_FLOOR}",
            "median": median,
            "pass": median >= MEDIAN_FLOOR,
        },
    }
    complete = len(entries) == expected
    return {
        **rules,
        "complete": complete,
        "pass": complete and all(r["pass"] for r in rules.values()),
    }


def write_atomic(path: Path, data: dict[str, Any]) -> None:
    """Write *data* as JSON through a ``.tmp`` file, then rename it over *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def collect(
    parse: Callable[[str, int], str],
    refs_for: Callable[[str], References],
    path: Path,
    *,
    pages: Sequence[str] = PAGES,
    resume: bool = False,
) -> dict[str, Any]:
    """Parse each page, score it against both references, checkpoint after each page.

    Raises SystemExit when *path* exists and *resume* is false.
    """
    if path.is_file() and not resume:
        raise SystemExit(f"{path.name} exists: pass --resume to continue")
    state: dict[str, Any] = {"pages": {}}
    if resume and path.is_file():
        state = json.loads(path.read_text(encoding="utf-8"))
    state.update(engine=ENGINE_NAME, references={"d4": "Experiment 41 arm D4", "tcontrol": "T-D0"})
    done: dict[str, Any] = state["pages"]

    def save() -> dict[str, Any]:
        rules = evaluate_rules([done[k] for k in pages if k in done], len(pages))
        full = state | rules | {"heartbeat_utc": datetime.now(UTC).isoformat()}
        write_atomic(path, full)
        return full

    for key in pages:
        if done.get(key, {}).get("status") == "ok":
            continue
        doc, page = key.split(":")
        entry: dict[str, Any] = {"doc": doc, "page": int(page)}
        started = time.perf_counter()
        try:
            text = parse(doc, int(page))
            refs = refs_for(key)
            pages_dir = path.parent / "parity-pages"
            pages_dir.mkdir(parents=True, exist_ok=True)
            (pages_dir / f"{doc}-p{int(page):03d}.md").write_text(text, encoding="utf-8")
            entry.update(
                status="ok",
                seconds=round(time.perf_counter() - started, 2),
                chars=len(text),
                sha256=hashlib.sha256(text.encode()).hexdigest(),
                dice_d4=round(text_dice(text, refs.d4), 4),
                identical_d4=text.strip() == refs.d4.strip(),
                dice_tcontrol=round(text_dice(text, refs.tcontrol), 4),
                tcontrol_source=refs.tcontrol_source,
            )
        except Exception as exc:  # noqa: BLE001 - one bad page must not lose the others
            entry.update(status="error", error=f"{type(exc).__name__}: {exc}")
        done[key] = entry
        save()
        print(f"[parity] {key} {entry['status']} {entry.get('seconds', '-')} s", flush=True)
    return save()


def plan_lines(exp41_output: Path, exp37_d0: Path) -> list[str]:
    """Return the text of the plan: pages, reference sources, output path."""
    missing = [k for k in PAGES if not page_file(exp41_output / "D4", k).is_file()]
    return [
        f"parity check for {ENGINE_NAME}: {len(PAGES)} pages (plan only, nothing is run)",
        "pages: " + " ".join(PAGES),
        f"D4 text: {exp41_output / 'D4'} (missing: {len(missing)})",
        f"T-control text: {exp41_output / 'T-D0'}, else {exp37_d0} (eq01:3)",
        f"output: {RESULT_PATH}",
        "run: uv run --no-sync python ocr-workers/engines/dots-mocr-llamacpp/parity_check.py --run",
    ]


def run(args: argparse.Namespace) -> int:
    """Parse the pages through ``build_ocr_routes`` with scratch state and write the result."""
    scratch = tempfile.TemporaryDirectory(prefix="omrs-parity-")
    os.environ["OMRS_STATE_DIR"] = str(Path(scratch.name) / "state")
    os.environ["OMRS_CONFIG_DIR"] = str(Path(scratch.name) / "config")
    sys.path.insert(0, str(EXP41_DIR))
    import run_ocr  # Experiment 41's corpus helper (checks the PDFs' SHA-256)

    from omrs.capabilities import build_ocr_routes
    from omrs.compose_runtime_manager import close_runtime_manager
    from omrs.config import Settings
    from omrs.integrations.ocr_worker.routes import request_timeout

    settings = Settings(
        ocr_fallback_enabled=True,
        ocr_workers_dir=str(REPO_ROOT / "ocr-workers"),
        ocr_engine_primary=ENGINE_NAME,
        ocr_engine_fallback="",
        pdf_reader="pypdf",
    )
    pdfs = run_ocr.corpus(list(PAGES))
    routes = build_ocr_routes(settings)
    try:
        client = routes.select()
        if client is None or client is not routes.primary:
            print(f"the {ENGINE_NAME} route is unavailable: provision the engine", file=sys.stderr)
            return 1

        def parse(doc: str, page: int) -> str:
            timeout = request_timeout(settings, 1)
            result = client.parse(str(pdfs[doc]), pages=[page], timeout=timeout)
            return (result.pages_markdown or (result.markdown,))[0]

        def refs_for(key: str) -> References:
            return load_references(key, args.exp41_output, args.exp37_d0)

        for key in PAGES:  # stop before the first parse when a reference is missing
            refs_for(key)
        result = collect(parse, refs_for, RESULT_PATH, resume=args.resume)
    finally:
        routes.close()
        close_runtime_manager()
        scratch.cleanup()
    for name, rule in result.items():
        if name.startswith("rule"):
            print(f"{name}: {'PASS' if rule['pass'] else 'FAIL'} {rule}")
    print(f"overall: {'PASS' if result['pass'] else 'FAIL'} -> {RESULT_PATH}")
    return 0 if result["pass"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Print the plan, or with ``--run`` run the parity check."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", action="store_true", help="parse the pages (starts llama-server)")
    parser.add_argument("--resume", action="store_true", help="skip pages already in parity.json")
    parser.add_argument("--exp41-output", type=Path, default=DEFAULT_EXP41_OUTPUT)
    parser.add_argument("--exp37-d0", type=Path, default=DEFAULT_EXP37_D0)
    args = parser.parse_args(argv)
    if not args.run:
        print("\n".join(plan_lines(args.exp41_output, args.exp37_d0)))
        return 0
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
