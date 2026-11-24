"""Experiment 35 ``context35.py``: the answer model's context length (task 14.1a).

The check reads the pinned host's endpoint, not the model-level value (gap G21).
The OpenRouter endpoints reply is stubbed. No test calls OpenRouter.
"""

from __future__ import annotations

import json

import pytest
from tests._exp35_fixtures import load

context35 = load("context35")
MODEL = "deepseek/deepseek-v4.1-flash-1017"
HOST = "deepinfra/fp8"
PLAN = {"pins": {"settings": {"answer": {"allowed_hosts": HOST}}}}


def _endpoint(tag: str, length: object) -> dict:
    return {"tag": tag, "provider_name": "X", "quantization": "fp8", "context_length": length}


def _reply(length: object, model: str = MODEL, host: str = HOST) -> dict:
    # The other hosts carry the floor-passing length, so only the pinned one decides.
    endpoints = [
        _endpoint(f"{host}/flex", 1_048_576),
        _endpoint(host, length),
        _endpoint("other/fp4", 1_048_576),
    ]
    return {"data": {"id": model, "context_length": 1_048_576, "endpoints": endpoints}}


def test_the_answer_model_is_the_pinned_one() -> None:
    assert context35.MODEL == MODEL
    assert context35.MIN_CONTEXT_TOKENS == 65_536
    assert context35.ENDPOINTS_URL == f"https://openrouter.ai/api/v1/models/{MODEL}/endpoints"


@pytest.mark.parametrize("length", [65_536, 131_072, 1_000_000])
def test_a_length_at_or_above_the_floor_is_returned(length: int) -> None:
    assert context35.context_length(_reply(length), HOST) == length


@pytest.mark.parametrize("length", [65_535, 32_768, 0])
def test_a_length_below_the_floor_is_refused_with_both_numbers(length: int) -> None:
    with pytest.raises(context35.ContextLengthError, match=rf"{HOST}.*{length}.*65,536"):
        context35.context_length(_reply(length), HOST)


def test_the_pinned_hosts_value_is_taken_not_the_model_or_another_host() -> None:
    reply = _reply(131_072)
    reply["data"]["context_length"] = 8_192
    reply["data"]["endpoints"][0]["context_length"] = 8_192
    assert context35.context_length(reply, HOST) == 131_072


def test_a_reply_without_the_pinned_host_is_refused_and_names_it() -> None:
    reply = _reply(131_072, host="deepinfra/bf16")
    with pytest.raises(context35.ContextLengthError, match=f"no endpoint {HOST!r}"):
        context35.context_length(reply, HOST)


def test_a_reply_without_the_model_is_refused_and_names_it() -> None:
    with pytest.raises(context35.ContextLengthError, match=MODEL):
        context35.context_length(_reply(131_072, model="other/model"), HOST)


@pytest.mark.parametrize("length", [None, "131072", True, 1.5])
def test_a_missing_or_malformed_length_is_refused(length: object) -> None:
    with pytest.raises(context35.ContextLengthError, match="context_length"):
        context35.context_length(_reply(length), HOST)


@pytest.mark.parametrize("reply", [{"error": "nope"}, {"data": []}, {"data": {"id": MODEL}}])
def test_a_reply_that_is_not_an_endpoints_list_is_refused(reply: dict) -> None:
    with pytest.raises(context35.ContextLengthError, match="endpoints"):
        context35.context_length(reply, HOST)


def test_the_pinned_host_is_read_from_the_plan() -> None:
    assert context35.pinned_host(PLAN) == HOST
    assert context35.pinned_host(context35.load_plan()) == HOST


@pytest.mark.parametrize("value", [None, "", "  ", "deepinfra/fp8,novita/fp8"])
def test_a_missing_or_multiple_pinned_host_is_refused(value: object) -> None:
    plan = {"pins": {"settings": {"answer": {"allowed_hosts": value}}}}
    with pytest.raises(context35.ContextLengthError, match="allowed_hosts"):
        context35.pinned_host(plan)


def test_check_reads_the_reply_through_the_fetch_seam_and_records_value_and_date() -> None:
    calls: list[str] = []

    def fetch(url: str) -> dict:
        calls.append(url)
        return _reply(131_072)

    record = context35.check(fetch=fetch, today="2026-11-23", plan=PLAN)
    assert calls == [context35.ENDPOINTS_URL]
    assert record == {
        "model": MODEL,
        "host": HOST,
        "context_length": 131_072,
        "minimum": 65_536,
        "checked": "2026-11-23",
        "source": context35.ENDPOINTS_URL,
    }


def test_main_prints_the_record_and_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    code = context35.main([], fetch=lambda _url: _reply(131_072), today="2026-11-23", plan=PLAN)
    assert code == 0
    assert json.loads(capsys.readouterr().out)["context_length"] == 131_072


def test_main_exits_2_with_the_reason_when_the_length_is_too_small(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = context35.main([], fetch=lambda _url: _reply(8_192), today="2026-11-23", plan=PLAN)
    assert code == 2
    assert "[error]" in capsys.readouterr().out


def test_main_exits_2_when_the_pinned_host_is_missing_from_the_reply(
    capsys: pytest.CaptureFixture[str],
) -> None:
    reply = _reply(1_048_576, host="novita/fp8")
    code = context35.main([], fetch=lambda _url: reply, today="2026-11-23", plan=PLAN)
    assert code == 2
    assert HOST in capsys.readouterr().out
