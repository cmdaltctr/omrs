"""Experiment 46a: sweep the confidence cut of each local OCR backend on saved Experiment 46 output.

Run from the repository root:

    uv run --no-sync python experiments/46a-local-ocr-per-backend-cuts-2026-11-06/analysis.py \
        --source <Experiment 46 output folder>

Runs no OCR and no model. The row loader, the token recall rule and the bad-page rule are
imported from Experiment 46 (``summarise.py`` and ``run_arm.py``). Nothing is copied here.
Writes ``output/cut_sweep.json`` in this folder. Rules fixed before the run:

- A page is kept when its page confidence is not None and at least the cut.
- A kept page is bad when its token recall is below 0.5 (Experiment 46's ``BAD_BELOW``).
- No script filter applies to any backend.
- The chain sends every page the first backend does not keep to the second backend.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
EXP46 = HERE.parent / "46-local-ocr-backends-2026-11-04"
sys.path.insert(0, str(EXP46))

import run_arm  # noqa: E402  (Experiment 46: page recall rule, file helpers)
import summarise  # noqa: E402  (Experiment 46: row loader, BAD_BELOW)

CUTS = [round(0.85 + 0.01 * i, 2) for i in range(13)]  # 0.85 ... 0.97
CHAIN_SECOND_CUT = 0.94
BAD_LIMIT = Fraction(1, 20)


def _is_bad(row: dict[str, Any]) -> bool:
    return Fraction(str(row["recall"])) < summarise.BAD_BELOW


def _kept(row: dict[str, Any], cut: float) -> bool:
    return row["conf"] is not None and row["conf"] >= cut


def _summary(kept: list[dict[str, Any]]) -> dict[str, Any]:
    bad = [r for r in kept if _is_bad(r)]
    return {
        "kept": len(kept),
        "bad": len(bad),
        "bad_share": round(len(bad) / len(kept), 4) if kept else None,
        "under_limit": bool(kept) and Fraction(len(bad), len(kept)) <= BAD_LIMIT,
        "bad_by_script": dict(sorted(Counter(r["script"] for r in bad).items())),
        "kept_by_script": dict(sorted(Counter(r["script"] for r in kept).items())),
    }


def sweep_single(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One backend alone at every cut."""
    return [{"cut": cut, **_summary([r for r in rows if _kept(r, cut)])} for cut in CUTS]


def sweep_chain(
    first: list[dict[str, Any]], second: list[dict[str, Any]], second_cut: float
) -> list[dict[str, Any]]:
    """First backend at every cut, then the second backend at *second_cut* on the rest."""
    by_key = {(r["doc"], r["page"]): r for r in second}
    out = []
    for cut in CUTS:
        kept_first = [r for r in first if _kept(r, cut)]
        rest = [by_key[(r["doc"], r["page"])] for r in first if not _kept(r, cut)]
        kept_second = [r for r in rest if _kept(r, second_cut)]
        out.append(
            {
                "first_cut": cut,
                "second_cut": second_cut,
                "kept_by_first": len(kept_first),
                "kept_by_second": len(kept_second),
                **_summary(kept_first + kept_second),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True, type=Path, help="Experiment 46 output folder")
    source = parser.parse_args().source.resolve()
    if not (source / "arm_b.jsonl").is_file():
        sys.exit("--source must hold arm_b.jsonl from Experiment 46")
    summarise.OUT = source  # the row loader reads arm files from here
    pages = json.loads(run_arm.PAGES.read_text(encoding="utf-8"))["pages"]
    pp = summarise._arm_rows("A", pages)
    indra = summarise._arm_rows("B", pages)
    if pp is None or indra is None or len(pp) != len(pages) or len(indra) != len(pages):
        sys.exit("a backend has missing rows; the sweep would be wrong")
    result = {
        "pages": len(pages),
        "documents": len({p["doc"] for p in pages}),
        "bad_below_recall": float(summarise.BAD_BELOW),
        "bad_share_limit": float(BAD_LIMIT),
        "pp_ocrv6_small_alone": sweep_single(pp),
        "indra_alone": sweep_single(indra),
        "chain_pp_then_indra": sweep_chain(pp, indra, CHAIN_SECOND_CUT),
        "inputs_sha256": {
            "pages.json": run_arm.sha256_file(run_arm.PAGES),
            "arm_b.jsonl": run_arm.sha256_file(source / "arm_b.jsonl"),
            "exp33_local_ocr_pages.json": run_arm.sha256_file(
                run_arm.find(f"{run_arm.EXP33}/output/local_ocr/pages.json")
            ),
        },
    }
    run_arm.write_json(HERE / "output" / "cut_sweep.json", result)
    print(f"wrote {HERE / 'output' / 'cut_sweep.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
