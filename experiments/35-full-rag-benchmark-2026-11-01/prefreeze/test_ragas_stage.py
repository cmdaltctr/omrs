# ruff: noqa: S101
"""Tests for the Ragas stage seam and per-metric accounting. No Ragas, no network."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ragas_stage  # noqa: E402
from ragas_stage import ChatReply, RecordingSeam  # noqa: E402


class _Verdict(BaseModel):
    verdict: int


class _Scripted:
    """Return the scripted texts in order; each call reports fixed tokens and a host."""

    def __init__(self, texts: list[str], tokens: tuple[int, int] = (100, 10)) -> None:
        self.texts = list(texts)
        self.prompts: list[str] = []
        self.tokens = tokens

    async def __call__(self, prompt: str) -> ChatReply:
        self.prompts.append(prompt)
        return ChatReply(
            text=self.texts.pop(0),
            input_tokens=self.tokens[0],
            output_tokens=self.tokens[1],
            reasoning_tokens=3,
            cost_usd=None,
            host="hostJ",
            host_in_list=True,
            temperature=0.0,
            seed=20261109,
        )


def test_ragas_structured_reply_parses_fenced_json_and_asks_for_the_schema() -> None:
    send = _Scripted(['```json\n{"verdict": 1}\n```'])
    seam = RecordingSeam(send)
    found = asyncio.run(ragas_stage.structured(seam, "Is it so?", _Verdict))
    assert found == _Verdict(verdict=1)
    assert '"verdict"' in send.prompts[0] and "JSON schema" in send.prompts[0]
    assert len(seam.calls) == 1 and seam.calls[0]["host"] == "hostJ"


def test_ragas_structured_reply_retries_once_and_records_both_calls() -> None:
    seam = RecordingSeam(_Scripted(["not json", '{"verdict": 0}']))
    assert asyncio.run(ragas_stage.structured(seam, "p", _Verdict)) == _Verdict(verdict=0)
    assert len(seam.calls) == 2
    seam = RecordingSeam(_Scripted(["bad", "still bad"]))
    with pytest.raises(ragas_stage.StructuredReplyError):
        asyncio.run(ragas_stage.structured(seam, "p", _Verdict))
    assert len(seam.calls) == 2


def test_ragas_judge_counts_calls_tokens_and_hosts_per_metric() -> None:
    seam = RecordingSeam(_Scripted(["x"] * 10, tokens=(200, 20)))

    def calling(n: int):
        async def score(sample: dict) -> float:
            for _ in range(n):
                await seam("prompt")
            return 0.5

        return score

    async def failing(sample: dict) -> float:
        await seam("prompt")
        raise RuntimeError("judge reply could not be used")

    metrics = {
        "faithfulness": calling(2),
        "answer_relevancy": calling(3),
        "context_precision": failing,
        "context_recall": calling(1),
    }
    sample = {"qid": "q1", "question": "q", "answer": "a", "contexts": ["c"], "reference": "r"}
    row = asyncio.run(ragas_stage.judge_answer(sample, seam, metrics, header={"seed": 1}))
    assert row["qid"] == "q1" and row["seed"] == 1 and row["error"] == ""
    got = row["metrics"]
    assert got["faithfulness"]["calls"] == 2 and got["faithfulness"]["input_tokens"] == 400
    assert got["answer_relevancy"]["calls"] == 3 and got["answer_relevancy"]["output_tokens"] == 60
    assert got["context_precision"]["error"] == "RuntimeError"
    assert got["context_precision"]["score"] is None and got["context_precision"]["calls"] == 1
    assert got["context_recall"]["score"] == 0.5
    assert len(row["calls"]) == 7
    assert {c["host"] for c in row["calls"]} == {"hostJ"}
    assert {c["metric"] for c in row["calls"]} == set(metrics)


def test_ragas_judge_skips_reference_metrics_without_a_reference() -> None:
    seam = RecordingSeam(_Scripted(["x"] * 4))

    async def score(sample: dict) -> float:
        await seam("prompt")
        return 1.0

    metrics = dict.fromkeys(ragas_stage.METRICS, score)
    sample = {"qid": "q", "question": "q", "answer": "a", "contexts": [], "reference": ""}
    row = asyncio.run(ragas_stage.judge_answer(sample, seam, metrics, header={}))
    assert row["metrics"]["context_recall"]["error"] == "no reference answer"
    assert row["metrics"]["context_precision"]["calls"] == 0
    assert row["metrics"]["faithfulness"]["calls"] == 1


def test_ragas_nan_score_is_an_error() -> None:
    seam = RecordingSeam(_Scripted([]))

    async def nan(sample: dict) -> float:
        return float("nan")

    sample = {"qid": "q", "question": "q", "answer": "a", "contexts": [], "reference": "r"}
    row = asyncio.run(ragas_stage.judge_answer(sample, seam, {"faithfulness": nan}, header={}))
    assert row["metrics"]["faithfulness"] == {
        **row["metrics"]["faithfulness"],
        "score": None,
        "error": "score is NaN",
    }


def test_ragas_seam_failure_records_type_only() -> None:
    class _Fails:
        async def __call__(self, prompt: str) -> ChatReply:
            raise ConnectionError(f"lost while sending {prompt}")

    seam = RecordingSeam(_Fails(), metric="faithfulness")
    with pytest.raises(ConnectionError):
        asyncio.run(seam("SECRET PROMPT"))
    assert seam.calls == [
        {"metric": "faithfulness", "error": "ConnectionError", "seconds": seam.calls[0]["seconds"]}
    ]


def test_ragas_venv_without_site_packages_gives_the_install_message(tmp_path: Path) -> None:
    with pytest.raises(ragas_stage.RagasMissingError, match="uv venv /workspace/ragas-venv"):
        ragas_stage.ragas_site(tmp_path)


def test_ragas_wrong_version_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = type(sys)("ragas")
    fake.__version__ = "0.3.9"
    monkeypatch.setitem(sys.modules, "ragas", fake)
    with pytest.raises(ragas_stage.RagasMissingError, match="0.3.9"):
        ragas_stage.require_ragas()
