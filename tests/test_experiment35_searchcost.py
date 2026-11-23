"""Search-cost figure data of Experiment 35 (readiness task 14.4; pre-registration section 14.3).

One expected-maximum curve over the 12 A3 cells, one over the 72 setups, both
from pooled half-A nDCG@10, and a RAGFlow curve only when its matched search ran.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load

select35 = load("select35")
searchcost35 = load("searchcost35")

QIDS = [f"q{i}" for i in range(4)]
HALVES = {d: {q: "AB"[i % 2] for i, q in enumerate(QIDS)} for d in (*select35.CORE, "legal")}


def _value(index: int, dataset: str) -> float:
    return 0.2 + index / 200 + {"financebench": 0.0, "freshstack": 0.01, "bioasq": 0.02}[dataset]


def _records(setups: list[str], *, half_b: float = 9.0, legal: float = 9.0) -> list[dict]:
    rows = []
    for k, setup in enumerate(setups):
        for dataset in (*select35.CORE, "legal"):
            for qid in QIDS:
                if dataset == "legal":
                    value = legal
                elif HALVES[dataset][qid] == "B":
                    value = half_b
                else:
                    value = _value(k, dataset)
                rows.append({"dataset": dataset, "setup": setup, "qid": qid, "ndcg_at_10": value})
    return rows


def _selection(records: list[dict]) -> dict[str, Any]:
    chunks = {
        select35.parse_setup(s).index: dict.fromkeys(select35.CORE, 10)
        for s in select35.SEARCH_SETUPS
    }
    return select35.select(records, HALVES, chunks, {"0.6b": 1024, "4b": 2560, "8b": 4096})


def _pooled(k: int) -> float:
    return sum(_value(k, d) for d in select35.CORE) / 3


def test_two_curves_from_pooled_half_a_scores() -> None:
    setups = list(select35.SEARCH_SETUPS)
    records = _records(setups)
    selection = _selection(records)
    data = searchcost35.search_cost(records, HALVES, selection)
    every = data["all_setups"]
    assert every["n"] == list(range(1, 73))
    assert every["expected_max"] == pytest.approx(
        select35.expected_max_curve([_pooled(k) for k in range(72)])
    )
    assert every["expected_max"][-1] == pytest.approx(max(_pooled(k) for k in range(72)))
    cells = data["a3_cells"]
    assert sorted(cells["setups"]) == sorted(selection["cell_scores"])
    assert cells["n"] == list(range(1, 13))
    want = [_pooled(setups.index(s)) for s in selection["cell_scores"]]
    assert cells["expected_max"] == pytest.approx(select35.expected_max_curve(want))
    # Half-B and Legal scores of 9.0 never enter: every value stays below 1.
    assert max(every["expected_max"]) < 1.0


def test_no_ragflow_curve_unless_its_matched_search_ran() -> None:
    records = _records(list(select35.SEARCH_SETUPS))
    data = searchcost35.search_cost(records, HALVES, _selection(records))
    assert data["ragflow"] is None
    assert "did not run" in data["ragflow_note"]


def test_ragflow_curve_over_its_own_half_a_cells() -> None:
    records = _records(list(select35.SEARCH_SETUPS))
    flow = _records(["rf-a", "rf-b", "rf-c"])
    data = searchcost35.search_cost(records, HALVES, _selection(records), ragflow_records=flow)
    curve = data["ragflow"]
    assert curve["setups"] == ["rf-a", "rf-b", "rf-c"]
    assert curve["expected_max"] == pytest.approx(
        select35.expected_max_curve([_pooled(k) for k in range(3)])
    )


def test_a_ragflow_cell_lacking_a_half_a_score_is_refused() -> None:
    records = _records(list(select35.SEARCH_SETUPS))
    flow = [r for r in _records(["rf-a"]) if not (r["qid"] == "q0" and r["dataset"] == "bioasq")]
    with pytest.raises(select35.SelectionError, match="rf-a on bioasq"):
        searchcost35.search_cost(records, HALVES, _selection(records), ragflow_records=flow)


def test_explicit_ragflow_input_with_no_half_a_scores_is_refused() -> None:
    records = _records(list(select35.SEARCH_SETUPS))
    with pytest.raises(select35.SelectionError, match="RAGFlow"):
        searchcost35.search_cost(records, HALVES, _selection(records), ragflow_records=[])


def test_a_selection_without_12_cells_is_refused() -> None:
    records = _records(list(select35.SEARCH_SETUPS))
    selection = _selection(records)
    selection["cell_scores"] = dict(list(selection["cell_scores"].items())[:11])
    with pytest.raises(select35.SelectionError, match="12"):
        searchcost35.search_cost(records, HALVES, selection)


def test_main_writes_the_figure_data_from_saved_half_a_files(tmp_path: Path) -> None:
    records = _records(list(select35.SEARCH_SETUPS))
    for dataset in select35.CORE:
        folder = tmp_path / "scores" / "A" / dataset
        folder.mkdir(parents=True)
        for setup in select35.SEARCH_SETUPS:
            rows = [r for r in records if r["dataset"] == dataset and r["setup"] == setup]
            (folder / f"{setup}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (tmp_path / "selection.json").write_text(json.dumps(_selection(records)))
    halves = tmp_path / "halves.json"
    halves.write_text(json.dumps({"halves": HALVES}))
    assert searchcost35.main(["--out-dir", str(tmp_path), "--halves", str(halves)]) == 0
    saved = json.loads((tmp_path / "search-cost.json").read_text())
    assert len(saved["all_setups"]["expected_max"]) == 72 and saved["ragflow"] is None
