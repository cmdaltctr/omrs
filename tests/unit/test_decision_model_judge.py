"""The page judge that compose builds from a router and its decision model.

Task 2.1 of document-reading-routers (design D2, D6, D7, D8, D12). Every
request goes to an ``httpx.MockTransport``; no test contacts a real model.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from tests.fixtures.decision.gguf import header_with_type

from omrs import compose_decision
from omrs.config.settings_maps import DecisionModelEntry, DocumentRouterEntry
from omrs.core.providers.decision import checks

LOCAL = "http://127.0.0.1:9931"
HOSTED = "https://api.typesafe.ai"
PAGE_TEXT = "private page text 4417"
KEY = "secret-key-value"


@pytest.fixture(autouse=True)
def _fresh_checks():
    compose_decision.reset_decision_checks()
    yield
    compose_decision.reset_decision_checks()


class FakeServer:
    """A System One server: the smoke right text scores high, everything else as set."""

    def __init__(
        self,
        *,
        p_yes: object = 0.8,
        model: str = "Clef-Flash-Q8_0.gguf",
        smoke: tuple[float, float] = (0.9, 0.07),
        error: Exception | None = None,
        status: int = 200,
    ) -> None:
        self.p_yes, self.model, self.smoke = p_yes, model, smoke
        self.error, self.status_code = error, status
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        body = json.loads(request.content)
        text = body["state"]["text"]
        score = self.p_yes
        if text == checks.SMOKE_RIGHT_TEXT:
            score = self.smoke[0]
        elif text == checks.SMOKE_WRONG_TEXT:
            score = self.smoke[1]
        reply = {"model": self.model, "answers": {"fidelity": {"noul": score}}}
        return httpx.Response(self.status_code, json=reply)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def _settings(model: object, router: object, *, selected: str = "r") -> SimpleNamespace:
    return SimpleNamespace(
        document_router=selected,
        decision_models={"m": model},
        document_routers={"r": router},
    )


def _model(**fields: object) -> dict:
    return {"kind": "llamacpp", "address": LOCAL, "model": "clef-flash", **fields}


def _router(**fields: object) -> dict:
    return {"model": "m", "question": "Is the text right?", "threshold": 0.172, **fields}


def _build(settings, server: FakeServer, **kwargs):
    return compose_decision.build_page_judge(settings, transport=server.transport, **kwargs)


# ── Selection ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("selected", ["", "none"])
def test_no_router_selected_gives_none(selected: str) -> None:
    server = FakeServer()
    assert _build(_settings(_model(), _router(), selected=selected), server) is None
    assert server.requests == []


def test_router_name_argument_wins_over_the_host_router() -> None:
    server = FakeServer()
    settings = _settings(_model(), _router(), selected="")
    judge = _build(settings, server, router_name="r")
    assert judge is not None and judge.name == "r"
    assert _build(_settings(_model(), _router()), server, router_name="none") is None


def test_settings_without_maps_give_none() -> None:
    assert compose_decision.build_page_judge(SimpleNamespace()) is None


def test_unknown_router_name_gives_none() -> None:
    assert _build(_settings(_model(), _router(), selected="other"), FakeServer()) is None


def test_unknown_model_entry() -> None:
    server = FakeServer()
    judge = _build(_settings(_model(), _router(model="absent")), server)
    assert judge.status == "unknown-model"
    assert judge.judge(PAGE_TEXT, None) is None
    assert server.requests == []


def test_unknown_kind_is_unknown_model() -> None:
    server = FakeServer()
    judge = _build(_settings(_model(kind="foo"), _router()), server)
    assert judge.status == "unknown-model"
    assert server.requests == []


# ── Local judging ───────────────────────────────────────────────────────


def test_local_judge_returns_p_yes_and_recipe() -> None:
    server = FakeServer(p_yes=0.31)
    judge = _build(_settings(_model(), _router(max_chars=7)), server)
    assert (judge.question, judge.threshold, judge.images, judge.max_chars) == (
        "Is the text right?",
        0.172,
        False,
        7,
    )
    assert judge.hosted is False
    assert judge.status is None
    assert judge.judge(PAGE_TEXT, None) == 0.31
    last = json.loads(server.requests[-1].content)
    assert last["state"]["text"] == PAGE_TEXT[:7]
    assert "TypeSafe-Danger-Zone-Images" not in server.requests[-1].headers


def test_pydantic_entries_work() -> None:
    server = FakeServer(p_yes=0.5)
    model = DecisionModelEntry(kind="llamacpp", address=LOCAL, model="clef-flash")
    router = DocumentRouterEntry(model="m", question="Q?", threshold=0.2)
    judge = _build(_settings(model, router), server)
    assert judge.status is None
    assert judge.judge("text", None) == 0.5


def test_identity_of_an_external_entry() -> None:
    judge = _build(_settings(_model(model_sha256="a" * 64), _router()), FakeServer())
    assert judge.identity == {"kind": "llamacpp", "model": "clef-flash"}


def test_identity_of_a_managed_entry(tmp_path) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(header_with_type("Q8_0"))
    entry = _model(server="managed", model_file=str(path), model_sha256="a" * 64)
    judge = _build(_settings(entry, _router()), FakeServer())
    assert judge.identity == {
        "kind": "llamacpp",
        "model": "clef-flash",
        "model_sha256": "a" * 64,
        "projector_sha256": None,
    }


def test_malformed_reply_gives_none_and_a_fixed_log(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    server = FakeServer()
    judge = _build(_settings(_model(), _router()), server)
    assert judge.status is None
    server.p_yes = float("nan")
    assert judge.judge(PAGE_TEXT, None) is None
    server.p_yes = 1.5
    assert judge.judge(PAGE_TEXT, None) is None
    assert "malformed-reply" in caplog.text
    assert PAGE_TEXT not in caplog.text


def test_failed_request_gives_none() -> None:
    server = FakeServer()
    judge = _build(_settings(_model(), _router()), server)
    assert judge.status is None
    server.status_code = 500
    assert judge.judge(PAGE_TEXT, None) is None
    server.error = httpx.ConnectError("down")
    assert judge.judge(PAGE_TEXT, None) is None


# ── Checks ──────────────────────────────────────────────────────────────


def test_unreachable_server() -> None:
    server = FakeServer(error=httpx.ConnectError("refused"))
    judge = _build(_settings(_model(), _router()), server)
    assert judge.status == "unreachable"
    count = len(server.requests)
    assert judge.judge(PAGE_TEXT, None) is None
    assert len(server.requests) == count


def test_building_contacts_nothing() -> None:
    server = FakeServer()
    _build(_settings(_model(), _router()), server)
    assert server.requests == []


def test_external_q4_name_is_refused() -> None:
    server = FakeServer(model="models/Clef-Flash-Q4_K_M.gguf")
    judge = _build(_settings(_model(), _router()), server)
    assert judge.status == "quantisation-refused"
    assert checks.EIGHT_BIT_RULE in judge.quantisation
    count = len(server.requests)
    assert judge.judge(PAGE_TEXT, None) is None
    assert len(server.requests) == count


def test_external_name_without_marker_is_not_checked() -> None:
    judge = _build(_settings(_model(), _router()), FakeServer(model="clef"))
    assert judge.status is None
    assert judge.quantisation == "Quantisation not checked"


def test_managed_q4_file_is_refused_before_any_request(tmp_path) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(header_with_type("Q4_K_M"))
    server = FakeServer()
    judge = _build(_settings(_model(server="managed", model_file=str(path)), _router()), server)
    assert judge.status == "quantisation-refused"
    assert "Q4_K_M" in judge.quantisation
    assert server.requests == []


def test_managed_q8_file_passes(tmp_path, monkeypatch) -> None:
    # A managed entry asks through its runtime lease (task 2.4); this lease sends at once.
    lease = SimpleNamespace(request=lambda send: send(LOCAL))
    manager = SimpleNamespace(lease=lambda spec: lease)
    monkeypatch.setattr("omrs.compose_runtime_manager.runtime_manager", lambda: manager)
    path = tmp_path / "m.gguf"
    path.write_bytes(header_with_type("Q8_0"))
    entry = _model(server="managed", model_file=str(path), model_sha256="a" * 64)
    settings = _settings(entry, _router())
    settings.llamacpp_server_binary = "/b/llama-server"
    judge = _build(settings, FakeServer())
    assert judge.status is None


def test_image_router_runs_the_smoke_test() -> None:
    server = FakeServer()
    judge = _build(_settings(_model(images=True), _router(images=True)), server)
    assert judge.status is None
    texts = [json.loads(r.content)["state"]["text"] for r in server.requests]
    assert checks.SMOKE_RIGHT_TEXT in texts and checks.SMOKE_WRONG_TEXT in texts


def test_equal_smoke_answers_mean_projector_not_loaded() -> None:
    server = FakeServer(smoke=(0.5, 0.5))
    judge = _build(_settings(_model(images=True), _router(images=True)), server)
    assert judge.status == "projector-not-loaded"


def test_image_router_on_a_text_only_entry() -> None:
    server = FakeServer()
    judge = _build(_settings(_model(images=False), _router(images=True)), server)
    assert judge.status == "projector-not-loaded"


def test_managed_image_entry_needs_a_projector_file(tmp_path) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(header_with_type("Q8_0"))
    entry = _model(server="managed", model_file=str(path), images=True)
    server = FakeServer()
    judge = _build(_settings(entry, _router(images=True)), server)
    assert judge.status == "projector-not-loaded"
    assert server.requests == []


def test_checks_run_once_per_entry_until_reset() -> None:
    server = FakeServer()
    settings = _settings(_model(images=True), _router(images=True))
    assert _build(settings, server).status is None
    count = len(server.requests)
    assert _build(settings, server).status is None
    assert len(server.requests) == count
    compose_decision.reset_decision_checks()
    assert _build(settings, server).status is None
    assert len(server.requests) > count


# ── Hosted entries and privacy ──────────────────────────────────────────


def _hosted(**fields: object) -> dict:
    return _model(kind="typesafe", address=HOSTED, model="jev-1.14.0", key="env://TS_KEY", **fields)


def test_hosted_without_opt_in_sends_nothing(monkeypatch) -> None:
    monkeypatch.setenv("TS_KEY", KEY)
    server = FakeServer()
    judge = _build(_settings(_hosted(images=True), _router(images=True)), server)
    assert judge.hosted is True
    assert judge.status == "needs-opt-in"
    assert judge.judge(PAGE_TEXT, b"\x89PNG") is None
    assert server.requests == []


def test_hosted_with_opt_in_sends_the_resolved_key(monkeypatch) -> None:
    monkeypatch.setenv("TS_KEY", KEY)
    server = FakeServer(model="jev-1.14.0", p_yes=0.21)
    judge = _build(_settings(_hosted(), _router(send_off_machine=True)), server)
    assert judge.status is None
    assert judge.judge(PAGE_TEXT, None) == 0.21
    assert server.requests[-1].headers["Authorization"] == f"Bearer {KEY}"
    assert str(server.requests[-1].url) == HOSTED + "/v1/systemone"


def test_hosted_image_request_carries_the_header(monkeypatch) -> None:
    monkeypatch.setenv("TS_KEY", KEY)
    server = FakeServer(model="jev-1.14.0")
    settings = _settings(_hosted(images=True), _router(images=True, send_off_machine=True))
    judge = _build(settings, server)
    assert judge.status is None
    judge.judge(PAGE_TEXT, b"\x89PNG")
    assert server.requests[-1].headers["TypeSafe-Danger-Zone-Images"] == "true"


def test_local_image_request_has_no_hosted_header() -> None:
    server = FakeServer()
    judge = _build(_settings(_model(images=True), _router(images=True)), server)
    assert judge.status is None
    judge.judge(PAGE_TEXT, b"\x89PNG")
    assert all("TypeSafe-Danger-Zone-Images" not in r.headers for r in server.requests)


def test_hosted_key_that_does_not_resolve_sends_nothing(monkeypatch) -> None:
    monkeypatch.delenv("TS_KEY", raising=False)
    server = FakeServer()
    judge = _build(_settings(_hosted(), _router(send_off_machine=True)), server)
    assert judge.status == "request-failed"
    assert server.requests == []


def test_file_key_reference_resolves(monkeypatch, tmp_path) -> None:
    config = tmp_path / "omrs"
    (config / "secrets").mkdir(parents=True)
    key_file = config / "secrets" / "typesafe.key"
    key_file.write_text(KEY + "\n")
    key_file.chmod(0o600)
    (config / "secrets").chmod(0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(config))
    assert compose_decision.resolve_key_reference(f"file://{key_file}") == KEY


def test_keychain_key_reference_uses_the_store() -> None:
    class Store:
        available = True

        def read(self, provider: str):
            assert provider == "typesafe"
            return SimpleNamespace(reveal=lambda: KEY)

    assert compose_decision.resolve_key_reference("keychain://typesafe", keychain=Store()) == KEY


def test_literal_key_is_not_used() -> None:
    assert compose_decision.resolve_key_reference(KEY) is None


def test_logs_hold_no_text_key_or_body(monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("TS_KEY", KEY)
    server = FakeServer(model="jev-1.14.0")
    judge = _build(_settings(_hosted(), _router(send_off_machine=True)), server)
    judge.judge(PAGE_TEXT, None)
    server.p_yes = "not a number"
    judge.judge(PAGE_TEXT, None)
    server.error = httpx.ConnectError(PAGE_TEXT)
    judge.judge(PAGE_TEXT, None)
    assert KEY not in caplog.text
    assert PAGE_TEXT not in caplog.text
    assert KEY not in repr(judge)
