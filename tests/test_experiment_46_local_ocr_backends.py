"""Fast tests for the pure parts of Experiment 46 (local OCR backends).

No OCR engine, model, download or network is used. The tests cover the rules that
the plan fixes before any run: the seeded Latin sample, the character-weighted page
confidence, the leave-one-document-out cut, each gate at its boundary value, and the
rule that a page with no output scores 0.

The scripts sit in the experiment folder. The tests load them by path, as the other
experiment tests do. A mutation that moves a gate threshold must fail at least one test.
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FOLDER = _REPO_ROOT / "experiments" / "46-local-ocr-backends-2026-11-04"


def _load(name: str) -> ModuleType:
    if str(_FOLDER) not in sys.path:
        sys.path.insert(0, str(_FOLDER))
    spec = importlib.util.spec_from_file_location(f"exp46_{name}", _FOLDER / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"exp46_{name}"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def run_arm() -> ModuleType:
    return _load("run_arm")


@pytest.fixture(scope="module")
def summarise() -> ModuleType:
    return _load("summarise")


@pytest.fixture(scope="module")
def plan() -> dict:
    return json.loads((_FOLDER / "plan.json").read_text(encoding="utf-8"))


# --- the Latin sample --------------------------------------------------------------


def _pools() -> dict[str, list[int]]:
    """Eligible pages per document, sized like the stored Experiment 33 rows."""
    return {
        "io04": list(range(1, 53)),
        "io05": list(range(1, 8)),
        "io06": list(range(1, 68)),
        "rf06": list(range(1, 45)),
        "rf07": list(range(1, 19)),
    }


def _count(sample: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for page in sample:
        counts[page["stratum"]] = counts.get(page["stratum"], 0) + 1
    return counts


def test_sample_draws_30_35_35_pages(run_arm: ModuleType) -> None:
    sample = run_arm.draw_latin_sample(_pools(), seed=46)
    assert _count(sample) == {"print": 30, "old_print": 35, "handwriting": 35}
    keys = {(p["doc"], p["page"]) for p in sample}
    assert len(keys) == 100


def test_sample_is_the_same_on_a_second_call_and_ignores_input_order(
    run_arm: ModuleType,
) -> None:
    first = run_arm.draw_latin_sample(_pools(), seed=46)
    shuffler = random.Random(1)  # noqa: S311  (reordering test data, not a secret)
    shuffled = {doc: shuffler.sample(pages, len(pages)) for doc, pages in _pools().items()}
    assert run_arm.draw_latin_sample(_pools(), seed=46) == first
    assert run_arm.draw_latin_sample(shuffled, seed=46) == first


def test_sample_changes_with_the_seed_and_keeps_to_each_strata_documents(
    run_arm: ModuleType,
) -> None:
    assert run_arm.draw_latin_sample(_pools(), seed=47) != run_arm.draw_latin_sample(
        _pools(), seed=46
    )
    docs = {"print": {"io04", "io05"}, "old_print": {"io06"}, "handwriting": {"rf06", "rf07"}}
    for page in run_arm.draw_latin_sample(_pools(), seed=46):
        assert page["doc"] in docs[page["stratum"]]


def test_sample_stops_when_a_stratum_has_too_few_pages(run_arm: ModuleType) -> None:
    pools = _pools()
    pools["io06"] = list(range(1, 35))  # 34 pages for a draw of 35
    with pytest.raises(run_arm.Stop):
        run_arm.draw_latin_sample(pools, seed=46)


# --- page recall and page confidence -------------------------------------------------


def test_a_page_with_no_output_scores_zero(run_arm: ModuleType) -> None:
    reference = ["alpha", "beta"]
    assert run_arm.page_recall(None, reference) == 0.0
    assert run_arm.page_recall("", reference) == 0.0
    assert run_arm.page_recall("   \n", reference) == 0.0


def test_page_recall_is_multiset_token_recall(run_arm: ModuleType) -> None:
    reference = ["alpha", "beta", "alpha", "gamma"]
    assert run_arm.page_recall("alpha beta alpha gamma", reference) == 1.0
    assert run_arm.page_recall("alpha beta", reference) == 0.5
    assert run_arm.page_recall("ALPHA, beta! alpha", reference) == 0.75


def test_page_confidence_is_weighted_by_characters(run_arm: ModuleType) -> None:
    lines = [("aaaa", 0.5), ("bb", 1.0)]
    assert run_arm.page_confidence(lines) == pytest.approx(4 / 6)
    assert run_arm.page_confidence([("a b", 0.9)]) == pytest.approx(0.9)  # spaces do not count


def test_page_confidence_is_none_without_characters(run_arm: ModuleType) -> None:
    assert run_arm.page_confidence([]) is None
    assert run_arm.page_confidence([("  ", 0.9)]) is None


def test_exploratory_confidence_alternatives(run_arm: ModuleType) -> None:
    lines = [("a" * 12, 0.6), ("b" * 8, 0.2), ("c" * 10, 0.95)]
    assert run_arm.min_confidence_long_lines(lines) == pytest.approx(0.6)  # 10+ characters
    assert run_arm.min_confidence_long_lines([("short", 0.1)]) is None
    assert run_arm.share_confident_characters(lines) == pytest.approx(10 / 30)  # 0.8 or above


def test_stop_rule_needs_20_timed_pages_and_a_median_above_15_seconds(
    run_arm: ModuleType,
) -> None:
    assert run_arm.should_stop([16.0] * 19) is False  # fewer than 20 timed pages
    assert run_arm.should_stop([16.0] * 20) is True
    assert run_arm.should_stop([15.0] * 20) is False  # 15.0 is not above 15 s
    assert run_arm.should_stop([1.0] * 11 + [99.0] * 9) is False  # median 1.0
    assert run_arm.should_stop([99.0] * 11 + [1.0] * 9) is True  # median 99.0
    assert run_arm.should_stop([1.0] * 20 + [99.0] * 30) is False  # only the first 20 count


# --- the leave-one-document-out cut ---------------------------------------------------


def _row(doc: str, conf: float | None, rec: float, script: str = "x") -> dict:
    return {"doc": doc, "conf": conf, "recall": rec, "script": script}


def test_cut_grid_is_the_planned_one(summarise: ModuleType) -> None:
    assert summarise.CUT_GRID[0] == 0.50
    assert summarise.CUT_GRID[-1] == 0.99
    assert summarise.CUT_GRID[:-1] == pytest.approx([0.50 + 0.05 * i for i in range(10)])


def test_cut_is_the_lowest_one_that_keeps_bad_pages_at_or_under_five_percent(
    summarise: ModuleType,
) -> None:
    # 18 good pages at 0.90 and two bad pages at 0.62 and 0.67. Cut 0.50 to 0.60 keep
    # both bad pages (2 of 20). Cut 0.65 keeps one (1 of 19 is 0.0526, too high).
    # Cut 0.70 keeps none, so it is the lowest cut that qualifies.
    rows = [_row("a", 0.90, 0.9) for _ in range(18)]
    rows += [_row("a", 0.62, 0.1), _row("a", 0.67, 0.1)]
    assert summarise.choose_cut(rows) == 0.70


def test_cut_rule_boundary_is_at_most_five_percent(summarise: ModuleType) -> None:
    good = [_row("a", 0.90, 0.9) for _ in range(19)]
    bad = [_row("a", 0.90, 0.1)]
    assert summarise.choose_cut(good + bad) == 0.50  # 1 bad of 20 kept: 0.05 passes
    two_bad = good[:18] + [_row("a", 0.90, 0.1), _row("a", 0.90, 0.1)]
    assert summarise.choose_cut(two_bad) is None  # 2 bad of 20 kept: 0.10 never qualifies


def test_cut_needs_at_least_one_kept_page(summarise: ModuleType) -> None:
    assert summarise.choose_cut([_row("a", 0.30, 0.9)]) is None
    assert summarise.choose_cut([]) is None
    assert summarise.choose_cut([_row("a", None, 0.9)]) is None  # no confidence, never kept


def test_a_fold_with_no_qualifying_cut_keeps_no_page(summarise: ModuleType) -> None:
    rows = [_row("a", 0.9, 0.9), _row("b", 0.9, 0.9), _row("c", 0.95, 0.1)]
    result = summarise.leave_one_document_out(rows)
    by_doc = {r["doc"]: r for r in result["rows"]}
    # Held out c: a and b are all good, so the cut is 0.50 and c's bad page is kept.
    assert result["cuts"]["c"] == 0.50
    assert by_doc["c"]["kept"] is True
    # Held out a: b is good, c is bad at the same confidence. No cut qualifies.
    assert result["cuts"]["a"] is None
    assert by_doc["a"]["kept"] is False
    assert by_doc["b"]["kept"] is False


def test_the_registered_cut_is_the_median_of_the_chosen_cuts_rounded_to_0_05(
    summarise: ModuleType,
) -> None:
    assert summarise.registered_cut([0.50, 0.60, 0.80]) == 0.60
    assert summarise.registered_cut([0.55, 0.60]) == 0.60  # median 0.575 rounds to 0.60
    assert summarise.registered_cut([0.50, None, 0.70]) == 0.60  # None is not a chosen cut
    assert summarise.registered_cut([None, None]) is None


# --- the gates at their boundary values -----------------------------------------------


def test_the_gate_thresholds_are_the_pre_registered_ones(summarise: ModuleType, plan: dict) -> None:
    thresholds = summarise.thresholds_from_plan(plan)
    assert thresholds == {
        "G1": 0.70,
        "G2a": 0.60,
        "G2b": 0.05,
        "G2c": 0.30,
        "G3a": -0.02,
        "G3b": -0.05,
        "G4": 5.0,
    }


@pytest.fixture()
def thresholds(summarise: ModuleType, plan: dict) -> dict[str, float]:
    return summarise.thresholds_from_plan(plan)


@pytest.mark.parametrize(
    ("median", "passes"), [(0.70, True), (0.6999, False), (0.95, True), (0.0, False)]
)
def test_g1_median_recall_boundary(
    summarise: ModuleType, thresholds: dict, median: float, passes: bool
) -> None:
    assert summarise.gate_g1([median] * 5, thresholds) is passes


def test_g1_uses_the_median_not_the_mean(summarise: ModuleType, thresholds: dict) -> None:
    assert summarise.gate_g1([0.0, 0.7, 1.0], thresholds) is True
    assert summarise.gate_g1([0.0, 0.0, 1.0], thresholds) is False


def _kept_table(good_kept: int, good_total: int, bad_kept: int, other_kept: int, total: int):
    """Rows for G2: good pages (recall 0.9), bad pages (0.1) and middle pages (0.6)."""
    rows = []
    for i in range(good_total):
        rows.append({"recall": 0.9, "kept": i < good_kept})
    rows += [{"recall": 0.1, "kept": True} for _ in range(bad_kept)]
    middle = total - good_total - bad_kept
    rows += [{"recall": 0.6, "kept": i < other_kept} for i in range(middle)]
    return rows


def test_g2_good_pages_kept_boundary_is_0_60(summarise: ModuleType, thresholds: dict) -> None:
    # 10 good pages, 6 kept = 0.60 passes; 5 kept = 0.50 fails. Other gates are met.
    ok = summarise.gate_g2(_kept_table(6, 10, 0, 0, 10), thresholds)
    assert ok["G2a"] is True
    assert summarise.gate_g2(_kept_table(5, 10, 0, 0, 10), thresholds)["G2a"] is False


def test_g2_kept_bad_share_boundary_is_0_05(summarise: ModuleType, thresholds: dict) -> None:
    # 19 good kept and 1 bad kept: 1 of 20 is 0.05, which passes. 2 of 21 is above it.
    assert summarise.gate_g2(_kept_table(19, 19, 1, 0, 20), thresholds)["G2b"] is True
    assert summarise.gate_g2(_kept_table(19, 19, 2, 0, 21), thresholds)["G2b"] is False


def test_g2_all_pages_kept_boundary_is_0_30(summarise: ModuleType, thresholds: dict) -> None:
    # 10 pages, 3 kept = 0.30 passes; 2 kept = 0.20 fails.
    assert summarise.gate_g2(_kept_table(3, 3, 0, 0, 10), thresholds)["G2c"] is True
    assert summarise.gate_g2(_kept_table(2, 3, 0, 0, 10), thresholds)["G2c"] is False


def test_g2_fails_when_nothing_is_kept_or_there_is_no_good_page(
    summarise: ModuleType, thresholds: dict
) -> None:
    nothing = summarise.gate_g2([{"recall": 0.9, "kept": False}] * 4, thresholds)
    assert nothing == {"G2a": False, "G2b": False, "G2c": False}
    no_good = summarise.gate_g2([{"recall": 0.6, "kept": True}] * 4, thresholds)
    assert no_good["G2a"] is False


@pytest.mark.parametrize(
    ("difference", "passes"),
    [(-0.02, True), (-0.0201, False), (0.0, True), (-0.5, False)],
)
def test_g3a_overall_latin_difference_boundary(
    summarise: ModuleType, thresholds: dict, difference: float, passes: bool
) -> None:
    rows = [{"stratum": "print", "diff": difference}] * 3
    assert summarise.gate_g3(rows, thresholds)["G3a"] is passes


@pytest.mark.parametrize(
    ("stratum_median", "passes"), [(-0.05, True), (-0.0501, False), (0.0, True)]
)
def test_g3b_lowest_stratum_boundary(
    summarise: ModuleType, thresholds: dict, stratum_median: float, passes: bool
) -> None:
    rows = [{"stratum": "print", "diff": 0.1}] * 5 + [
        {"stratum": "handwriting", "diff": stratum_median}
    ] * 5
    assert summarise.gate_g3(rows, thresholds)["G3b"] is passes


@pytest.mark.parametrize(
    ("median", "passes"), [(5.0, True), (5.01, False), (0.7, True), (37.0, False)]
)
def test_g4_median_seconds_boundary(
    summarise: ModuleType, thresholds: dict, median: float, passes: bool
) -> None:
    assert summarise.gate_g4([median] * 5, thresholds) is passes


def test_g4_excludes_the_three_warm_up_pages(summarise: ModuleType) -> None:
    rows = [{"seconds": 90.0, "timed": False}] * 3 + [{"seconds": 1.0, "timed": True}] * 4
    assert summarise.timed_seconds(rows) == [1.0] * 4


# --- the outcome ------------------------------------------------------------------------


def _verdict(g1: bool, g2: bool, g3: bool, g4: bool) -> dict:
    return {"G1": g1, "G2": g2, "G3": g3, "G4": g4}


def test_outcome_pass_when_one_arm_script_holds_all_four(summarise: ModuleType) -> None:
    table = {"B": {"arabic": _verdict(True, True, True, True)}}
    assert summarise.decide(table) == "PASS"


def test_outcome_inconclusive_when_only_g3_fails(summarise: ModuleType) -> None:
    table = {"B": {"arabic": _verdict(True, True, False, True)}}
    assert summarise.decide(table) == "INCONCLUSIVE"


@pytest.mark.parametrize("failing", ["G1", "G2", "G4"])
def test_outcome_fail_when_g1_g2_or_g4_fail_everywhere(summarise: ModuleType, failing: str) -> None:
    verdict = _verdict(True, True, True, True) | {failing: False}
    assert summarise.decide({"B": {"arabic": verdict}, "D": {"devanagari": verdict}}) == "FAIL"


def test_outcome_pass_wins_over_inconclusive(summarise: ModuleType) -> None:
    table = {
        "B": {"arabic": _verdict(True, True, False, True)},
        "D": {"devanagari": _verdict(True, True, True, True)},
    }
    assert summarise.decide(table) == "PASS"


# --- the confidence AUC (H2, secondary) ---------------------------------------------------


def test_auc_ranks_good_pages_above_bad_pages(summarise: ModuleType) -> None:
    assert summarise.auc([0.9, 0.8, 0.2, 0.1], [True, True, False, False]) == 1.0
    assert summarise.auc([0.1, 0.2, 0.8, 0.9], [True, True, False, False]) == 0.0
    assert summarise.auc([0.5, 0.5], [True, False]) == 0.5  # a tie counts half
    assert summarise.auc([0.5, 0.6], [True, True]) is None  # one class only
