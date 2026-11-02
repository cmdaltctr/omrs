"""Fixed-table tests for the routing and page metrics (task 3.4)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analysis  # noqa: E402


def docs() -> list[dict]:
    """rf06 (40 pages), rf07 (20), u6 usable (6), big usable (30), prior usable (5), plain (4)."""
    rows = [("rf06", 40, True, False), ("rf07", 20, True, False), ("u6", 6, True, False),
            ("big", 30, True, False), ("prior", 5, True, True), ("plain", 4, False, False)]  # fmt: skip
    return [
        {"doc_id": d, "page_count": n, "extraction_fallback_backend": "liteparse" if r else None,
         "ocr_required": p}  # fmt: skip
        for d, n, r, p in rows
    ]


LABELS = {"rf06": "needs_ocr", "rf07": "needs_ocr", "u6": "usable", "big": "usable",
          "prior": "usable", "plain": "usable"}  # fmt: skip


def all_pages() -> set:
    return {(d["doc_id"], p) for d in docs() for p in range(1, d["page_count"] + 1)}


def scores() -> dict:
    """rf06: 4 low pages (10%); rf07: 1 low page (5%); u6: 1 low; big: 2 low; plain: 4 low."""
    values = {key: 0.9 for key in all_pages()}
    low = [("rf06", 1), ("rf06", 2), ("rf06", 3), ("rf06", 4), ("rf07", 1), ("u6", 3),
           ("big", 1), ("big", 2), ("plain", 1), ("plain", 2), ("plain", 3), ("plain", 4)]  # fmt: skip
    values.update({key: 0.1 for key in low})
    values[("big", 3)] = 0.5  # equal to the threshold: not flagged (strict rule)
    return values


def test_flags_are_strictly_below_threshold() -> None:
    flags = analysis.flagged(scores(), 0.5)
    assert ("big", 3) not in flags
    assert len(flags) == 12
    assert analysis.flagged(scores(), None) == set()


def test_ten_percent_rule_routes_known_documents() -> None:
    routing = analysis.route(docs(), LABELS, analysis.flagged(scores(), 0.5), all_pages(), "ten_percent")
    assert routing["rf06"]["routed"] is True  # 4/40 = 10%
    assert routing["rf07"]["routed"] is False  # 1/20 = 5%
    assert routing["u6"]["routed"] is True  # 1/6
    assert routing["big"]["routed"] is False  # 2/30
    assert routing["plain"]["flagged_pages"] == 0  # not rescued: the check never sees it
    assert routing["prior"]["routed"] and not routing["prior"]["newly_routed_usable"]
    verdict = analysis.pass_rule(routing)
    assert verdict["part_1_rf06_rf07_routed"] is False
    assert verdict["usable_newly_routed"] == ["u6"]
    assert verdict["ocr_cost_pages"] == 6
    assert verdict["ocr_cost_seconds"] == round(6 * 38.2, 1)
    assert verdict["pass"] is False


def test_one_page_rule_routes_short_document_with_one_flag() -> None:
    routing = analysis.route(docs(), LABELS, analysis.flagged(scores(), 0.5), all_pages(), "one_page")
    assert routing["rf07"]["routed"] and routing["u6"]["routed"] and routing["big"]["routed"]
    verdict = analysis.pass_rule(routing)
    assert verdict["usable_newly_routed"] == ["big", "u6"]
    assert verdict["ocr_cost_pages"] == 36


def test_population_limits_which_pages_count() -> None:
    flags = analysis.flagged(scores(), 0.5)
    population = all_pages() - {("u6", 3)}
    routing = analysis.route(docs(), LABELS, flags, population, "ten_percent")
    assert routing["u6"]["routed"] is False


def test_pass_rule_passes_when_both_parts_hold() -> None:
    values = scores()
    values[("u6", 3)] = 0.9
    values[("rf07", 2)] = 0.1
    routing = analysis.route(docs(), LABELS, analysis.flagged(values, 0.5), all_pages(), "ten_percent")
    assert analysis.pass_rule(routing)["pass"] is True
    values[("u6", 3)] = 0.1
    routing = analysis.route(docs(), LABELS, analysis.flagged(values, 0.5), all_pages(), "ten_percent")
    verdict = analysis.pass_rule(routing)
    assert verdict["part_1_rf06_rf07_routed"] is True
    assert verdict["pass"] is False


def test_page_metrics_count_known_values() -> None:
    classes = {("rf06", 1): "junk", ("rf06", 2): "junk", ("mx01", 1): "junk",
               ("bd01", 1): "healthy", ("bd01", 2): "healthy", ("bd01", 3): "grey"}  # fmt: skip
    flags = {("rf06", 1), ("mx01", 1), ("bd01", 2), ("bd01", 3)}
    m = analysis.page_metrics(classes, flags, set(classes) - {("rf06", 2)})
    assert (m["junk_pages"], m["junk_caught"]) == (3, 2)
    assert (m["junk_rf06_rf07_pages"], m["junk_rf06_rf07_caught"]) == (2, 1)
    assert (m["healthy_pages"], m["healthy_flagged"]) == (2, 1)
    assert m["junk_unscored"] == 1


def test_fit_threshold_uses_equal_cost_rule() -> None:
    rows = [{"doc_id": "bd01", "page": i, "phase": "fit", "p_yes": i / 561} for i in range(561)]
    # floor(0.02 x 561) = 11, so the threshold is the 12th lowest value and 11 pages flag.
    value = analysis.fit_threshold(rows)
    assert value == 11 / 561
    assert sum(r["p_yes"] < value for r in rows) == 11
