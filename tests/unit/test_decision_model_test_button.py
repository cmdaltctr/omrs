"""``compose_decision.test_decision_model``: the Test button of one entry (task 2.3, design D6).

Test re-runs the quantisation check, the one-question text request and, for an
image entry, the projector smoke test, and returns four fields. Every request
goes to an ``httpx.MockTransport``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from omrs import compose_decision
from omrs.core.providers.decision import checks

LOCAL = "http://127.0.0.1:18931"


@pytest.fixture(autouse=True)
def _fresh_checks():
    compose_decision.reset_decision_checks()
    yield
    compose_decision.reset_decision_checks()


class _Server:
    def __init__(self, *, smoke=(0.9, 0.07), error: Exception | None = None) -> None:
        self.smoke, self.error = smoke, error
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.error is not None:
            raise self.error
        text = json.loads(request.content)["state"]["text"]
        score = {checks.SMOKE_RIGHT_TEXT: self.smoke[0], checks.SMOKE_WRONG_TEXT: self.smoke[1]}
        reply = {"model": "Clef-Flash-Q8_0.gguf", "answers": {"fidelity": {"noul": 0.8}}}
        reply["answers"]["fidelity"]["noul"] = score.get(text, 0.8)
        return httpx.Response(200, json=reply)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def _settings(**entry: object) -> SimpleNamespace:
    model = {"kind": "llamacpp", "address": LOCAL, "model": "clef-flash", **entry}
    return SimpleNamespace(document_router="", decision_models={"m": model}, document_routers={})


def test_a_text_entry_that_answers_reads_ok_with_its_quantisation():
    server = _Server()

    result = compose_decision.test_decision_model(_settings(), "m", transport=server.transport)

    assert result == {
        "status": "ok",
        "quantisation": "Quantisation Q8_0.",
        "projector": None,
        "build": None,
    }
    assert server.calls == 1, "one text request; no smoke test for a text entry"


def test_an_image_entry_runs_the_smoke_test():
    server = _Server()

    result = compose_decision.test_decision_model(
        _settings(images=True), "m", transport=server.transport
    )

    assert result["status"] == "ok"
    assert result["projector"] == compose_decision.PROJECTOR_PASSED
    assert server.calls == 3


def test_an_image_entry_without_a_working_projector_reads_projector_not_loaded():
    server = _Server(smoke=(0.5, 0.5))

    result = compose_decision.test_decision_model(
        _settings(images=True), "m", transport=server.transport
    )

    assert result["status"] == "projector-not-loaded"
    assert result["projector"] == compose_decision.PROJECTOR_FAILED


def test_an_unreachable_server_reads_unreachable():
    server = _Server(error=httpx.ConnectError("refused"))

    result = compose_decision.test_decision_model(
        _settings(images=True), "m", transport=server.transport
    )

    assert result["status"] == "unreachable"
    assert result["quantisation"] == checks.NOT_CHECKED_TEXT
    assert result["projector"] == compose_decision.PROJECTOR_NOT_CHECKED


def test_an_unknown_entry_or_kind_reads_unknown_model():
    server = _Server()

    missing = compose_decision.test_decision_model(_settings(), "other", transport=server.transport)
    bad_kind = compose_decision.test_decision_model(
        _settings(kind="nope"), "m", transport=server.transport
    )

    assert missing["status"] == bad_kind["status"] == "unknown-model"
    assert server.calls == 0


def test_test_runs_the_checks_again_and_the_router_judge_sees_the_new_result():
    settings = _settings()
    settings.document_router = "r"
    settings.document_routers = {"r": {"model": "m", "question": "Right?", "threshold": 0.1}}
    good, bad = _Server(), _Server(error=httpx.ConnectError("refused"))
    judge = compose_decision.build_page_judge(settings, transport=bad.transport)
    assert judge is not None
    compose_decision.test_decision_model(settings, "m", transport=good.transport)
    assert judge.status is None, "the cached result came from the good server"

    result = compose_decision.test_decision_model(settings, "m", transport=bad.transport)

    assert result["status"] == "unreachable", "Test did not reuse the cached ok"
    assert judge.status == "unreachable"


def test_a_hosted_entry_is_tested_without_the_router_opt_in():
    server = _Server()
    settings = _settings(kind="typesafe", address="https://api.example.test")

    result = compose_decision.test_decision_model(settings, "m", transport=server.transport)

    assert result["status"] == "ok"
    assert server.calls == 1, "the probe is content free, so Test may send it"


# ── Review finding 3: a malformed probe reply has its own reason ─────────


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"model": "Clef-Flash-Q8_0.gguf", "answers": {}}),
        httpx.Response(200, text="not json"),
    ],
    ids=["no-answer", "not-json"],
)
def test_a_malformed_probe_reply_reads_malformed_reply(response: httpx.Response):
    transport = httpx.MockTransport(lambda request: response)

    result = compose_decision.test_decision_model(_settings(), "m", transport=transport)

    assert result["status"] == "malformed-reply"


def test_an_http_error_on_the_probe_still_reads_request_failed():
    transport = httpx.MockTransport(lambda request: httpx.Response(500, text="boom"))

    result = compose_decision.test_decision_model(_settings(), "m", transport=transport)

    assert result["status"] == "request-failed"
