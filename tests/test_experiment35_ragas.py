# ruff: noqa: S101
"""Experiment 35 Ragas stage: judging loop, resend rule and resume (tasks 7.1, 7.2).

Stub metrics and a scripted seam; no Ragas, no router, no network.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_ragas_fixtures import (
    QIDS,
    APIConnectionError,
    Router,
    Script,
    Status429,
    answer_row,
    ctx,
    parts,
    ragas35,
    ragas_stage,
    rows,
    run,
    stub_metrics,
    write_answers,
)

FIVE = list(ragas35.METRICS)


def _setup(tmp_path: Path, qids: list[str] = QIDS, run_no: int = 1) -> Path:
    run_dir = tmp_path / "financebench" / "e4b-c512-roff-hoff" / f"run{run_no}"
    write_answers(run_dir, [answer_row(q) for q in qids])
    return run_dir


# --- task 7.1 -----------------------------------------------------------------


def test_the_stage_reads_and_writes_only_the_named_run(tmp_path: Path) -> None:
    run1 = _setup(tmp_path, run_no=1)
    run2 = run1.parent / "run2"
    write_answers(run2, [answer_row(q, text="Other answers.") for q in QIDS])
    script, router = Script(), Router()
    assert run(ctx(run2, QIDS, router), parts(script, router)) == 0
    assert [r["qid"] for r in rows(run2)] == QIDS
    assert (run2 / ".done-ragas.json").exists()
    assert not (run1 / "ragas.jsonl").exists()
    assert {r["metrics"]["ragas_faithfulness"]["score"] for r in rows(run2)} == {0.25}


def test_the_stage_refuses_before_any_call_without_the_answer_marker(tmp_path: Path) -> None:
    run_dir = tmp_path / "run1"
    write_answers(run_dir, [answer_row(q) for q in QIDS], done=False)
    script, router = Script(), Router()
    with pytest.raises(ragas35.RagasRefused, match="answer stage"):
        run(ctx(run_dir, QIDS, router), parts(script, router))
    assert script.prompts == [] and router.opened == 0
    assert not (run_dir / "ragas.jsonl").exists()


def test_a_wrong_ragas_version_stops_before_any_call_and_names_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = type(sys)("ragas")
    fake.__version__ = "0.3.9"
    monkeypatch.setitem(sys.modules, "ragas", fake)
    run_dir = _setup(tmp_path)
    script, router = Script(), Router()
    with pytest.raises(ragas_stage.RagasMissingError, match=r"0\.3\.9.*0\.4\.3"):
        run(ctx(run_dir, QIDS, router), parts(script, router, require=ragas_stage.require_ragas))
    assert script.prompts == [] and router.opened == 0


def test_an_answer_with_an_error_is_not_judged_and_an_empty_answer_is(tmp_path: Path) -> None:
    # Review R2-03: a returned empty answer is a final answer (section 12) and gets scores.
    run_dir = tmp_path / "run1"
    answers = [answer_row("q0", error="generation failed"), answer_row("q1"), answer_row("q2")]
    answers[2]["answer"] = ""
    write_answers(run_dir, answers)
    script, router = Script(), Router()
    assert run(ctx(run_dir, ["q0", "q1", "q2"], router), parts(script, router)) == 0
    saved = {r["qid"]: r for r in rows(run_dir)}
    assert saved["q0"]["not_judged"] == "no answer text"
    assert saved["q0"]["metrics"] == {} and saved["q0"]["calls"] == []
    assert saved["q2"]["not_judged"] is None and sorted(saved["q2"]["metrics"]) == sorted(FIVE)
    assert {p.split("|")[1] for p in script.prompts} == {"q1", "q2"}


def test_a_missing_answer_row_is_not_judged(tmp_path: Path) -> None:
    run_dir = tmp_path / "run1"
    write_answers(run_dir, [{"qid": "q0", "missing": True, "error": "x"}, answer_row("q1")])
    script, router = Script(), Router()
    assert run(ctx(run_dir, ["q0", "q1"], router), parts(script, router)) == 0
    assert rows(run_dir)[0]["not_judged"] == "no answer text"
    assert {p.split("|")[1] for p in script.prompts} == {"q1"}


def test_an_answer_without_passages_skips_the_three_passage_metrics(tmp_path: Path) -> None:
    # Closed-book answers have no evidence: those metrics are undefined (pod 2026-11-24).
    run_dir = tmp_path / "run1"
    row = answer_row("q1")
    row["evidence"] = []
    write_answers(run_dir, [row])
    script, router = Script(), Router()
    assert run(ctx(run_dir, ["q1"], router), parts(script, router)) == 0
    saved = rows(run_dir)[0]
    assert saved["unjudged"] == []
    for name in ragas35.CONTEXT_METRICS:
        assert saved["metrics"][name] == {"score": None, "not_judged": "no passages", "calls": 0}
    assert saved["metrics"]["ragas_answer_correctness"]["score"] is not None
    assert saved["metrics"]["ragas_answer_relevancy"]["score"] is not None


def test_a_refusal_answer_is_scored_with_every_metric(tmp_path: Path) -> None:
    run_dir = tmp_path / "run1"
    write_answers(run_dir, [answer_row("q1", text="The evidence does not answer this.")])
    script, router = Script(), Router()
    assert run(ctx(run_dir, ["q1"], router), parts(script, router)) == 0
    row = rows(run_dir)[0]
    assert row["not_judged"] is None and row["unjudged"] == []
    assert sorted(row["metrics"]) == sorted(FIVE)
    assert all(m["score"] is not None for m in row["metrics"].values())


def test_each_worker_has_its_own_seam_so_calls_never_mix(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path)
    script, router = Script(), Router()
    assert run(ctx(run_dir, QIDS, router, ragas_concurrency=4), parts(script, router)) == 0
    for row in rows(run_dir):
        expected = 1 + int(row["qid"][1:]) % 3
        for name in FIVE:
            assert row["metrics"][name]["calls"] == expected, (row["qid"], name)
        assert len(row["calls"]) == expected * len(FIVE)


def test_rows_are_byte_identical_at_concurrency_8_and_1(tmp_path: Path) -> None:
    texts = []
    for concurrency in (8, 1):
        run_dir = _setup(tmp_path / str(concurrency))
        script, router = Script(), Router()
        c = ctx(run_dir, QIDS, router, ragas_concurrency=concurrency)
        assert run(c, parts(script, router)) == 0
        texts.append((run_dir / "ragas.jsonl").read_bytes())
    assert texts[0] == texts[1]


# --- task 7.2 -----------------------------------------------------------------


def test_a_429_on_every_attempt_saves_no_row_and_exits_5(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script, router = Script({("ragas_answer_relevancy", "q1"): Status429}), Router()
    assert run(ctx(run_dir, ["q1"], router), parts(script, router)) == ragas35.EXIT_RATE_LIMIT
    assert rows(run_dir) == []
    assert not (run_dir / ".done-ragas.json").exists()


def test_a_rate_limit_stop_keeps_the_scored_metrics_and_resume_scores_the_rest(
    tmp_path: Path,
) -> None:
    """Issue 217: metrics scored before the stop are saved; resume sends only the others."""
    run_dir = _setup(tmp_path, ["q1", "q2"])
    script, router = Script({("ragas_answer_relevancy", "q1"): Status429}), Router()
    assert run(ctx(run_dir, ["q1", "q2"], router), parts(script, router)) == (
        ragas35.EXIT_RATE_LIMIT
    )
    partial = [json.loads(x) for x in (run_dir / "ragas.partial.jsonl").read_text().splitlines()]
    assert [p["qid"] for p in partial] == ["q1"]
    assert list(partial[0]["metrics"]) == ["ragas_faithfulness"]
    assert partial[0]["unjudged"] == []
    assert rows(run_dir) == []
    summary = json.loads((run_dir / "ragas-summary.json").read_text())
    assert summary["unjudged_open"] == {}
    assert not (run_dir / "ragas.metric-errors.jsonl").exists()

    script = Script()
    c = ctx(run_dir, ["q1", "q2"], router)
    c.resume = True
    assert run(c, parts(script, router)) == 0
    q1 = {p.split("|")[0] for p in script.prompts if p.split("|")[1] == "q1"}
    assert q1 == set(FIVE) - {"ragas_faithfulness"}
    assert {p.split("|")[1] for p in script.prompts if p.startswith("ragas_faithfulness")} == {"q2"}
    assert [r["qid"] for r in rows(run_dir)] == ["q1", "q2"]
    assert sorted(rows(run_dir)[0]["metrics"]) == sorted(FIVE)


def test_a_rate_limit_stop_also_keeps_a_failed_metric_error_of_the_answer(
    tmp_path: Path,
) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script = Script(
        {
            ("ragas_answer_relevancy", "q1"): APIConnectionError,
            ("ragas_context_precision", "q1"): Status429,
        }
    )
    router = Router()
    assert run(ctx(run_dir, ["q1"], router), parts(script, router)) == ragas35.EXIT_RATE_LIMIT
    partial = [json.loads(x) for x in (run_dir / "ragas.partial.jsonl").read_text().splitlines()]
    assert list(partial[-1]["metrics"]) == ["ragas_faithfulness"]
    assert [u["metric"] for u in partial[-1]["unjudged"]] == ["ragas_answer_relevancy"]
    errors = (run_dir / "ragas.metric-errors.jsonl").read_text().splitlines()
    assert [json.loads(x)["metric"] for x in errors] == ["ragas_answer_relevancy"]


def test_resume_after_a_stop_at_40_of_100_sends_calls_for_the_other_60_only(
    tmp_path: Path,
) -> None:
    qids = [f"q{i}" for i in range(100)]
    run_dir = _setup(tmp_path, qids)
    script, router = Script({("ragas_faithfulness", "q40"): Status429}), Router()
    assert run(ctx(run_dir, qids, router), parts(script, router)) == ragas35.EXIT_RATE_LIMIT
    assert [r["qid"] for r in rows(run_dir)] == qids[:40]
    script = Script()
    c = ctx(run_dir, qids, router)
    c.resume = True
    assert run(c, parts(script, router)) == 0
    assert {p.split("|")[1] for p in script.prompts} == set(qids[40:])
    assert [r["qid"] for r in rows(run_dir)] == qids


def test_a_connection_error_is_unjudged_and_resume_reruns_only_that_metric(
    tmp_path: Path,
) -> None:
    run_dir = _setup(tmp_path, ["q1", "q2"])
    failing = Script({("ragas_answer_correctness", "q1"): APIConnectionError})
    router = Router()
    assert run(ctx(run_dir, ["q1", "q2"], router), parts(failing, router)) == ragas35.EXIT_OPEN
    assert not (run_dir / ".done-ragas.json").exists()
    assert [r["qid"] for r in rows(run_dir)] == []  # q1 is open, so q2 waits in order
    partial = [json.loads(x) for x in (run_dir / "ragas.partial.jsonl").read_text().splitlines()]
    assert partial[-1]["unjudged"] == [
        {
            "metric": "ragas_answer_correctness",
            "errors": 1,
            "error": "APIConnectionError",
            "closed": False,
        }
    ]
    assert "ragas_answer_correctness" not in partial[-1]["metrics"]
    assert len(partial[-1]["metrics"]) == 4
    summary = json.loads((run_dir / "ragas-summary.json").read_text())
    assert summary["errors"] == 1 and summary["unjudged_open"] == {"ragas_answer_correctness": 1}

    script = Script()
    c = ctx(run_dir, ["q1", "q2"], router)
    c.resume = True
    assert run(c, parts(script, router)) == 0
    assert {p.split("|")[0] for p in script.prompts} == {"ragas_answer_correctness"}
    assert {p.split("|")[1] for p in script.prompts} == {"q1"}
    row = rows(run_dir)[0]
    assert row["qid"] == "q1" and sorted(row["metrics"]) == sorted(FIVE)
    assert row["unjudged"] == []
    marker = json.loads((run_dir / ".done-ragas.json").read_text())
    assert marker["resent_calls"] == 1


def test_a_metric_that_failed_three_times_is_closed_and_the_stage_continues(
    tmp_path: Path,
) -> None:
    run_dir = _setup(tmp_path, ["q1", "q2"])
    router = Router()
    codes = []
    for attempt in range(3):
        script = Script({("ragas_faithfulness", "q1"): APIConnectionError})
        c = ctx(run_dir, ["q1", "q2"], router)
        c.resume = attempt > 0
        codes.append(run(c, parts(script, router)))
    assert codes == [ragas35.EXIT_OPEN, ragas35.EXIT_OPEN, 0]
    saved = {r["qid"]: r for r in rows(run_dir)}
    assert saved["q1"]["unjudged"] == [
        {"metric": "ragas_faithfulness", "errors": 3, "error": "APIConnectionError", "closed": True}
    ]
    assert "ragas_faithfulness" not in saved["q1"]["metrics"]
    assert saved["q2"]["unjudged"] == []
    summary = json.loads((run_dir / ".done-ragas.json").read_text())
    assert summary["unjudged_closed"] == {"ragas_faithfulness": 1}
    assert summary["errors"] == 3 and summary["resent_calls"] == 2


def test_the_summary_never_reports_zero_errors_when_a_row_is_unjudged(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script = Script({("ragas_context_recall", "q1"): APIConnectionError})
    router = Router()
    run(ctx(run_dir, ["q1"], router), parts(script, router))
    summary = json.loads((run_dir / "ragas-summary.json").read_text())
    assert summary["setup"] == "e4b-c512-roff-hoff"
    assert summary["errors"] >= 1 and summary["unjudged_open"] == {"ragas_context_recall": 1}


def _nan_metrics(seam: Any, embeddings: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """The stub metrics, with faithfulness returning NaN for ``q1``."""
    fns, weights = stub_metrics(seam, embeddings)
    real = fns["ragas_faithfulness"]

    async def faith(sample: dict[str, Any]) -> float:
        score = await real(sample)
        return math.nan if sample["qid"] == "q1" else score

    return {**fns, "ragas_faithfulness": faith}, weights


def test_a_nan_score_is_final_undefined_and_never_resent(tmp_path: Path) -> None:
    # Review R2-14: a NaN from a call that returned is returned content.
    run_dir = _setup(tmp_path, ["q1", "q2"])
    script, router = Script(), Router()
    assert run(ctx(run_dir, ["q1", "q2"], router), parts(script, router, metrics=_nan_metrics)) == 0
    row = rows(run_dir)[0]
    metric = row["metrics"]["ragas_faithfulness"]
    assert metric["score"] is None and metric["not_defined"] == "score is NaN"
    assert row["unjudged"] == [] and not (run_dir / "ragas.metric-errors.jsonl").exists()
    summary = json.loads((run_dir / "ragas-summary.json").read_text())
    assert summary["errors"] == 0 and summary["not_defined"] == {"ragas_faithfulness": 1}


def test_cut_last_lines_of_the_ragas_side_files_are_repaired_on_resume(tmp_path: Path) -> None:
    # Review R2-09: a stop part-way through an append must not block --resume.
    run_dir = _setup(tmp_path, ["q1", "q2"])
    failing = Script({("ragas_answer_correctness", "q1"): APIConnectionError})
    router = Router()
    assert run(ctx(run_dir, ["q1", "q2"], router), parts(failing, router)) == ragas35.EXIT_OPEN
    for name in ("ragas.partial.jsonl", "ragas.metric-errors.jsonl"):
        path = run_dir / name
        path.write_text(path.read_text(encoding="utf-8") + '{"qid": "q1", "met', encoding="utf-8")
    c = ctx(run_dir, ["q1", "q2"], router)
    c.resume = True
    assert run(c, parts(Script(), router)) == 0
    assert [r["qid"] for r in rows(run_dir)] == ["q1", "q2"]
    errors = (run_dir / "ragas.metric-errors.jsonl").read_text(encoding="utf-8")
    assert errors.endswith("\n") and len(errors.splitlines()) == 1
