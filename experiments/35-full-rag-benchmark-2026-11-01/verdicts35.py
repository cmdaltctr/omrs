"""Hypothesis verdict rules of Experiment 35 (pre-registration section 7).

Moved out of ``factorial35.py`` unchanged, so that file stays under 500 lines.
The input is, per dataset and contrast row, the sign of a counted row (+1 or
-1), else 0.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import select35

FB, FS, BQ = select35.CORE


def _two_of_three(counted: Mapping[str, Mapping[int, int]], row: int) -> bool:
    return sum(counted.get(d, {}).get(row, 0) > 0 for d in select35.CORE) >= 2


def _both(counted: Mapping[str, Mapping[int, int]], rows: Sequence[int]) -> dict[str, Any]:
    fb, fs = counted.get(FB, {}), counted.get(FS, {})
    holding = [r for r in rows if fb.get(r, 0) != 0 and fb.get(r) == fs.get(r)]
    signs = {fb[r] for r in holding}
    return {
        "holds": bool(holding),
        "rows": holding,
        "sign": signs.pop() if len(signs) == 1 else 0,
        "dataset_dependent": [r for r in rows if fb.get(r, 0) * fs.get(r, 0) < 0],
    }


def verdicts(counted: Mapping[str, Mapping[int, int]]) -> dict[str, Any]:
    """Apply the per-hypothesis rules of section 7.

    Args:
        counted: Per dataset and row, the sign of a counted row (+1 or -1), else 0.

    Returns:
        The verdict of each hypothesis.
    """

    def steps(rows: Sequence[int]) -> dict[str, Any]:
        held = {r: _two_of_three(counted, r) for r in rows}
        n = sum(held.values())
        return {"holds": "full" if n == len(rows) else "part" if n else "no", "steps": held}

    per_dataset = {
        d: counted.get(d, {}).get(5, 0) > 0 and counted.get(d, {}).get(6, 0) > 0
        for d in select35.CORE
    }
    return {
        "H1": steps((1, 2)),
        "H2": {"holds": _two_of_three(counted, 3)},
        "H3": {"holds": _two_of_three(counted, 4)},
        "H4": {"holds": sum(per_dataset.values()) >= 2, "per_dataset": per_dataset},
        "H5": steps((7, 8)),
        "H6": _both(counted, (9, 10)),
        "H7": {"holds": counted.get(FB, {}).get(11, 0) > 0 and counted.get(FS, {}).get(11, 0) > 0},
        "H8a": {"faithfulness": _both(counted, (12, 13)), "correctness": _both(counted, (14, 15))},
        "H8b": {"faithfulness": _both(counted, (16, 17)), "correctness": _both(counted, (18, 19))},
    }
