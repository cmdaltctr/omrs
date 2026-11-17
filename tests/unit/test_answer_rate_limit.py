"""A rate-limited answer or judge call is a typed result (Exp 35 tasks 0.1 to 0.3, design D25).

Task 0.1 tests the classifier in ``omrs.core.answer.rate_limits``. Task 0.2
tests the ``rate_limited`` and ``verification_rate_limited`` records through
``Engine.answer`` on the standard path and on the user-profile graph path.
Task 0.3 tests the short HTTP 402 retry with an injected sleep, through the
core ``answer()`` operation.

No test reaches a network: every model is a fake that raises a stub error or
a real ``openai`` error built on a local ``httpx.Response``.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import httpx
import openai
import pytest
from tests.fixtures.pipeline_parity.answer.harness import (
    QUERY,
    case_by_name,
    case_rows,
    case_settings,
)
from tests.unit.test_answer_graph_adapters_support import FakeLLM
from tests.unit.test_engine_pipelines_support import Factory
from tests.unit.test_engine_profiles_support import COLLECTION, PROFILE, make_env, tagged_engine
from tests.unit.test_pipeline_templates_parity import _store_rows

RATE_LIMIT_ERROR = (
    "Generation failed: the answer model's provider is limiting requests (HTTP 429). "
    "Wait, then ask again."
)
_REPLY = "The tower is 100 metres tall [1]."


class _StubStatusError(Exception):
    """A provider error with a status code and response headers (duck typing)."""

    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        super().__init__(f"HTTP {status}")
        self.status_code = status
        self.response = SimpleNamespace(headers=dict(headers or {}))


def _openai_error(status: int, headers: dict[str, str] | None = None) -> Exception:
    """Return the real ``openai`` error the client raises for *status*."""
    request = httpx.Request("POST", "https://provider.invalid/v1/chat/completions")
    response = httpx.Response(status, headers=headers or {}, request=request)
    if status == 429:
        return openai.RateLimitError("rate limited upstream", response=response, body=None)
    return openai.APIStatusError("payment required", response=response, body=None)


class _Script:
    """Async seam that raises or replies per script item; the last item repeats."""

    def __init__(self, *items: Any) -> None:
        self.items = list(items)
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        item = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(item, BaseException):
            raise item
        return str(item)


@pytest.fixture
def rate_limits() -> ModuleType:
    """Import the module under test lazily, so the 0.2 tests run on today's code."""
    return importlib.import_module("omrs.core.answer.rate_limits")


# ── Task 0.1: classifier ──────────────────────────────────────────────────


@pytest.mark.parametrize("status", [429, 402])
def test_a_429_or_402_is_a_rate_limit(rate_limits: ModuleType, status: int) -> None:
    record = rate_limits.classify_rate_limit(_StubStatusError(status, {"Retry-After": "7"}))
    assert record is not None and record.http_status == status


@pytest.mark.parametrize(
    "exc", [_StubStatusError(500), TimeoutError("timed out"), ValueError("bad value")]
)
def test_other_errors_are_not_a_rate_limit(rate_limits: ModuleType, exc: Exception) -> None:
    assert rate_limits.classify_rate_limit(exc) is None


@pytest.mark.parametrize(
    ("headers", "seconds"),
    [({"Retry-After": "7"}, 7.0), ({"retry-after-ms": "1500"}, 1.5), ({}, None)],
)
def test_the_wait_comes_from_the_headers(
    rate_limits: ModuleType, headers: dict[str, str], seconds: float | None
) -> None:
    record = rate_limits.classify_rate_limit(_StubStatusError(429, headers))
    assert record.retry_after_seconds == seconds


@pytest.mark.parametrize(
    ("status", "headers", "kind"),
    [
        (429, {}, "rate_limit"),
        (402, {"Retry-After": "5"}, "rate_limit"),
        (402, {}, "out_of_credit"),
    ],
)
def test_the_kind(rate_limits: ModuleType, status: int, headers: dict[str, str], kind: str) -> None:
    assert rate_limits.classify_rate_limit(_StubStatusError(status, headers)).kind == kind


def test_a_date_form_retry_after_on_a_402_is_a_wait_not_out_of_credit(
    rate_limits: ModuleType,
) -> None:
    """RFC 9110 lets Retry-After be an HTTP-date; a 402 with one is a wait (issue 214)."""
    when = datetime.now(UTC) + timedelta(seconds=600)
    header = {"Retry-After": format_datetime(when, usegmt=True)}
    record = rate_limits.classify_rate_limit(_StubStatusError(402, header))
    assert record.kind == "rate_limit"
    assert 590 <= record.retry_after_seconds <= 600


def test_a_past_date_form_retry_after_is_a_zero_wait(rate_limits: ModuleType) -> None:
    past = format_datetime(datetime.now(UTC) - timedelta(hours=1), usegmt=True)
    record = rate_limits.classify_rate_limit(_StubStatusError(402, {"Retry-After": past}))
    assert (record.kind, record.retry_after_seconds) == ("rate_limit", 0.0)


def test_real_openai_errors_classify(rate_limits: ModuleType) -> None:
    limited = rate_limits.classify_rate_limit(_openai_error(429, {"retry-after": "7"}))
    empty = rate_limits.classify_rate_limit(_openai_error(402))
    assert limited.as_dict() == {
        "kind": "rate_limit",
        "http_status": 429,
        "retry_after_seconds": 7.0,
    }
    assert empty.as_dict() == {
        "kind": "out_of_credit",
        "http_status": 402,
        "retry_after_seconds": None,
    }


# ── Task 0.2: typed result on both answering paths ────────────────────────


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


async def _engine_answer(
    tmp_path: Path, effective_settings: Any, tag: str, complete: Any, judge: Any = None
) -> dict[str, Any]:
    """Run ``Engine.answer`` on a collection tagged *tag* with the given fake seams."""
    case = case_by_name("verification_supported" if judge else "ok_single_citation")
    settings = case_settings(effective_settings(), case)
    env = make_env(tmp_path / tag, effective_settings)
    engine = tagged_engine(
        env,
        settings,
        _store_rows(case_rows(case)),
        tag,
        env_overrides={"RETRIEVAL__RERANK_ENABLED": "false"},
        answer_llm_factory=Factory(FakeLLM(complete)),
        verify_llm_factory=Factory(FakeLLM(judge) if judge else None),
    )
    return await engine.answer(QUERY, collection_name=COLLECTION, include_diagnostics=True)


@pytest.mark.parametrize("tag", ["documents", PROFILE])
async def test_a_429_is_a_typed_generation_error(
    tag: str, tmp_path: Path, effective_settings: Any
) -> None:
    seam = _Script(_openai_error(429, {"Retry-After": "7"}))
    result = await _engine_answer(tmp_path, effective_settings, tag, seam)
    assert (result["status"], result["failure_stage"], result["answer"]) == (
        "error",
        "generation",
        None,
    )
    assert result["evidence"], "the evidence is kept"
    assert result["rate_limited"] == {
        "kind": "rate_limit",
        "http_status": 429,
        "retry_after_seconds": 7.0,
    }
    assert result["error"] == RATE_LIMIT_ERROR


@pytest.mark.parametrize("tag", ["documents", PROFILE])
async def test_a_402_without_a_wait_is_out_of_credit(
    tag: str, tmp_path: Path, effective_settings: Any
) -> None:
    result = await _engine_answer(tmp_path, effective_settings, tag, _Script(_openai_error(402)))
    assert result["rate_limited"] == {
        "kind": "out_of_credit",
        "http_status": 402,
        "retry_after_seconds": None,
    }
    assert "Top up" in result["error"] and "out of credit" in result["error"]


@pytest.mark.parametrize("tag", ["documents", PROFILE])
async def test_another_failure_keeps_its_shape(
    tag: str, tmp_path: Path, effective_settings: Any
) -> None:
    seam = _Script(ConnectionError("model endpoint down"))
    result = await _engine_answer(tmp_path, effective_settings, tag, seam)
    assert "rate_limited" not in result
    assert result["error"] == "Generation failed: ConnectionError: model endpoint down"


@pytest.mark.parametrize("tag", ["documents", PROFILE])
async def test_a_rate_limited_judge_keeps_the_answer(
    tag: str, tmp_path: Path, effective_settings: Any
) -> None:
    judge = _Script(_openai_error(429, {"Retry-After": "30"}))
    result = await _engine_answer(tmp_path, effective_settings, tag, _Script(_REPLY), judge)
    assert (result["status"], result["answer"]) == ("ok", _REPLY)
    assert result["verification_rate_limited"] == {
        "kind": "rate_limit",
        "http_status": 429,
        "retry_after_seconds": 30.0,
    }
    assert "limiting requests" in result["verification_skipped"]
    assert "RateLimitError" not in result["verification_skipped"]


@pytest.mark.parametrize("tag", ["documents", PROFILE])
async def test_a_judge_out_of_credit_names_the_top_up(
    tag: str, tmp_path: Path, effective_settings: Any
) -> None:
    judge = _Script(_openai_error(402))
    result = await _engine_answer(tmp_path, effective_settings, tag, _Script(_REPLY), judge)
    assert result["verification_rate_limited"]["kind"] == "out_of_credit"
    assert "Top up the judge provider account" in result["verification_skipped"]


@pytest.mark.parametrize("tag", ["documents", PROFILE])
async def test_another_judge_failure_keeps_todays_reason(
    tag: str, tmp_path: Path, effective_settings: Any
) -> None:
    judge = _Script(ConnectionError("judge network down"))
    result = await _engine_answer(tmp_path, effective_settings, tag, _Script(_REPLY), judge)
    assert "verification_rate_limited" not in result
    assert result["verification_skipped"] == (
        "verification failed: ConnectionError: judge network down"
    )


# ── Task 0.3: short HTTP 402 retry ────────────────────────────────────────


@pytest.fixture
def waits(rate_limits: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace the retry sleep; return the list of waits it was asked for."""
    seen: list[float] = []

    async def _sleep(seconds: float) -> None:
        seen.append(seconds)

    monkeypatch.setattr(rate_limits, "sleep", _sleep)
    return seen


async def _core_answer(effective_settings: Any, complete: Any, judge: Any = None) -> dict:
    """Run the core ``answer()`` operation on pre-fetched rows."""
    from omrs.core.answer import answer

    case = case_by_name("verification_supported" if judge else "ok_single_citation")
    return await answer(
        QUERY,
        complete=complete,
        verify_complete=judge,
        rows=case_rows(case),
        include_diagnostics=True,
        effective_settings=case_settings(effective_settings(), case),
    )


async def test_a_short_402_wait_then_success_is_ok(
    waits: list[float], effective_settings: Any
) -> None:
    seam = _Script(_openai_error(402, {"Retry-After": "5"}), _REPLY)
    result = await _core_answer(effective_settings, seam)
    assert result["status"] == "ok" and "rate_limited" not in result
    assert (waits, len(seam.prompts)) == ([5.0], 2)
    assert result["diagnostics"]["completion_calls"] == 1, "rounds, not attempts"


async def test_a_short_402_wait_stops_after_three_attempts(
    waits: list[float], effective_settings: Any
) -> None:
    seam = _Script(_openai_error(402, {"Retry-After": "5"}))
    result = await _core_answer(effective_settings, seam)
    assert (len(seam.prompts), waits) == (3, [5.0, 5.0])
    assert result["rate_limited"] == {
        "kind": "rate_limit",
        "http_status": 402,
        "retry_after_seconds": 5.0,
    }
    assert result["diagnostics"]["completion_calls"] == 1, "rounds, not attempts"


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (_openai_error(402, {"Retry-After": "120"}), "rate_limit"),
        (_openai_error(402), "out_of_credit"),
        (_openai_error(429, {"Retry-After": "5"}), "rate_limit"),
    ],
)
async def test_no_retry_for_a_long_wait_no_wait_or_a_429(
    waits: list[float], effective_settings: Any, error: Exception, kind: str
) -> None:
    seam = _Script(error)
    result = await _core_answer(effective_settings, seam)
    assert (len(seam.prompts), waits) == (1, [])
    assert result["status"] == "error" and result["rate_limited"]["kind"] == kind


async def test_a_plain_judge_seam_follows_the_402_rule(
    waits: list[float], effective_settings: Any
) -> None:
    judge = _Script(_openai_error(402, {"Retry-After": "5"}), "supported")
    result = await _core_answer(effective_settings, _Script(_REPLY), judge)
    assert result.get("verified") is True and "verification_rate_limited" not in result
    assert (waits, len(judge.prompts)) == ([5.0], 2)


class _JudgeLLM:
    """A judge LLM whose ``acomplete`` follows a :class:`_Script`."""

    model = "z-ai/glm-5.3"

    def __init__(self, script: _Script) -> None:
        self.script = script

    async def acomplete(self, prompt: str, **_kwargs: Any) -> Any:
        return SimpleNamespace(text=await self.script(prompt), raw=None)


async def test_the_server_judge_follows_the_402_rule(
    waits: list[float], effective_settings: Any
) -> None:
    """The ``chat`` judge that ``Engine.answer`` builds is a typed judge (R1-01)."""
    from omrs.engine_answer import build_verifier

    script = _Script(_openai_error(402, {"Retry-After": "5"}), "supported")
    base = effective_settings()
    effective = base.model_copy(
        update={"answer": base.answer.model_copy(update={"verify_claims": True})}
    )
    judge, reason = build_verifier(effective, lambda _block: _JudgeLLM(script), str)
    assert reason is None

    result = await _core_answer(effective_settings, _Script(_REPLY), judge)
    assert result.get("verified") is True and "verification_rate_limited" not in result
    assert (waits, len(script.prompts)) == ([5.0], 2)
