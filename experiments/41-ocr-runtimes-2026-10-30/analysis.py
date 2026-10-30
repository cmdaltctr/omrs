"""Experiment 41 analysis: page similarity of an arm against a baseline arm.

    analysis.py --arm D4              # against D0 (dots.mocr) or P0 (PaddleOCR-VL)
    analysis.py --arm D4 --baseline D2    # matched-runtime pair, reported only

For every page both arms have text for, the script computes the token Dice coefficient with
the Experiment 33 tokeniser (``build_labels.tokens``, imported by path), then reports the
median, the share below 0.9, the 20 lowest pages and the formulas the arm altered or lost.
It writes ``output/similarity_<arm>_vs_<baseline>.json``. A baseline page without text (P0 had
36) and an arm page without a file (timeout, not yet run) are counted and skipped.

``review_list`` is the page selection of DR-3. The review step (task 6.2) builds the review
page from its result in this file; the noise screen that supplies ``flagged`` is run there.

Run with any interpreter that has Python 3.11 or later; this file imports no third-party code.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import re
import statistics
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_ocr  # noqa: E402 - same folder; shared paths and page helpers

EXP33 = run_ocr.WORKTREE / "experiments/33-ocr-routing-natural-positive-2026-09-17"
EXP33_REL = "../33-ocr-routing-natural-positive-2026-09-17"
BUILD_LABELS_SHA256 = "4d9faa5437ee02d3de256a0fea156f9b02942e1798e2784a4f022497ac1ba2fa"
SEED = 41

# ruff: noqa: E501 - the pinned SHA-256 table below has lines longer than 100 characters

#: SHA-256 of every Experiment 37 and 33 input this experiment reads (OI-7), taken 2026-10-30.
#: A folder entry is the SHA-256 of ``<relative path>\0<file sha>\n`` lines for its files.
PINNED = {
    "sources.json": "d616b2de351d8e3307c5053f7760838c008d619a5866e1de1b7c29001b005df3",
    "maths_labels.json": "324ef438171c27ad388130691f4e9bbc0e29d69e320f38495732e99c5fc8ffbc",
    "noise_verdicts.json": "3f3a3cd2e4a6dc5766980e73a34501f9b055ffbbeb14772e6f99aa7575946634",
    "plan.json": "6c69907f3726841d0a1c7a9e28efbde4f32988a61596c7f6729f3dddae13ed63",
    "score_recall.py": "ee09cea51bfebce81205c42f9fd7227cdbc4d37ba467990fd2bb986c06d9e5e2",
    "check_katex.mjs": "3db2a9cf501ba4d6269720b88d990c766d2232f02db673d963c563ba5faae261",
    "output/ocr_state_dots-mocr.json": "6bafafaf4b2a3db4a250f68bfb09e5addbdf3c71a0725137c7bba3340ef8e597",
    "output/ocr_state_paddleocr-vl.json": "60f16801464cf96063f1cb07aafd044e5ec68fff69e35e6696a5abb8f76ec6c1",
    "output/katex_dots-mocr.json": "8cad66c56eb9e589f76ab33d6559ac6584aa03bde3821309af3b090bbcfb4a8d",
    "output/katex_paddleocr-vl.json": "19fdd1e704b7864cfad3ac605c75088d407951d28c7c191d9cb2cfe538a02d1d",
    "output/recall_dots-mocr.json": "8203fb88c5f117bb9925d32fafbc3d3456d44b9bd95e963d8df7570f24ef4e5a",
    "output/recall_paddleocr-vl.json": "5e2ad24929151a97e051c887b39bd3ac451e3b7c971b793fbf8ee33c2159d49f",
    "output/dots-mocr": "888575e61e7a4351d18628ebff48bdcd73a842410347dd2b151073f53b6aac4f",
    "output/paddleocr-vl": "9c0aebfc69c2576a52e41a79a1d9fe0ff782d9b436ab08dd483dea960af3f462",
    f"{EXP33_REL}/build_labels.py": "4d9faa5437ee02d3de256a0fea156f9b02942e1798e2784a4f022497ac1ba2fa",
    f"{EXP33_REL}/output/local_ocr/pages.json": "e6223d1536293b6860cd8eda9d48b2e383139e3e6c2f5e095a36f2b9822a711f",
    f"{EXP33_REL}/output/.transcripts": "ed9e0e184ef59dc6184d3f981cc9cc08ad221e199f062d6a59213bf47d8e3453",
    f"{EXP33_REL}/output/.transcripts_split": "2cc5f067a5df45247cfb627c67f640508a04c82c836c05bac2e76296b35b3e44",
}
DISPLAY = re.compile(r"\$\$([\s\S]*?)\$\$")
INLINE = re.compile(r"(?<![\\$])\$([^$\n]+?)\$(?!\$)")  # check_katex.mjs extract(), same rule


def check_pinned(names: Iterable[str]) -> dict[str, str]:
    """Return the SHA-256 of each named input; stop when one is missing or changed (OI-7)."""
    found: dict[str, str] = {}
    for name in names:
        path = run_ocr.EXP37 / name
        if path.is_dir():
            lines = (
                f"{p.relative_to(path).as_posix()}\0{run_ocr.sha256_file(p)}\n"
                for p in sorted(path.rglob("*"))
                if p.is_file()
            )
            digest = hashlib.sha256("".join(lines).encode()).hexdigest()
        elif path.is_file():
            digest = run_ocr.sha256_file(path)
        else:
            raise SystemExit(f"input is missing: {path}")
        if digest != PINNED[name]:
            raise SystemExit(f"{name} changed: expected {PINNED[name]}, found {digest}")
        found[name] = digest
    return found


def exp33_tokens() -> Any:
    """Import ``build_labels.tokens`` from the Experiment 33 folder of this worktree."""
    path = EXP33 / "build_labels.py"
    if run_ocr.sha256_file(path) != BUILD_LABELS_SHA256:
        raise SystemExit(
            "Experiment 33 build_labels.py changed: the tokeniser is not the frozen one"
        )
    spec = importlib.util.spec_from_file_location("exp33_build_labels", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.tokens


def dice(a: list[str], b: list[str]) -> float:
    """Return the multiset Dice coefficient of two token lists (1.0 when both are empty)."""
    if not a and not b:
        return 1.0
    return 2 * sum((Counter(a) & Counter(b)).values()) / (len(a) + len(b))


def formulas(text: str) -> Counter[str]:
    """Return the formulas of *text*, whitespace removed (display first, then inline)."""
    found = [re.sub(r"\s+", "", body) for body in DISPLAY.findall(text)]
    found += [re.sub(r"\s+", "", body) for body in INLINE.findall(DISPLAY.sub(" ", text))]
    return Counter(found)


def compare(arm: str, baseline: str) -> dict[str, Any]:
    """Score *arm* against *baseline* on the frozen page lists; return the result."""
    inputs = check_pinned(
        ["output/" + run_ocr.BASELINES[b] for b in (arm, baseline) if b in run_ocr.BASELINES]
    )
    tokens = exp33_tokens()
    keys = list(run_ocr.select_pages(run_ocr.page_lists(run_ocr.load_plan()), "all"))
    scores: dict[str, float] = {}
    lost: dict[str, dict[str, list[str]]] = {}
    skipped = {"arm_missing": 0, "baseline_missing": 0}
    base_formulas = missing = added = 0
    for key in keys:
        base_file, arm_file = run_ocr.page_path(baseline, key), run_ocr.page_path(arm, key)
        if not base_file.is_file():
            skipped["baseline_missing"] += 1
        elif not arm_file.is_file():
            skipped["arm_missing"] += 1
        else:
            base_text, arm_text = base_file.read_text("utf-8"), arm_file.read_text("utf-8")
            scores[key] = round(dice(tokens(arm_text), tokens(base_text)), 4)
            have, want = formulas(arm_text), formulas(base_text)
            gone, extra = want - have, have - want
            base_formulas += sum(want.values())
            missing, added = missing + sum(gone.values()), added + sum(extra.values())
            if gone or extra:
                lost[key] = {
                    "missing": [f[:200] for f in gone.elements()],
                    "added": [f[:200] for f in extra.elements()],
                }
    values = list(scores.values())
    ranked = sorted(scores.items(), key=lambda item: (item[1], item[0]))
    return {
        "arm": arm,
        "baseline": baseline,
        "tokeniser": "experiments/33-ocr-routing-natural-positive-2026-09-17/build_labels.py tokens()",
        "inputs_sha256": inputs,
        "pages_compared": len(values),
        **skipped,
        "dice": {
            "median": round(statistics.median(values), 4) if values else None,
            "mean": round(statistics.fmean(values), 4) if values else None,
            "share_below_0_9": round(sum(v < 0.9 for v in values) / len(values), 4)
            if values
            else None,
        },
        "lowest_20": [{"page": k, "dice": v} for k, v in ranked[:20]],
        "formulas": {
            "baseline_total": base_formulas,
            "missing_from_arm": missing,
            "added_by_arm": added,
            "pages_with_difference": lost,
        },
        "pages": scores,
    }


def review_list(
    dice_by_page: dict[str, float],
    flagged: Iterable[str],
    *,
    lowest: int = 10,
    random_pages: int = 5,
    seed: int = SEED,
) -> dict[str, list[str]]:
    """Select the pages the operator reviews (DR-3); return ``{page: reasons}``.

    The pages are the *lowest* pages by Dice, every page the noise screen *flagged*, and
    *random_pages* more drawn with *seed* from the pages not yet chosen.
    """
    chosen: dict[str, list[str]] = {}
    for key in sorted(dice_by_page, key=lambda k: (dice_by_page[k], k))[:lowest]:
        chosen.setdefault(key, []).append("lowest_similarity")
    for key in sorted(set(flagged)):
        chosen.setdefault(key, []).append("noise_screen")
    rest = sorted(set(dice_by_page) - chosen.keys())
    for key in random.Random(seed).sample(rest, min(random_pages, len(rest))):  # noqa: S311 - seeded sample
        chosen.setdefault(key, []).append("random")
    return chosen


def main() -> int:
    """Write the similarity file for one arm."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--arm", required=True, choices=sorted(run_ocr.ARMS) + sorted(run_ocr.BASELINES)
    )
    parser.add_argument("--baseline", choices=sorted(run_ocr.ARMS) + sorted(run_ocr.BASELINES))
    args = parser.parse_args()
    engine = run_ocr.BASELINES.get(args.arm) or run_ocr.ARMS[args.arm][0]
    baseline = args.baseline or {v: k for k, v in run_ocr.BASELINES.items()}[engine]
    result = compare(args.arm, baseline)
    target = run_ocr.OUT / f"similarity_{args.arm}_vs_{baseline}.json"
    run_ocr.write_atomic(target, json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    print(f"{args.arm} vs {baseline}: {result['pages_compared']} pages, Dice {result['dice']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
