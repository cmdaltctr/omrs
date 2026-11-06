"""A managed decision model entry asks through the router (one-llamacpp-router, task 5.1).

A ``llamacpp`` entry with ``server: "managed"`` names a ``llamacpp_models`` entry
by ``model`` and sends every request through the router lease, with the model
name. The judge reads ``wrong-build`` from the router's build check and
``quantisation-refused`` from the GGUF header of the list entry's file; neither
starts a server. Requests go to an ``httpx.MockTransport``; the router lease is
a fake.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from tests.fixtures.decision.gguf import header_with_type

from omrs import compose_decision
from omrs.integrations.llamacpp_runtime import process
from omrs.integrations.llamacpp_runtime.lease import RuntimeUnavailable

ROUTER_BASE = "http://127.0.0.1:18080"
BINARY = "/b/llama-server"
SHA = "a" * 64
MODEL = "Clef/Clef-Flash-GGUF:Q8_0"


@pytest.fixture(autouse=True)
def _fresh_checks():
    compose_decision.reset_decision_checks()
    yield
    compose_decision.reset_decision_checks()


class _Router:
    def __init__(self, refusal: str | None = None) -> None:
        self.refusal, self.models = refusal, []
        self.spec = SimpleNamespace(mode="managed", binary=BINARY, min_build=11941)

    def request_model(self, model, send):
        if self.refusal is not None:
            raise RuntimeUnavailable("router", self.refusal)
        self.models.append(model)
        return send(ROUTER_BASE)


def _use(monkeypatch, router) -> None:
    monkeypatch.setattr("omrs.compose_runtimes.router_lease_for", lambda settings: router)


@pytest.fixture
def router(monkeypatch) -> _Router:
    fake = _Router()
    _use(monkeypatch, fake)
    return fake


class _Server:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        json.loads(request.content)
        return httpx.Response(200, json={"model": "x", "answers": {"fidelity": {"noul": 0.7}}})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def _model_file(tmp_path, quantisation: str = "Q8_0") -> str:
    path = tmp_path / "clef.gguf"
    path.write_bytes(header_with_type(quantisation))
    return str(path)


def _settings(model_file: str) -> SimpleNamespace:
    entry = {"kind": "llamacpp", "address": "http://127.0.0.1:1", "model": MODEL,
             "server": "managed"}  # fmt: skip
    listed = SimpleNamespace(model=MODEL, file=model_file, projector=None, sha256=SHA,
                             projector_sha256=None, preset={"parallel": 1})  # fmt: skip
    router = {"model": "m", "question": "Right?", "threshold": 0.172}
    return SimpleNamespace(
        document_router="r",
        decision_models={"m": entry},
        document_routers={"r": router},
        llamacpp_models={"clef": listed},
    )


def test_requests_go_through_the_router_with_the_model_name(tmp_path, router):
    server = _Server()
    judge = compose_decision.build_page_judge(
        _settings(_model_file(tmp_path)), transport=server.transport
    )
    assert router.models == [], "building the judge starts nothing"

    assert judge.status is None
    assert judge.judge("page text", None) == pytest.approx(0.7)

    assert router.models == [MODEL, MODEL]
    assert server.urls == [f"{ROUTER_BASE}/v1/systemone"] * 2


def test_a_build_below_the_floor_reads_wrong_build_and_sends_nothing(tmp_path, monkeypatch):
    _use(monkeypatch, _Router(refusal="wrong-build"))
    server = _Server()
    judge = compose_decision.build_page_judge(
        _settings(_model_file(tmp_path)), transport=server.transport
    )

    assert judge.status == "wrong-build"
    assert judge.judge("page text", None) is None
    assert server.urls == []


def test_a_4_bit_model_file_is_refused_before_the_router_starts(tmp_path, router):
    judge = compose_decision.build_page_judge(_settings(_model_file(tmp_path, "Q4_K_M")))

    assert judge.status == "quantisation-refused"
    assert router.models == []


def test_a_managed_entry_whose_router_cannot_be_built_reads_unreachable(tmp_path, monkeypatch):
    _use(monkeypatch, "not-configured")
    judge = compose_decision.build_page_judge(_settings(_model_file(tmp_path)))

    assert judge.status == "unreachable"


@pytest.mark.parametrize(
    ("build", "status", "line"),
    [
        (11960, "ok", "llama.cpp build b11960."),
        (11900, "wrong-build", "llama.cpp build b11900 is below the floor b11941."),
    ],
)
def test_test_shows_the_build_of_the_router(tmp_path, monkeypatch, build, status, line):
    _use(monkeypatch, _Router(refusal="wrong-build" if build < 11941 else None))
    monkeypatch.setattr(process, "read_build", lambda binary, env: build)

    result = compose_decision.test_decision_model(
        _settings(_model_file(tmp_path)), "m", transport=_Server().transport
    )

    assert (result["status"], result["build"]) == (status, line)
    assert result["quantisation"] == "Quantisation Q8_0."


def test_an_external_entry_has_no_build_line(tmp_path, router):
    settings = _settings(_model_file(tmp_path))
    settings.decision_models["m"] = {"kind": "llamacpp", "address": "http://127.0.0.1:1",
                                     "model": "c"}  # fmt: skip

    result = compose_decision.test_decision_model(settings, "m", transport=_Server().transport)

    assert result["build"] is None
    assert router.models == []
