"""Tests for ``experiments/_lib/stats_d6.py`` (Experiment 35, task 2.5).

The module holds an unchanged copy of the design D6 functions from the
s-experiment skill reference ``stats.py``. The pinned values below were
computed on 2026-11-10 by loading that skill file and calling each function
once on the inputs in this file. Floats are compared with ``pytest.approx``;
integers, dicts and counts are compared exactly.
"""

from __future__ import annotations

import ast
import importlib.util
import math
from pathlib import Path

import pytest
from experiments._lib import stats as lib_stats
from experiments._lib import stats_d6
from experiments._lib.stats_d6 import (
    holm,
    mcnemar_exact,
    min_detectable_effect,
    paired_bootstrap,
    paired_permutation,
    wilson,
    win_loss,
)

SKILL_STATS = Path.home() / ".agents/skills/s-experiment/references/stats.py"

# Continuous scores for a baseline (A) and a candidate (B) on eight questions.
A = [0.2, 0.5, 0.5, 0.7, 0.9, 0.1, 0.4, 0.6]
B = [0.3, 0.5, 0.4, 0.9, 1.0, 0.3, 0.4, 0.8]
GROUPS = ["x", "x", "y", "y", "z", "z", "w", "w"]

# Hit or miss outcomes on ten questions.
HIT_A = [True, False, False, True, False, False, True, False, False, False]
HIT_B = [True, True, True, True, False, True, True, False, True, False]

COPIED = [
    "wilson",
    "win_loss",
    "mcnemar_exact",
    "paired_permutation",
    "paired_bootstrap",
    "holm",
    "min_detectable_effect",
    "_check_paired",
]


def test_wilson_matches_reference() -> None:
    low, high = wilson(7, 20)
    assert low == pytest.approx(0.18119182410108212)
    assert high == pytest.approx(0.5671457233147637)


def test_wilson_empty_sample_is_full_range() -> None:
    assert wilson(0, 0) == (0.0, 1.0)


def test_win_loss_matches_reference() -> None:
    assert win_loss(A, B) == {"wins": 5, "losses": 1, "ties": 2}


def test_mcnemar_exact_matches_reference() -> None:
    assert mcnemar_exact(HIT_A, HIT_B) == pytest.approx(0.125)
    assert mcnemar_exact(HIT_A, HIT_B, one_sided=True) == pytest.approx(0.0625)


def test_paired_permutation_matches_reference() -> None:
    p = paired_permutation(A, B, n_perm=2000, seed=7)
    assert p == pytest.approx(0.12493753123438281)


def test_paired_bootstrap_matches_reference() -> None:
    mean, low, high = paired_bootstrap(A, B, n_boot=2000, seed=7)
    assert mean == pytest.approx(0.0875)
    assert low == pytest.approx(0.0125)
    assert high == pytest.approx(0.1625)


def test_paired_bootstrap_grouped_matches_reference() -> None:
    mean, low, high = paired_bootstrap(A, B, groups=GROUPS, n_boot=2000, seed=7)
    assert mean == pytest.approx(0.0875)
    assert low == pytest.approx(0.05)
    assert high == pytest.approx(0.125)


def test_holm_matches_reference() -> None:
    assert holm([0.01, 0.04, 0.03, 0.5]) == pytest.approx([0.04, 0.09, 0.09, 0.5])


def test_min_detectable_effect_matches_reference() -> None:
    assert min_detectable_effect(0.15, 223) == pytest.approx(0.028141203376130637)
    assert min_detectable_effect(0.15, 0) == math.inf


def test_unequal_lengths_raise() -> None:
    with pytest.raises(ValueError, match="same length"):
        win_loss([0.1, 0.2], [0.1])


def test_existing_lib_functions_are_reexported() -> None:
    assert stats_d6.paired_bootstrap_ci is lib_stats.paired_bootstrap_ci
    assert stats_d6.cell_record is lib_stats.cell_record


@pytest.mark.skipif(not SKILL_STATS.exists(), reason="s-experiment skill file absent (CI)")
def test_copy_is_identical_to_skill_source() -> None:
    """Each copied function has the same source text as the skill original."""
    original_src = SKILL_STATS.read_text(encoding="utf-8")
    copy_path = Path(stats_d6.__file__)
    copy_src = copy_path.read_text(encoding="utf-8")

    def sources(text: str) -> dict[str, str]:
        tree = ast.parse(text)
        return {
            node.name: ast.get_source_segment(text, node) or ""
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }

    original = sources(original_src)
    copied = sources(copy_src)
    for name in COPIED:
        assert name in original, f"{name} missing from skill file"
        assert copied.get(name) == original[name], f"{name} differs from the skill source"


@pytest.mark.skipif(not SKILL_STATS.exists(), reason="s-experiment skill file absent (CI)")
def test_copy_gives_same_results_as_skill_module() -> None:
    """Run both modules on the same input; the outputs match."""
    spec = importlib.util.spec_from_file_location("skill_stats_ref", SKILL_STATS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.paired_permutation(A, B, n_perm=500, seed=3) == paired_permutation(
        A, B, n_perm=500, seed=3
    )
    assert module.holm([0.01, 0.2]) == holm([0.01, 0.2])
