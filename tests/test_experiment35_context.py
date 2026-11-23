"""Experiment 35 ``context35.py``: the answer model's context length (task 14.1a).

The OpenRouter models reply is stubbed. No test calls OpenRouter.
"""

from __future__ import annotations

import json

import pytest
from tests._exp35_fixtures import load

context35 = load("context35")
MODEL = "deepseek/deepseek-v4.1-flash-1017"


def _reply(length: object, model: str = MODEL) -> dict:
    other = {"id": "other/model", "context_length": 8_192}
    return {"data": [other, {"id": model, "context_length": length, "name": "x"}]}


def test_the_answer_model_is_the_pinned_one() -> None:
    assert context35.MODEL == MODEL
    assert context35.MIN_CONTEXT_TOKENS == 65_536


@pytest.mark.parametrize("length", [65_536, 131_072, 1_000_000])
def test_a_length_at_or_above_the_floor_is_returned(length: int) -> None:
    assert context35.context_length(_reply(length)) == length


@pytest.mark.parametrize("length", [65_535, 32_768, 0])
def test_a_length_below_the_floor_is_refused_with_both_numbers(length: int) -> None:
    with pytest.raises(context35.ContextLengthError, match=rf"{length}.*65,536"):
        context35.context_length(_reply(length))


def test_a_reply_without_the_model_is_refused_and_names_it() -> None:
    reply = {"data": [{"id": "other/model", "context_length": 200_000}]}
    with pytest.raises(context35.ContextLengthError, match=MODEL):
        context35.context_length(reply)


@pytest.mark.parametrize("length", [None, "131072", True, 1.5])
def test_a_missing_or_malformed_length_is_refused(length: object) -> None:
    with pytest.raises(context35.ContextLengthError, match="context_length"):
        context35.context_length(_reply(length))


def test_a_reply_that_is_not_a_models_list_is_refused() -> None:
    with pytest.raises(context35.ContextLengthError, match="data"):
        context35.context_length({"error": "nope"})


def test_check_reads_the_reply_through_the_fetch_seam_and_records_value_and_date() -> None:
    calls: list[str] = []

    def fetch(url: str) -> dict:
        calls.append(url)
        return _reply(131_072)

    record = context35.check(fetch=fetch, today="2026-11-23")
    assert calls == [context35.MODELS_URL]
    assert record == {
        "model": MODEL,
        "context_length": 131_072,
        "minimum": 65_536,
        "checked": "2026-11-23",
        "source": context35.MODELS_URL,
    }


def test_main_prints_the_record_and_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    code = context35.main([], fetch=lambda _url: _reply(131_072), today="2026-11-23")
    assert code == 0
    assert json.loads(capsys.readouterr().out)["context_length"] == 131_072


def test_main_exits_2_with_the_reason_when_the_length_is_too_small(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = context35.main([], fetch=lambda _url: _reply(8_192), today="2026-11-23")
    assert code == 2
    assert "[error]" in capsys.readouterr().out
