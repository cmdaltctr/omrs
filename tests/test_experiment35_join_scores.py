"""Experiment 35 answer-score records and the join guard (review R3-03, R3-05, R3-08, R3-12).

Pre-registration section 12 (unjudged rows, unparseable verdicts) and 14.2 (half-B guard).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests import _exp35_join_fixtures as fx
from tests._exp35_fixtures import load

join35 = load("join35")
joinscores35 = load("joinscores35")
scoring35 = load("scoring35")

FAITH = ("faithfulness_glm_factual", "faithfulness_glm_factual_uncited")
CORRECT = "ragas_answer_correctness"


@pytest.fixture
def built(tmp_path: Path) -> tuple[Path, Path, list[Path]]:
    out, experiment = tmp_path / "out", tmp_path / "exp"
    return out, experiment, fx.build(out, experiment)


def _folder(out: Path) -> Path:
    return out / "bioasq" / "answer" / fx.SETUPS[0] / "run2"


def _edit(path: Path, qid: str, **change: object) -> None:
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    fx.write_rows(path, [{**r, **change} if r["qid"] == qid else r for r in rows])


def _scores(folder: Path, **kw: object) -> dict[str, dict]:
    records = joinscores35.answer_scores(folder, "bioasq", fx.SETUPS[0], 2, kinds_version="v", **kw)
    return {r["qid"]: r for r in records}


def test_a_closed_missing_checker_row_marks_faithfulness_unjudged(built) -> None:
    out, _, _ = built
    folder = _folder(out)
    fx.write_rows(
        folder / "judge-chat.jsonl",
        [{"qid": "q1", "missing": True, "error": "down"}, {"qid": "q2", "verdicts": []}],
    )
    scores = _scores(folder)
    assert scores["q1"]["unjudged"] == list(FAITH)
    assert scores["q1"]["faithfulness_glm_factual"] is None
    assert scores["q2"]["unjudged"] == []  # a judged answer with no verdict: no claim, not unjudged


def test_a_closed_missing_ragas_metric_marks_correctness_unjudged(built) -> None:
    out, _, _ = built
    folder = _folder(out)
    closed = [{"metric": CORRECT, "errors": 3, "error": "Timeout", "closed": True}]
    _edit(folder / "ragas.jsonl", "q1", metrics={}, unjudged=closed)
    scores = _scores(folder)
    assert scores["q1"]["unjudged"] == [CORRECT] and scores["q1"][CORRECT] is None
    assert scores["q2"]["unjudged"] == [] and scores["q2"][CORRECT] == 0.75


def test_an_answer_with_a_closed_claim_is_unjudged_and_counted(built) -> None:
    # The judge stage (F6) saves it with missing: true and closed_claims, keeping the
    # other verdicts. Section 12: the row leaves the complete cases and is counted.
    out, experiment, pods = built
    folder = _folder(out)
    verdicts = [
        {"index": 0, "ordinals": [1], "verdict": None, "closed": True, "error": "down"},
        {"index": 1, "ordinals": [1], "verdict": "supported"},
    ]
    _edit(folder / "judge-chat.jsonl", "q1", missing=True, closed_claims=[0], verdicts=verdicts)
    scores = _scores(folder)
    assert scores["q1"]["unjudged"] == list(FAITH) and scores["q1"][FAITH[0]] is None
    report = join35.join(
        out,
        experiment=experiment,
        records=pods,
        search_setups=fx.SETUPS,
        answer_setups=fx.SETUPS,
        datasets=fx.DATASETS,
        requested=fx.REQUESTED,
    )
    assert report["unjudged"]["bioasq"][fx.SETUPS[0]] == {FAITH[0]: 1, FAITH[1]: 1, CORRECT: 0}


def test_an_undefined_ragas_correctness_is_its_own_category(built) -> None:
    # F6: a NaN score is returned content, saved as score null with not_defined. It is
    # neither unjudged nor 0: the run has no value, as a no-claim run for faithfulness.
    out, experiment, pods = built
    folder = _folder(out)
    metric = {"score": None, "not_defined": "score is NaN"}
    _edit(folder / "ragas.jsonl", "q1", metrics={CORRECT: metric})
    scores = _scores(folder)
    assert scores["q1"][CORRECT] is None
    assert scores["q1"]["not_defined"] == [CORRECT] and scores["q1"]["unjudged"] == []
    assert scores["q2"]["not_defined"] == []
    report = join35.join(
        out,
        experiment=experiment,
        records=pods,
        search_setups=fx.SETUPS,
        answer_setups=fx.SETUPS,
        datasets=fx.DATASETS,
        requested=fx.REQUESTED,
    )
    assert report["not_defined"]["bioasq"][fx.SETUPS[0]] == {CORRECT: 1}


def test_an_empty_answer_scores_correctness_zero_and_is_not_unjudged(built) -> None:
    # Ragas gets no text (a not_judged row), as for a closed-missing answer.
    out, _, _ = built
    folder = _folder(out)
    _edit(folder / "answer.jsonl", "q1", answer="")
    _edit(folder / "ragas.jsonl", "q1", metrics={}, not_judged="no answer text")
    scores = _scores(folder)
    assert scores["q1"][CORRECT] == 0.0 and scores["q1"]["unjudged"] == []


def test_an_unparseable_verdict_counts_not_supported_and_is_counted(built) -> None:
    out, _, _ = built
    folder = _folder(out)
    verdicts = [{"index": 0, "ordinals": [1], "verdict": "unparseable"}]
    _edit(folder / "judge-chat.jsonl", "q1", verdicts=verdicts)
    scores = _scores(folder)
    assert scores["q1"]["faithfulness_glm_factual"] == 0.0
    assert scores["q1"]["unparseable_verdicts"] == 1 and scores["q1"]["unjudged"] == []
    assert scores["q2"]["unparseable_verdicts"] == 0


def test_a_closed_missing_answer_keeps_its_question_document(built) -> None:
    out, _, _ = built
    folder = _folder(out)
    fx.write_rows(
        folder / "answer.jsonl",
        [{"qid": "q1", "missing": True, "error": "down"}, {"qid": "q2", "doc_id": "WRONG"}],
    )
    scores = _scores(folder, documents={"q1": "DOC_A", "q2": "DOC_B"})
    assert scores["q1"]["doc_id"] == "DOC_A"  # the question's document, not the answer row's
    assert scores["q2"]["doc_id"] == "DOC_B"


def test_the_join_reads_financebench_documents_from_the_score_records(tmp_path: Path) -> None:
    for half, rows in (("A", [("q1", "D1")]), ("B", [("q2", "D2")])):
        fx.write_rows(
            tmp_path / "scores" / half / "financebench" / "e4b-c512-roff-hoff.jsonl",
            [{"qid": q, "doc_id": d} for q, d in rows],
        )
    assert join35.question_documents(tmp_path) == {"q1": "D1", "q2": "D2"}


def test_the_main_join_writes_nothing_before_half_b_opens(built) -> None:
    out, experiment, pods = built
    (out / "osf-timestamp.json").unlink()
    with pytest.raises(scoring35.HalfBLocked, match="osf-timestamp.json"):
        join35.join(
            out,
            experiment=experiment,
            records=pods,
            search_setups=fx.SETUPS,
            answer_setups=fx.SETUPS,
            datasets=fx.DATASETS,
            requested=fx.REQUESTED,
        )
    assert not (out / "join.json").exists() and not (out / "answer-scores.jsonl").exists()


def test_a_smoke_join_needs_no_time_stamp(tmp_path: Path) -> None:
    out, experiment = tmp_path / "out", tmp_path / "exp"
    pods = fx.build(out, experiment, runs=(1,))
    (out / "osf-timestamp.json").unlink()
    report = join35.join(
        out,
        experiment=experiment,
        records=pods,
        search_setups=fx.SETUPS,
        answer_setups=fx.SETUPS,
        datasets=fx.DATASETS,
        runs=(1,),
        smoke=True,
        requested=fx.REQUESTED,
    )
    assert report["smoke"] is True and (out / "join.json").exists()


def test_the_record_carries_the_realised_evidence_total_into_the_h8b_table(built) -> None:
    # Review B4: the answer stage saves evidence_tokens; the join must copy it, or the
    # registered cut-against-realised table (prereg section 21) prints nulls.
    out, _, _ = built
    folder = _folder(out)
    t20k = "e4b-c512-r4b-hon-t20k"
    scores = joinscores35.answer_scores(folder, "bioasq", t20k, 2, kinds_version="v")
    assert {r["evidence_tokens"] for r in scores} == {900}
    totals = load("reporttables35").h8b_token_totals(scores)["bioasq"][t20k]
    assert totals["all"] == {"mean_cut_tokens": 1000, "mean_realised_tokens": 900}
    assert totals["no_realised_total"] == 0


def test_join_counts_unparseable_verdicts_per_dataset_and_setup(built) -> None:
    # Pre-registration section 12 (Counts): the join counts unparseable verdicts per setup.
    out, experiment, pods = built
    folder = _folder(out)
    verdicts = [{"index": 0, "ordinals": [1], "verdict": "unparseable"}]
    _edit(folder / "judge-chat.jsonl", "q1", verdicts=verdicts)
    report = join35.join(
        out,
        experiment=experiment,
        records=pods,
        search_setups=fx.SETUPS,
        answer_setups=fx.SETUPS,
        datasets=fx.DATASETS,
        requested=fx.REQUESTED,
    )
    assert report["unparseable_verdicts"]["bioasq"] == {fx.SETUPS[0]: 1, fx.SETUPS[1]: 0}
    assert report["unparseable_verdicts"]["legal"] == {fx.SETUPS[0]: 0, fx.SETUPS[1]: 0}
