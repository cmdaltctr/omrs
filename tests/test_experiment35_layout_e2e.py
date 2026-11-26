"""Experiment 35 readers on a folder written through the runner's ``Layout`` (integration F3).

Rule under test: every reader of run folders takes its paths from
``outputs35.Layout`` (``<out>/<dataset>/<kind>/<setup>/run<n>/``), so the join,
``score35.py``, the faithfulness label sampler, the correctness gate sample and
the refusal report all find the rows the stages wrote. A reader that finds no
answer file where the plan expects one refuses and names the folder; it never
writes an empty result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests import _exp35_e2e_fixtures as fx
from tests._exp35_fixtures import load

correct35 = load("correct35")
crosstable35 = load("crosstable35")
join35 = load("join35")
labels35 = load("labels35")
lengthcheck35 = load("lengthcheck35")
outputs35 = load("outputs35")
refusalreport35 = load("refusalreport35")
score35 = load("score35")
scoring35 = load("scoring35")


@pytest.fixture
def out(tmp_path: Path) -> Path:
    folder, experiment = tmp_path / "out", tmp_path / "exp"
    pods = fx.build(folder, experiment)
    report = join35.join(
        folder,
        experiment=experiment,
        records=pods,
        search_setups=fx.SETUPS,
        answer_setups=fx.SETUPS,
        datasets=fx.DATASETS,
        runs=fx.RUNS,
        requested=fx.REQUESTED,
    )
    assert report["ok"] is True, report["failures"]
    return folder


def _golds() -> dict:
    return {
        d: {q: scoring35.Gold(q, frozenset({fx.unit(d, q)})) for q in fx.QIDS} for d in fx.DATASETS
    }


def test_the_join_finds_every_answer_row(out: Path) -> None:
    rows = outputs35.read_rows(out / "answer-scores.jsonl")
    assert len(rows) == len(fx.DATASETS) * len(fx.SETUPS) * len(fx.RUNS) * len(fx.QIDS)
    assert {r["faithfulness_glm_factual"] for r in rows} == {1.0}
    assert {r["ragas_answer_correctness"] for r in rows} == {0.75}


def test_score35_finds_the_search_rows(out: Path) -> None:
    found = score35.score(
        out,
        "A",
        halves=fx.HALVES,
        golds=_golds(),
        unit_maps={"freshstack": {f"doc-{q}": f"doc-{q}" for q in fx.QIDS}},
    )
    assert set(found) == set(fx.DATASETS)
    for dataset in fx.DATASETS:
        assert set(found[dataset]) == set(fx.SETUPS)
        assert {s["n"] for s in found[dataset].values()} == {2}
        assert {s["recall_at_10"] for s in found[dataset].values()} == {1.0}


def test_the_faithfulness_sampler_finds_the_claims(out: Path) -> None:
    labels35.require_kinds(out, fx.VERSION)
    claims = labels35.faithfulness_claims(out, fx.questions(), fx.VERSION)
    expected = len(fx.DATASETS) * len(fx.SETUPS) * len(fx.RUNS) * len(fx.QIDS) * len(fx.CLAIMS)
    assert len(claims) == expected
    items = labels35.draw_faithfulness(claims, per_cell=1)
    verdicts = labels35.saved_verdicts(out, items)
    assert set(verdicts["chat"].values()) == {"supported"}
    assert len(verdicts["chat"]) == len(items) > 0


def test_the_correctness_sample_finds_run_one_answers_and_ragas_scores(out: Path) -> None:
    items = correct35.draw(out, out.parent / "halves.json", fx.questions(), per_dataset=2)
    assert len(items) == 2 * len(fx.DATASETS)  # drop step 1: no Legal
    assert {i["answer"] for i in items} == {fx.ANSWER}
    assert set(correct35._scores(out, items).values()) == {0.75}


def test_the_refusal_report_finds_every_run(out: Path) -> None:
    gate = out.parent / "gate.json"
    gate.write_text(json.dumps({"pass": True, "version": fx.VERSION}))
    path = refusalreport35.write_report(out, gate_path=gate, n_boot=50)
    loaded = refusalreport35.load(out, fx.VERSION)
    assert set(loaded) == {(d, s) for d in fx.DATASETS for s in fx.SETUPS}
    assert all(set(runs) == set(fx.RUNS) for runs in loaded.values())
    assert json.loads(path.read_text())["faithfulness"]


# --- refusal on a folder with no answer files ------------------------------------------------


def _empty(tmp_path: Path) -> Path:
    folder = tmp_path / "empty"
    (folder / "bioasq" / "answer").mkdir(parents=True)
    (folder / "join.json").write_text(json.dumps({"ok": True, "smoke": False}))
    return folder


@pytest.mark.parametrize(
    "reader",
    [
        lambda o: labels35.faithfulness_claims(o, fx.questions(), fx.VERSION),
        lambda o: labels35.require_kinds(o, fx.VERSION),
        lambda o: refusalreport35.load(o, fx.VERSION),
        lambda o: lengthcheck35.pool(o),
        lambda o: correct35.draw(o, o.parent / "halves.json", fx.questions(), per_dataset=2),
    ],
)
def test_an_answer_reader_refuses_a_folder_with_no_answer_files(tmp_path: Path, reader) -> None:
    folder = _empty(tmp_path)
    (folder / "drops.json").write_text(json.dumps({"drops": [{"step": 1}]}))
    with pytest.raises(outputs35.NoRunFiles, match=str(folder)):
        reader(folder)


def test_score35_refuses_a_folder_with_no_search_files(tmp_path: Path) -> None:
    folder = _empty(tmp_path)
    with pytest.raises(outputs35.NoRunFiles, match=str(folder)):
        score35.score(folder, "A", halves=fx.HALVES, golds=_golds())


def test_the_cross_table_refuses_without_answer_scores(tmp_path: Path) -> None:
    folder = _empty(tmp_path)
    with pytest.raises(outputs35.NoRunFiles, match="answer-scores.jsonl"):
        crosstable35.build_tables(folder)
