# ruff: noqa: S101
"""Experiment 35 Ragas stage: judge settings, router session, correctness and provenance.

Tasks 7.3, 7.4, 14.5 and 15.9. No Ragas, no router, no network.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tests._exp35_ragas_fixtures import (
    EMBED_FILE,
    JUDGE,
    Router,
    Script,
    answer_row,
    built,
    ctx,
    parts,
    plan,
    ragas35,
    ragas_stage,
    rows,
    run,
    write_answers,
)


def _setup(tmp_path: Path, qids: list[str]) -> Path:
    run_dir = tmp_path / "run1"
    write_answers(run_dir, [answer_row(q) for q in qids])
    return run_dir


# --- task 7.3 -----------------------------------------------------------------


def test_the_arguments_parse() -> None:
    parser = argparse.ArgumentParser()
    ragas35.add_arguments(parser)
    args = parser.parse_args(
        ["--ragas-host", "hostj", "--ragas-venv", "/v", "--ragas-concurrency", "4"]
    )
    assert (args.ragas_host, args.ragas_venv, args.ragas_concurrency) == ("hostj", Path("/v"), 4)
    assert parser.parse_args([]).ragas_host == ""


def test_a_missing_host_refuses_before_any_call(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script, router = Script(), Router()
    with pytest.raises(ragas35.RagasRefused, match="--ragas-host is required"):
        run(ctx(run_dir, ["q1"], router, ragas_host=""), parts(script, router))
    assert script.prompts == [] and router.opened == 0


def test_a_host_or_setting_missing_from_the_plan_refuses(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script, router = Script(), Router()
    with pytest.raises(ragas35.RagasRefused, match="hostk.*hostj|hostj.*hostk"):
        run(ctx(run_dir, ["q1"], router, ragas_host="hostk"), parts(script, router))
    no_seed = plan()
    del no_seed["runtime"]["references"][0]["seed"]
    with pytest.raises(ragas35.RagasRefused, match="seed"):
        run(ctx(run_dir, ["q1"], router), parts(script, router), no_seed)
    assert script.prompts == []


def test_the_dry_run_prints_the_judge_settings_and_version_and_sends_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script, router = Script(), Router()
    assert run(ctx(run_dir, ["q1"], router, dry_run=True), parts(script, router)) == 0
    out = capsys.readouterr().out
    for text in ("openai/gpt-oss-120b", "hostj", "low", "0.0", "20261109", "0.4.3"):
        assert text in out
    assert script.prompts == [] and router.opened == 0
    assert not (run_dir / "ragas.jsonl").exists()


def test_recorded_judge_settings_and_seed_equal_the_plan(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script, router = Script(), Router()
    p = plan(seed=777, temperature=0.5)
    judge = lambda settings: (script, built(seed=777, temperature=0.5))  # noqa: E731
    assert run(ctx(run_dir, ["q1"], router), parts(script, router, judge=judge), p) == 0
    row = rows(run_dir)[0]
    assert (row["judge_model"], row["judge_host"], row["reasoning"]) == (
        "openai/gpt-oss-120b",
        "hostj",
        "low",
    )
    assert (row["temperature"], row["seed"]) == (0.5, 777)
    marker = json.loads((run_dir / ".done-ragas.json").read_text())
    assert marker["judge"]["seed"] == 777 and marker["ragas_version"] == "0.4.3"


@pytest.mark.parametrize(
    "change", [{"seed": 20261101}, {"temperature": 1.0}, {"model": "x"}, {"host": "other"}]
)
def test_a_built_judge_that_differs_from_the_plan_refuses(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script, router = Script(), Router()
    judge = lambda settings: (script, built(**change))  # noqa: E731
    name = next(iter(change))
    with pytest.raises(ragas35.RagasRefused, match=name):
        run(ctx(run_dir, ["q1"], router), parts(script, router, judge=judge))
    assert script.prompts == [] and router.opened == 0


def test_built_judge_values_are_read_from_the_llm_object() -> None:
    llm = SimpleNamespace(
        model="openai/gpt-oss-120b",
        temperature=0.0,
        additional_kwargs={
            "seed": 20261109,
            "extra_body": {"reasoning": {"effort": "low"}, "provider": {"only": ["hostj"]}},
        },
    )
    assert ragas35.built_judge_values(llm) == built()


# --- task 7.4 -----------------------------------------------------------------


def test_one_router_session_for_the_4b_file_spans_every_embedding_call(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, ["q1", "q2", "q3"])
    script, router = Script(), Router()
    assert (
        run(ctx(run_dir, ["q1", "q2", "q3"], router, ragas_concurrency=2), parts(script, router))
        == 0
    )
    assert router.files == [EMBED_FILE]
    assert (router.opened, router.closed) == (1, 1)
    assert router.events[0] == "open" and router.events[-1] == "close"
    assert router.events.count("embed") == 6


def test_the_runtime_check_runs_before_the_first_paid_call_and_a_wrong_build_stops(
    tmp_path: Path,
) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script, router = Script(), Router()
    script.events = router.events
    seen: list[tuple[str, str]] = []

    def check(entry: dict, base_url: str) -> dict:
        seen.append((entry["file"], base_url))
        router.events.append("check")
        return {"build": 11941, "sha256": "a" * 64}

    c = ctx(run_dir, ["q1"], router)
    c.runtime_check = check
    assert run(c, parts(script, router)) == 0
    assert seen == [(EMBED_FILE, "http://127.0.0.1:18080/v1")]
    assert router.events.index("check") < router.events.index("chat")

    class WrongBuild(RuntimeError):
        pass

    def wrong(entry: dict, base_url: str) -> dict:
        raise WrongBuild("build 11000, plan 11941")

    other = _setup(tmp_path / "b", ["q1"])
    script = Script()
    c = ctx(other, ["q1"], router)
    c.runtime_check = wrong
    with pytest.raises(WrongBuild):
        run(c, parts(script, router))
    assert script.prompts == []


def test_the_done_marker_records_the_embedding_endpoint_build_and_hash(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script, router = Script(), Router()
    assert run(ctx(run_dir, ["q1"], router), parts(script, router)) == 0
    marker = json.loads((run_dir / ".done-ragas.json").read_text())
    assert marker["embedding"] == {
        "endpoint": "http://127.0.0.1:18080/v1",
        "file": EMBED_FILE,
        "build": 11941,
        "sha256": "a" * 64,
    }
    assert rows(run_dir)[0]["embedding_endpoint"] == "http://127.0.0.1:18080/v1"


# --- task 14.5 ----------------------------------------------------------------


def test_the_stage_scores_five_metrics_and_records_the_weights(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script, router = Script(), Router()
    assert run(ctx(run_dir, ["q1"], router), parts(script, router)) == 0
    assert sorted(rows(run_dir)[0]["metrics"]) == sorted(ragas35.METRICS)
    assert "ragas_answer_correctness" in ragas35.METRICS
    marker = json.loads((run_dir / ".done-ragas.json").read_text())
    assert marker["weights"] == {"answer_correctness": [0.75, 0.25]}


def test_no_reference_means_not_judged_and_no_call(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script, router = Script(), Router()
    c = ctx(run_dir, ["q1"], router)
    c.questions[0].reference = ""
    assert run(c, parts(script, router)) == 0
    metrics = rows(run_dir)[0]["metrics"]
    for name in ("ragas_answer_correctness", "ragas_context_precision", "ragas_context_recall"):
        assert metrics[name] == {"score": None, "not_judged": "no reference answer", "calls": 0}
    assert {p.split("|")[0] for p in script.prompts} == {
        "ragas_faithfulness",
        "ragas_answer_relevancy",
    }


def test_resume_skips_saved_rows(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, ["q1", "q2"])
    router = Router()
    assert run(ctx(run_dir, ["q1", "q2"], router), parts(Script(), router)) == 0
    (run_dir / ".done-ragas.json").unlink()
    script = Script()
    c = ctx(run_dir, ["q1", "q2"], router)
    c.resume = True
    assert run(c, parts(script, router)) == 0
    assert script.prompts == [] and len(rows(run_dir)) == 2


class _Result:
    def __init__(self, value: float) -> None:
        self.value = value


def _fake_collections(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict]]:
    seen: dict[str, list[dict]] = {}

    def metric(name: str, **extra: Any) -> type:
        class Metric:
            def __init__(self, **kwargs: Any) -> None:
                seen.setdefault(f"{name}.init", []).append(kwargs)
                for key, value in extra.items():
                    setattr(self, key, value)

            async def ascore(self, **kwargs: Any) -> _Result:
                seen.setdefault(name, []).append(kwargs)
                return _Result(0.5)

        return Metric

    module = type(sys)("ragas.metrics.collections")
    for name in ("Faithfulness", "AnswerRelevancy", "ContextPrecision", "ContextRecall"):
        setattr(module, name, metric(name))
    module.AnswerCorrectness = metric("AnswerCorrectness", weights=[0.75, 0.25])
    monkeypatch.setitem(sys.modules, "ragas.metrics.collections", module)
    monkeypatch.setattr(ragas_stage, "ragas_llm", lambda seam: ("llm", seam))
    return seen


def test_answer_correctness_gets_question_answer_and_reference_never_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _fake_collections(monkeypatch)
    seam = object()
    metrics, weights = ragas35.main_metrics(seam, "EMB")
    assert sorted(metrics) == sorted(ragas35.METRICS)
    sample = {"qid": "q", "question": "Q?", "answer": "A.", "contexts": ["c"], "reference": "R."}
    assert asyncio.run(metrics["ragas_answer_correctness"](sample)) == 0.5
    assert seen["AnswerCorrectness"] == [{"user_input": "Q?", "response": "A.", "reference": "R."}]
    assert seen["AnswerCorrectness.init"] == [{"llm": ("llm", seam), "embeddings": "EMB"}]
    assert weights == {"answer_correctness": [0.75, 0.25]}


# --- task 15.9 ----------------------------------------------------------------


def test_the_seam_records_the_returned_model_and_provider_per_call() -> None:
    seam = ragas_stage.RecordingSeam(Script(), metric="ragas_faithfulness")
    asyncio.run(seam("ragas_faithfulness|q1"))
    assert seam.calls[0]["model_returned"] == "openai/gpt-oss-120b"
    assert seam.calls[0]["provider_returned"] == "hostj"


def test_the_omrs_seam_reads_model_and_provider_from_the_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import omrs.engine_answer as engine_answer

    monkeypatch.setattr(engine_answer, "reply_reader", lambda provider: lambda raw: None)
    monkeypatch.setattr(engine_answer, "sampling_record", lambda llm, provider, raw: {})

    class _LLM:
        async def acomplete(self, prompt: str) -> Any:
            raw = {"model": "openai/gpt-oss-120b-2026", "provider": "HostJ"}
            return SimpleNamespace(text="ok", raw=raw)

    reply = asyncio.run(ragas_stage.omrs_chat_seam(_LLM())("p"))
    assert (reply.model_returned, reply.provider_returned) == ("openai/gpt-oss-120b-2026", "HostJ")


def test_a_ragas_row_records_the_returned_models_and_providers(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    script, router = Script(), Router()
    assert run(ctx(run_dir, ["q1"], router), parts(script, router)) == 0
    row = rows(run_dir)[0]
    assert row["model_returned"] == ["openai/gpt-oss-120b"]
    assert row["provider_returned"] == ["hostj"]
    assert row["judge_model"] == JUDGE["model"]
