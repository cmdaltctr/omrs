"""FreshStack alpha-nDCG@10 through the official scorer (RDY 16.3; pre-registration section 6).

The official ``metrics.py`` runs in its own venv with the pinned ``pyndeval``.
These tests stand in a fake ``metrics.py`` (its SHA-256 is the pin under test)
and run the real runner with this interpreter, so no network and no pyndeval.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load, open_half_b

alphandcg35 = load("alphandcg35")

#: Records the arguments it got and returns the share of questions with a result.
FAKE_METRICS = """
import json, sys, types
fake = types.ModuleType("pyndeval")
fake.__version__ = "0.0.8"
sys.modules["pyndeval"] = fake
CALLS = []

def alpha_ndcg(qrels_nuggets, query_to_nuggets, results, k_values):
    CALLS.append({"qrels": qrels_nuggets, "nuggets": query_to_nuggets,
                  "results": results, "k": k_values})
    with open(sys.argv[2] + ".calls", "a") as handle:
        handle.write(json.dumps(CALLS[-1]) + "\\n")
    return {"alpha-nDCG@10": round(len(results) / len(query_to_nuggets), 4)}
"""

GROUND_TRUTH = {
    "queries": [
        {
            "query_id": "1",
            "relevant_parent_ids": ["a", "b"],
            "nuggets": [
                {
                    "nugget_id": "1_0",
                    "relevant_corpus_ids": ["a"],
                    "non_relevant_corpus_ids": ["n"],
                },
                {"nugget_id": "1_1", "relevant_corpus_ids": ["b"], "non_relevant_corpus_ids": []},
            ],
        },
        {
            "query_id": "2",
            "relevant_parent_ids": ["c"],
            "nuggets": [
                {"nugget_id": "2_0", "relevant_corpus_ids": ["c"], "non_relevant_corpus_ids": []}
            ],
        },
        {
            "query_id": "continuity_001",  # the 20 continuity queries carry nuggets too
            "relevant_parent_ids": ["z"],
            "nuggets": [
                {
                    "nugget_id": "continuity_001_0",
                    "relevant_corpus_ids": ["z"],
                    "non_relevant_corpus_ids": [],
                }
            ],
        },
    ]
}


@pytest.fixture
def scorer(tmp_path: Path) -> dict[str, Any]:
    repo = tmp_path / "repo"
    metrics = repo / "freshstack" / "retrieval" / "metrics.py"
    metrics.parent.mkdir(parents=True)
    metrics.write_text(FAKE_METRICS, encoding="utf-8")
    gt = tmp_path / "data" / alphandcg35.datasets35._FS_GT
    gt.parent.mkdir(parents=True)
    gt.write_text(json.dumps(GROUND_TRUTH), encoding="utf-8")
    pin = {
        "repo": "https://github.com/fresh-stack/freshstack",
        "commit": "a1c8c45bb8e6b0d5ec2b61852977b67207f0c9d4",
        "metrics_py_sha256": hashlib.sha256(metrics.read_bytes()).hexdigest(),
        "pyndeval_version": "0.0.8",
        "alpha": 0.5,
        "k": 10,
    }
    return {"repo": repo, "root": tmp_path / "data", "pin": pin, "python": sys.executable}


def _record(setup: str, qid: str, ranked: list[str], dataset: str = "freshstack") -> dict:
    return {"dataset": dataset, "setup": setup, "qid": qid, "ranked_units": ranked}


def test_nugget_qrels_follow_the_official_loader(scorer: dict[str, Any]) -> None:
    qrels, by_query = alphandcg35.nugget_qrels(scorer["root"])
    assert qrels == {"1_0": {"a": 1, "n": 0}, "1_1": {"b": 1}, "2_0": {"c": 1}}
    assert by_query == {"1": ["1_0", "1_1"], "2": ["2_0"]}


def test_runs_give_strictly_falling_scores_in_rank_order() -> None:
    records = [_record("s1", "1", ["b", "x", "a"]), _record("s1", "2", [], "freshstack")]
    records.append(_record("s1", "9", ["a"], "bioasq"))
    assert alphandcg35.runs(records) == {"s1": {"1": {"b": 1000, "x": 999, "a": 998}, "2": {}}}


def test_score_calls_the_pinned_scorer_once_per_setup(scorer: dict[str, Any], tmp_path) -> None:
    records = [
        _record("e4b-c512-roff-hoff", "1", ["a", "x"]),
        _record("e4b-c512-roff-hoff", "2", []),
        _record("e8b-c512-roff-hoff", "1", ["b"]),
    ]
    out = alphandcg35.score(records, **scorer)
    assert out["e4b-c512-roff-hoff"] == {"alpha_ndcg_at_10": 0.5, "n": 2}
    assert out["e8b-c512-roff-hoff"] == {"alpha_ndcg_at_10": 1.0, "n": 1}
    calls = [json.loads(x) for x in Path(f"{out['_input']}.calls").read_text().splitlines()]
    assert [c["k"] for c in calls] == [[10], [10]]
    assert calls[0]["nuggets"] == {"1": ["1_0", "1_1"], "2": ["2_0"]}
    assert calls[0]["results"] == {"1": {"a": 1000, "x": 999}}  # an empty list sends no result
    assert calls[1]["nuggets"] == {"1": ["1_0", "1_1"]}


def test_a_changed_metrics_file_is_refused(scorer: dict[str, Any]) -> None:
    path = scorer["repo"] / "freshstack" / "retrieval" / "metrics.py"
    path.write_text(FAKE_METRICS + "\n# edited\n", encoding="utf-8")
    with pytest.raises(alphandcg35.ScorerRefused, match="metrics.py"):
        alphandcg35.score([_record("s", "1", ["a"])], **scorer)


def test_another_pyndeval_version_is_refused(scorer: dict[str, Any]) -> None:
    scorer["pin"]["pyndeval_version"] = "0.0.7"
    with pytest.raises(alphandcg35.ScorerRefused, match="0.0.8"):
        alphandcg35.score([_record("s", "1", ["a"])], **scorer)


def test_an_alpha_other_than_the_official_default_is_refused(scorer: dict[str, Any]) -> None:
    scorer["pin"]["alpha"] = 0.4
    with pytest.raises(alphandcg35.ScorerRefused, match="alpha"):
        alphandcg35.score([_record("s", "1", ["a"])], **scorer)


def test_main_writes_the_table_behind_the_half_b_guard(
    scorer: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scoring35 = load("scoring35")
    out = tmp_path / "out"
    folder = out / "scores" / "A" / "freshstack"
    folder.mkdir(parents=True)
    (folder / "e4b-c512-roff-hoff.jsonl").write_text(
        json.dumps(_record("e4b-c512-roff-hoff", "1", ["a"])) + "\n", encoding="utf-8"
    )
    plan = {"pins": {"scorers": {"freshstack_alpha_ndcg": scorer["pin"]}}}
    monkeypatch.setattr(alphandcg35, "read_plan", lambda: plan)
    monkeypatch.setattr(alphandcg35.datasets35, "data_root", lambda: scorer["root"])
    argv = ["--out-dir", str(out), "--python", scorer["python"], "--repo", str(scorer["repo"])]
    with pytest.raises(scoring35.HalfBLocked):
        alphandcg35.main(argv)
    open_half_b(out)
    assert alphandcg35.main(argv) == 0
    saved = json.loads((out / "alpha-ndcg.json").read_text(encoding="utf-8"))
    assert saved["setups"] == {"e4b-c512-roff-hoff": {"alpha_ndcg_at_10": 1.0, "n": 1}}
    assert saved["descriptive"] is True and saved["pin"] == scorer["pin"]


def test_the_plan_pins_the_official_scorer() -> None:
    plan = json.loads((alphandcg35.EXP_DIR / "plan.json").read_text(encoding="utf-8"))
    pin = plan["pins"]["scorers"]["freshstack_alpha_ndcg"]
    assert pin["commit"] == "a1c8c45bb8e6b0d5ec2b61852977b67207f0c9d4"
    assert pin["metrics_py_sha256"] == (
        "0f3316491bb6adfcf06c6fbc91bd2734cba0f19575602cd99c0b652c0fb3e0b9"
    )
    assert (pin["pyndeval_version"], pin["alpha"], pin["k"]) == ("0.0.8", 0.5, 10)
    assert pin["role"] == "secondary, descriptive (FreshStack only)"
