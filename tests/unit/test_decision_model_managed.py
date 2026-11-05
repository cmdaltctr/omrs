"""A managed decision model entry asks through its runtime (document-reading-routers, task 2.4).

A ``llamacpp`` entry with ``server: "managed"`` sends every request through the
lease of runtime ``decision-<name>``, which starts ``llama-server`` on the first
request. The judge reads ``wrong-build`` from the runtime's build check and
``quantisation-refused`` from the GGUF header of the model file; neither starts
a server. Requests go to an ``httpx.MockTransport``; the runtime manager is a fake.
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

ADDRESS = "http://127.0.0.1:18932"
BINARY = "/b/llama-server"
SHA = "a" * 64


@pytest.fixture(autouse=True)
def _fresh_checks():
    compose_decision.reset_decision_checks()
    yield
    compose_decision.reset_decision_checks()


class _Lease:
    def __init__(self, spec, refusal: str | None) -> None:
        self.spec, self.refusal, self.requests = spec, refusal, 0

    def request(self, send):
        if self.refusal is not None:
            raise RuntimeUnavailable(self.spec.id, self.refusal)
        self.requests += 1
        return send(f"http://127.0.0.1:{self.spec.port}")


class _Manager:
    def __init__(self, refusal: str | None = None) -> None:
        self.refusal = refusal
        self.leases: list[_Lease] = []

    def lease(self, spec):
        self.leases.append(_Lease(spec, self.refusal))
        return self.leases[-1]


@pytest.fixture
def manager(monkeypatch) -> _Manager:
    fake = _Manager()
    monkeypatch.setattr("omrs.compose_runtime_manager.runtime_manager", lambda: fake)
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


def _settings(model_file: str, **extra: object) -> SimpleNamespace:
    entry = {
        "kind": "llamacpp", "address": ADDRESS, "model": "clef-flash", "server": "managed",
        "model_file": model_file, "model_sha256": SHA,
    }  # fmt: skip
    router = {"model": "m", "question": "Right?", "threshold": 0.172}
    values = {"document_router": "r", "decision_models": {"m": entry}}
    values.update({"document_routers": {"r": router}, "llamacpp_server_binary": BINARY, **extra})
    return SimpleNamespace(**values)


def test_requests_go_through_the_decision_runtime_lease(tmp_path, manager):
    server = _Server()
    judge = compose_decision.build_page_judge(
        _settings(_model_file(tmp_path)), transport=server.transport
    )
    assert manager.leases == [], "building the judge starts nothing"

    assert judge.status is None
    assert judge.judge("page text", None) == pytest.approx(0.7)

    spec = manager.leases[0].spec
    assert (spec.id, spec.role, spec.min_build) == ("decision-m", "decision", 11941)
    assert spec.argv[:3] == (BINARY, "-m", _model_file(tmp_path))
    assert sum(lease.requests for lease in manager.leases) == 2
    assert server.urls == [f"{ADDRESS}/v1/systemone"] * 2


def test_a_build_below_the_floor_reads_wrong_build_and_sends_nothing(tmp_path, monkeypatch):
    refusing = _Manager(refusal="wrong-build")
    monkeypatch.setattr("omrs.compose_runtime_manager.runtime_manager", lambda: refusing)
    server = _Server()
    judge = compose_decision.build_page_judge(
        _settings(_model_file(tmp_path)), transport=server.transport
    )

    assert judge.status == "wrong-build"
    assert judge.judge("page text", None) is None
    assert server.urls == []


def test_a_4_bit_model_file_is_refused_before_the_runtime_starts(tmp_path, manager):
    judge = compose_decision.build_page_judge(_settings(_model_file(tmp_path, "Q4_K_M")))

    assert judge.status == "quantisation-refused"
    assert manager.leases == []


def test_a_managed_entry_that_cannot_start_reads_unreachable(tmp_path, manager):
    judge = compose_decision.build_page_judge(
        _settings(_model_file(tmp_path), llamacpp_server_binary="")
    )

    assert judge.status == "unreachable"
    assert manager.leases == []


def test_settings_without_the_program_take_it_from_the_process_settings(
    tmp_path, manager, monkeypatch
):
    settings = _settings(_model_file(tmp_path))
    del settings.llamacpp_server_binary  # EffectiveSettings has no such field
    monkeypatch.setattr(
        "omrs.compose_runtimes.current_settings",
        lambda values=None: SimpleNamespace(llamacpp_server_binary=BINARY),
    )
    judge = compose_decision.build_page_judge(settings, transport=_Server().transport)

    assert judge.status is None
    assert manager.leases[0].spec.binary == BINARY


@pytest.mark.parametrize(
    ("build", "status", "line"),
    [
        (11960, "ok", "llama.cpp build b11960."),
        (11900, "wrong-build", "llama.cpp build b11900 is below the floor b11941."),
    ],
)
def test_test_shows_the_build_of_a_managed_entry(tmp_path, monkeypatch, build, status, line):
    refusal = "wrong-build" if build < 11941 else None
    fake = _Manager(refusal=refusal)
    monkeypatch.setattr("omrs.compose_runtime_manager.runtime_manager", lambda: fake)
    monkeypatch.setattr(process, "read_build", lambda binary, env: build)

    result = compose_decision.test_decision_model(
        _settings(_model_file(tmp_path)), "m", transport=_Server().transport
    )

    assert (result["status"], result["build"]) == (status, line)
    assert result["quantisation"] == "Quantisation Q8_0."


def test_an_external_entry_has_no_build_line(tmp_path, manager):
    settings = _settings(_model_file(tmp_path))
    settings.decision_models["m"] = {"kind": "llamacpp", "address": ADDRESS, "model": "c"}

    result = compose_decision.test_decision_model(settings, "m", transport=_Server().transport)

    assert result["build"] is None
    assert manager.leases == []
