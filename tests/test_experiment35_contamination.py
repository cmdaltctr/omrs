"""Contamination sensitivity of Experiment 35 (readiness task 15.4; pre-registration section 13).

Rows 14, 15, 18 and 19 run again on the questions that both closed-book runs
answer wrongly (Ragas correctness below 0.5). When drop step 3 removed the
RAG-prompt run, the subset uses the own-knowledge run alone and says so.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load, open_half_b

select35 = load("select35")
contamination35 = load("contamination35")
scoring35 = load("scoring35")

DATASETS = ("financebench", "freshstack")
N = 12
STEP = {512: 0, 1024: 1, 2048: 2}
CORRECT = "ragas_answer_correctness"


def _setups() -> list[str]:
    crossed = [
        select35.Setup("4b", c, r, h).name
        for c in (512, 1024, 2048)
        for r in ("off", "4b")
        for h in ("off", "on")
    ]
    return crossed + [select35.Setup("4b", c, "4b", "on", True).name for c in (512, 1024, 2048)]


def _answers() -> list[dict[str, Any]]:
    """Plant a chunk effect of 0.1 per level on q00 to q05 only; no effect elsewhere."""
    rows = []
    for setup in _setups():
        chunk = select35.parse_setup(setup).chunk
        for dataset in DATASETS:
            for i in range(N):
                effect = 0.1 * STEP[chunk] if i < 6 else 0.0
                for run in (1, 2, 3):
                    rows.append(
                        {
                            "dataset": dataset,
                            "setup": setup,
                            "qid": f"q{i:02d}",
                            "doc_id": f"doc{i // 2}",
                            "run": run,
                            CORRECT: 0.3 + effect + i / 1000,
                        }
                    )
    return rows


def _closed() -> dict[str, dict[str, dict[str, float]]]:
    """Own wrong on q00 to q07; RAG prompt wrong on q00 to q05 and q08; q09 own is exactly 0.5."""
    own = {f"q{i:02d}": (0.1 if i < 8 else 0.9) for i in range(N)}
    own["q09"] = 0.5
    rag = {f"q{i:02d}": (0.2 if i < 6 or i == 8 else 0.8) for i in range(N)}
    rag["q09"] = 0.1
    del own["q11"]  # a question with no closed-book score
    return {d: {"closedbook-own": dict(own), "closedbook-rag": dict(rag)} for d in DATASETS}


def _rows(table: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {r["row"]: r for r in table["rows"]}


def test_subset_is_questions_both_closed_book_runs_answer_wrongly() -> None:
    result = contamination35.contamination(_answers(), _closed(), frozenset(), n_draws=500)
    table = result["freshstack"]
    assert table["label"] == "two closed-book runs"
    assert table["runs"] == ["closedbook-own", "closedbook-rag"]
    assert table["questions"] == N
    assert table["questions_kept"] == 6  # q00 to q05; q08 is right without context, q09 is 0.5
    assert table["no_closed_book_score"] == 1
    rows = _rows(table)
    assert sorted(rows) == [14, 15, 18, 19]
    assert rows[14]["n"] == 6 and rows[14]["metric"] == CORRECT
    assert rows[14]["estimate"] == pytest.approx(0.1)
    assert rows[19]["estimate"] == pytest.approx(0.1)
    assert rows[14]["method"].startswith("bias-reduced GEE")
    assert result["financebench"]["rows"][0]["method"] == "document sign-flip"


def test_drop_step_3_uses_the_own_knowledge_run_alone_and_labels_it() -> None:
    result = contamination35.contamination(_answers(), _closed(), frozenset({3}), n_draws=500)
    table = result["freshstack"]
    assert table["label"] == "one closed-book run"
    assert table["runs"] == ["closedbook-own"]
    assert table["questions_kept"] == 8  # q00 to q07
    assert _rows(table)[14]["estimate"] == pytest.approx(6 * 0.1 / 8)


def test_rag_prompt_scores_are_ignored_after_drop_step_3() -> None:
    closed = _closed()
    for d in DATASETS:
        del closed[d]["closedbook-rag"]
    dropped = contamination35.contamination(_answers(), closed, frozenset({3}), n_draws=500)
    assert dropped["freshstack"]["questions_kept"] == 8
    kept = contamination35.contamination(_answers(), closed, frozenset(), n_draws=500)
    assert kept["freshstack"]["questions_kept"] == 0
    assert kept["freshstack"]["no_closed_book_score"] == N


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_main_reads_saved_runs_behind_the_half_b_guard(tmp_path: Path) -> None:
    with pytest.raises(scoring35.HalfBLocked):
        contamination35.main(["--out-dir", str(tmp_path)])
    open_half_b(tmp_path)
    _write(tmp_path / "answer-scores.jsonl", _answers())
    for dataset, kinds in _closed().items():
        for kind, scores in kinds.items():
            folder = tmp_path / dataset / kind / _setups()[0] / "run1"
            _write(folder / "answer.jsonl", [{"qid": q, "answer": "a"} for q in scores])
            ragas = [{"qid": q, "metrics": {CORRECT: {"score": s}}} for q, s in scores.items()]
            _write(folder / "ragas.jsonl", ragas)
    (tmp_path / "drops.json").write_text(json.dumps({"drops": [{"step": 3}]}))
    assert contamination35.main(["--out-dir", str(tmp_path), "--draws", "200"]) == 0
    saved = json.loads((tmp_path / "contamination.json").read_text())
    assert saved["freshstack"]["label"] == "one closed-book run"
    assert saved["freshstack"]["questions_kept"] == 8
