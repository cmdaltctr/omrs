# ruff: noqa: S101
"""Tests for the 20-answer measurement (master task 6.3). Stubs only: no router, net or Ragas."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import measure_answers  # noqa: E402
import measure_lib  # noqa: E402
from ragas_stage import ChatReply, RecordingSeam  # noqa: E402

SENTINEL = "ZQX-SENTINEL-TEXT-7731"


def _pool(n_exp2: int = 17, n_fb: int = 25) -> list[dict]:
    exp2 = [{"query": f"exp2 question {i}", "expected_answer": f"ref {i}"} for i in range(n_exp2)]
    fb = [
        {"financebench_id": f"financebench_id_{i:05d}", "question": f"fb q {i}", "answer": "r"}
        for i in range(n_fb)
    ]
    return measure_lib.question_pool(exp2, fb)


# --- sample ------------------------------------------------------------------


def test_measure_sample_is_stable_and_distinct() -> None:
    pool = _pool()
    assert len(pool) == 42
    first = [q["qid"] for q in measure_lib.sample_questions(pool, 20)]
    again = [q["qid"] for q in measure_lib.sample_questions(list(reversed(pool)), 20)]
    assert first == again
    assert len(set(first)) == 20
    assert [q["qid"] for q in measure_lib.sample_questions(pool, 5)] == first[:5]
    other = [q["qid"] for q in measure_lib.sample_questions(pool, 20, seed=1)]
    assert other != first


def test_measure_sample_refuses_a_limit_above_the_pool() -> None:
    with pytest.raises(ValueError, match="above"):
        measure_lib.sample_questions(_pool(2, 1), 4)


# --- answers stage: resume and failures --------------------------------------


def _result(text: str = "an answer", host: str = "hostA") -> dict:
    return {
        "status": "answered",
        "answer": text,
        "evidence": [{"text": "context one"}, {"text": "context two"}],
        "citations": [{"ordinal": 1}],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "reasoning_tokens": 5,
            "cost_usd": 0.0001,
            "calls": 1,
        },
        "sampling": {
            "chat": {
                "temperature": 0.0,
                "seed": 20261109,
                "host": host,
                "accepted": None,
                "host_in_list": True,
            }
        },
    }


class _Answerer:
    def __init__(self, fail: set[str] | None = None, text: str = "an answer") -> None:
        self.asked: list[str] = []
        self.fail = fail or set()
        self.text = text

    async def __call__(self, question: str) -> dict:
        self.asked.append(question)
        if question in self.fail:
            raise RuntimeError(f"boom while answering {question}")
        return _result(self.text)


def _opts(tmp_path: Path, stages: tuple[str, ...], resume: bool = False, prices=None):
    return measure_answers.Options(out_dir=tmp_path, stages=stages, resume=resume, prices=prices)


def test_answers20_resume_skips_done_rows(tmp_path: Path) -> None:
    questions = measure_lib.sample_questions(_pool(3, 2), 5)
    first = _Answerer()
    deps = measure_answers.Deps(answer=first)
    asyncio.run(measure_answers.run_stages(_opts(tmp_path, ("answers",)), deps, questions[:2]))
    assert len(first.asked) == 2

    again = _Answerer()
    deps = measure_answers.Deps(answer=again)
    asyncio.run(
        measure_answers.run_stages(_opts(tmp_path, ("answers",), resume=True), deps, questions)
    )
    assert again.asked == [q["question"] for q in questions[2:]]
    rows = measure_lib.read_rows(tmp_path / "answers20.jsonl")
    assert sorted(r["qid"] for r in rows) == sorted(q["qid"] for q in questions)


def test_answers20_without_resume_refuses_an_existing_file(tmp_path: Path) -> None:
    questions = measure_lib.sample_questions(_pool(2, 1), 3)
    deps = measure_answers.Deps(answer=_Answerer())
    asyncio.run(measure_answers.run_stages(_opts(tmp_path, ("answers",)), deps, questions))
    with pytest.raises(measure_lib.StageFileExistsError):
        asyncio.run(measure_answers.run_stages(_opts(tmp_path, ("answers",)), deps, questions))


def test_answers20_failed_answer_keeps_row_and_counts_in_denominator(tmp_path: Path) -> None:
    questions = measure_lib.sample_questions(_pool(2, 1), 3)
    bad = questions[1]["question"]
    deps = measure_answers.Deps(answer=_Answerer(fail={bad}))
    asyncio.run(
        measure_answers.run_stages(_opts(tmp_path, ("answers", "summary")), deps, questions)
    )
    rows = measure_lib.read_rows(tmp_path / "answers20.jsonl")
    assert len(rows) == 3
    failed = [r for r in rows if r["error"]]
    assert len(failed) == 1 and failed[0]["qid"] == questions[1]["qid"]
    assert "RuntimeError" in failed[0]["error"]
    summary = json.loads((tmp_path / "measure-summary.json").read_text(encoding="utf-8"))
    block = summary["answers"]
    assert block["n"] == 3 and block["errors"] == 1
    # Two answered rows of 100 input tokens, one failure of 0, over 3 rows.
    assert block["mean_input_tokens"] == pytest.approx(200 / 3, abs=1e-3)


# --- cost arithmetic and extrapolation ---------------------------------------


PRICES = {
    "deepseek/deepseek-v4.1-flash-1017": {
        "prompt_per_million": 0.10,
        "completion_per_million": 0.40,
    },
    "openai/gpt-oss-120b": {"prompt_per_million": 0.05, "completion_per_million": 0.25},
}


def _answer_row(qid: str, tin, tout, error: str = "") -> dict:
    return {
        "qid": qid,
        "input_tokens": tin,
        "output_tokens": tout,
        "reasoning_tokens": 0,
        "seconds": 1.0,
        "error": error,
        "host": "h",
    }


def _ragas_row(qid: str, per_metric: dict[str, tuple[int, int, int]]) -> dict:
    metrics = {
        name: {
            "score": 0.5,
            "calls": calls,
            "input_tokens": tin,
            "output_tokens": tout,
            "reasoning_tokens": 0,
            "seconds": 1.0,
            "error": "",
            "unreported_calls": 0,
        }
        for name, (calls, tin, tout) in per_metric.items()
    }
    return {"qid": qid, "error": "", "metrics": metrics}


def test_cost_arithmetic_on_hand_computed_numbers() -> None:
    answers = [
        _answer_row("a", 1000, 200),
        _answer_row("b", 3000, 600),
        _answer_row("c", None, None, error="RuntimeError: x"),
    ]
    ragas = [
        _ragas_row("a", {"faithfulness": (2, 2000, 400), "context_recall": (1, 1000, 100)}),
        _ragas_row("b", {"faithfulness": (2, 4000, 800), "context_recall": (1, 3000, 300)}),
    ]
    cost = measure_lib.cost_block(answers, ragas, PRICES)
    # Answering: 4000 in x 0.10/M + 800 out x 0.40/M = 0.00072 over 3 rows.
    assert cost["answer_per_answer_usd"] == pytest.approx(0.00024)
    # Faithfulness: 6000 x 0.05/M + 1200 x 0.25/M = 0.0006 over 2 rows = 0.0003.
    assert cost["ragas_per_metric_usd"]["faithfulness"] == pytest.approx(0.0003)
    # Context recall: 4000 x 0.05/M + 400 x 0.25/M = 0.0003 over 2 rows = 0.00015.
    assert cost["ragas_per_metric_usd"]["context_recall"] == pytest.approx(0.00015)
    assert cost["ragas_per_answer_usd"] == pytest.approx(0.00045)
    assert cost["total_per_answer_usd"] == pytest.approx(0.00069)
    assert cost["unpriced_answer_rows"] == 1


def test_cost_refuses_prices_without_the_model() -> None:
    with pytest.raises(KeyError, match="gpt-oss"):
        measure_lib.cost_block(
            [],
            [],
            {"deepseek/deepseek-v4.1-flash-1017": PRICES["deepseek/deepseek-v4.1-flash-1017"]},
        )


def test_cost_extrapolation_on_hand_computed_numbers() -> None:
    assert measure_lib.MAIN_QUESTIONS == 1080
    found = measure_lib.extrapolate(0.00024)
    assert found["answers"] == 6 * 1080 * 3 == 19440
    assert found["dollars"] == pytest.approx(4.6656)
    small = measure_lib.extrapolate(0.5, arms=2, questions=10, runs=3)
    assert small == {"answers": 60, "dollars": 30.0}


def test_cost_main_run_block_splits_reference_metrics() -> None:
    answers = [_answer_row("a", 1000, 200)]
    ragas = [_ragas_row("a", {"faithfulness": (1, 1000, 0), "context_recall": (1, 1000, 0)})]
    cost = measure_lib.cost_block(answers, ragas, PRICES)
    main = cost["main_run"]
    # Answering 0.00018 x 19440; faithfulness 0.00005 x 19440; recall 0.00005 x 6 x 857 x 3.
    assert main["answering"]["dollars"] == pytest.approx(0.00018 * 19440)
    assert main["ragas_reference_free"]["dollars"] == pytest.approx(0.00005 * 19440)
    assert main["ragas_reference"]["answers"] == 6 * 857 * 3
    assert main["ragas_reference"]["dollars"] == pytest.approx(0.00005 * 6 * 857 * 3)
    assert main["total_dollars"] == pytest.approx(
        main["answering"]["dollars"]
        + main["ragas_reference_free"]["dollars"]
        + main["ragas_reference"]["dollars"]
    )


def test_cost_load_prices_checks_fields(tmp_path: Path) -> None:
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"m": {"prompt_per_million": 1}}), encoding="utf-8")
    with pytest.raises(ValueError, match="completion_per_million"):
        measure_lib.load_prices(path)
    path.write_text(json.dumps(PRICES), encoding="utf-8")
    assert measure_lib.load_prices(path) == PRICES


# --- no text in any output file ----------------------------------------------


class _SentinelSeam:
    async def __call__(self, prompt: str) -> ChatReply:
        return ChatReply(
            text=f'{{"value": "{SENTINEL}"}}',
            input_tokens=10,
            output_tokens=2,
            reasoning_tokens=0,
            cost_usd=None,
            host="judgehost",
            host_in_list=True,
            temperature=0.0,
            seed=20261109,
        )


def _sentinel_metrics(seam: RecordingSeam) -> dict:
    async def score(sample: dict) -> float:
        await seam(f"judge {sample['question']} {sample['answer']} {sample['contexts']}")
        return 0.75

    async def boom(sample: dict) -> float:
        await seam(sample["reference"])
        raise ValueError(f"cannot parse {SENTINEL}")

    return {
        "faithfulness": score,
        "answer_relevancy": score,
        "context_precision": boom,
        "context_recall": score,
    }


def test_no_question_or_answer_text_in_any_output_file(tmp_path: Path) -> None:
    exp2 = [{"query": f"{SENTINEL} q{i}", "expected_answer": f"{SENTINEL} ref"} for i in range(3)]
    fb = [
        {
            "financebench_id": "financebench_id_1",
            "question": f"{SENTINEL} fb",
            "answer": f"{SENTINEL} fbref",
        }
    ]
    questions = measure_lib.sample_questions(measure_lib.question_pool(exp2, fb), 4)
    answerer = _Answerer(fail={questions[0]["question"]}, text=f"{SENTINEL} answer")

    def judge() -> tuple:
        seam = RecordingSeam(_SentinelSeam())
        return seam, _sentinel_metrics(seam), {"judge_model": "openai/gpt-oss-120b"}

    def ingest() -> list[dict]:
        return [{"file": "doc.pdf", "seconds": 1.0, "error": ""}]

    deps = measure_answers.Deps(
        answer=answerer, judge=judge, ingest=ingest, require_ragas=lambda: "0.4.3"
    )
    prices = tmp_path / "in" / "prices.json"
    prices.parent.mkdir()
    prices.write_text(json.dumps(PRICES), encoding="utf-8")
    out = tmp_path / "out"
    code = asyncio.run(
        measure_answers.run_stages(
            _opts(out, measure_answers.STAGES, prices=prices), deps, questions
        )
    )
    assert code == 0
    files = [p for p in out.rglob("*") if p.is_file()]
    assert {p.name for p in files} >= {
        "ingest.jsonl",
        "answers20.jsonl",
        "ragas20.jsonl",
        "measure-summary.json",
    }
    for path in files:
        assert SENTINEL not in path.read_text(encoding="utf-8"), path.name
    ragas = measure_lib.read_rows(out / "ragas20.jsonl")
    judged = [r for r in ragas if not r["error"]]
    assert judged and all(
        r["metrics"]["context_precision"]["error"] == "ValueError" for r in judged
    )


# --- missing Ragas -----------------------------------------------------------


def test_ragas_missing_stops_with_plain_message_before_any_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "ragas", None)  # import ragas now raises ImportError
    import ragas_stage

    answerer = _Answerer()
    deps = measure_answers.Deps(answer=answerer, require_ragas=ragas_stage.require_ragas)
    questions = measure_lib.sample_questions(_pool(2, 1), 3)
    code = asyncio.run(
        measure_answers.run_stages(_opts(tmp_path, measure_answers.STAGES), deps, questions)
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "Ragas 0.4.3 is not installed" in err
    assert "uv pip install --python /workspace/ragas-venv/bin/python" in err
    assert answerer.asked == []
    assert not (tmp_path / "answers20.jsonl").exists()


def test_ragas_missing_leaves_the_other_stages_working(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "ragas", None)
    import ragas_stage

    deps = measure_answers.Deps(
        answer=_Answerer(), require_ragas=ragas_stage.require_ragas, ingest=lambda: []
    )
    questions = measure_lib.sample_questions(_pool(2, 1), 3)
    code = asyncio.run(
        measure_answers.run_stages(
            _opts(tmp_path, ("ingest", "answers", "summary")), deps, questions
        )
    )
    assert code == 0
    assert len(measure_lib.read_rows(tmp_path / "answers20.jsonl")) == 3
    summary = json.loads((tmp_path / "measure-summary.json").read_text(encoding="utf-8"))
    assert summary["ragas"]["n"] == 0 and summary["cost"] is None


def test_measure_parse_stages_rejects_unknown_names() -> None:
    assert measure_answers.parse_stages("answers,summary") == ("answers", "summary")
    with pytest.raises(SystemExit):
        measure_answers.parse_stages("answers,judge")


def test_live_ingest_runs_inside_the_running_event_loop() -> None:
    """Pod run 2026-11-10: the ingest dep called Exp 48's ingest_documents, which calls
    asyncio.run(), from inside run_stages' event loop. It must run off that loop."""
    import asyncio

    import measure_live

    def part_a_ingest() -> list[dict]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return [{"file": "a.pdf", "seconds": 1.0, "error": None}]
        raise RuntimeError("asyncio.run() cannot be called from a running event loop")

    async def from_a_running_loop() -> list[dict]:
        return measure_live.run_ingest_off_loop(part_a_ingest)

    assert asyncio.run(from_a_running_loop()) == [{"file": "a.pdf", "seconds": 1.0, "error": None}]


def test_append_after_a_torn_last_line_keeps_every_later_row_readable(tmp_path: Path) -> None:
    """A crash mid-write leaves a line with no newline; the next append must not join it."""
    path = tmp_path / "rows.jsonl"
    path.write_text('{"qid": "a"}\n{"qid": "b", "ans', encoding="utf-8")
    measure_lib.append_row(path, {"qid": "b"})
    measure_lib.append_row(path, {"qid": "c"})
    assert [row["qid"] for row in measure_lib.read_rows(path)] == ["a", "b", "c"]
