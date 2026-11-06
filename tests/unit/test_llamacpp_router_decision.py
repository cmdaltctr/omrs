"""Decision models run on the router (one-llamacpp-router, tasks 5.1 and 5.2; outcome A of D10).

A managed ``llamacpp`` decision entry names a ``llamacpp_models`` entry by
``model``. Its requests and its projector smoke test go through the router
lease to ``<router address>/v1/systemone`` with the model name. The
quantisation check reads the list entry's file. The router build floor
(b11941) gives ``wrong-build``. The fake router lease and an
``httpx.MockTransport`` stand in for the server, except in the build test,
which starts the fake router of ``tests/fixtures/llamacpp``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from tests.fixtures.decision.gguf import header_with_type
from tests.unit.test_llamacpp_router_compose_support import (
    CLEF,
    RouterRig,
    composed_rig,
    point_at,
)

from omrs import compose_decision
from omrs.integrations.llamacpp_runtime import ModelUnavailable

ROUTER_BASE = "http://127.0.0.1:18080"
ENTRY_ADDRESS = "http://127.0.0.1:18932"
SHA = "a" * 64


@pytest.fixture(autouse=True)
def _fresh_checks() -> Iterator[None]:
    compose_decision.reset_decision_checks()
    yield
    compose_decision.reset_decision_checks()


class _Router:
    """A router lease that records each model name and sends to one base URL."""

    def __init__(self, refusal: str | None = None) -> None:
        self.refusal = refusal
        self.models: list[str] = []
        self.spec = SimpleNamespace(mode="managed", binary="/b/llama-server", min_build=11941)

    def request_model(self, model: str, send: Callable[[str], Any]) -> Any:
        if self.refusal is not None:
            raise ModelUnavailable(model, self.refusal)
        self.models.append(model)
        return send(ROUTER_BASE)


class _Server:
    """Answers P(yes): 0.9 for the smoke test's right text, else 0.05 or a fixed value."""

    def __init__(self, p_yes: float = 0.7) -> None:
        self.p_yes = p_yes
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append((str(request.url), body))
        text = str(body.get("state", {}).get("text", ""))
        p_yes = self.p_yes
        if body.get("images"):
            from omrs.core.providers.decision.checks import SMOKE_RIGHT_TEXT

            p_yes = 0.9 if text == SMOKE_RIGHT_TEXT else 0.05
        return httpx.Response(200, json={"model": CLEF, "answers": {"fidelity": {"noul": p_yes}}})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def router(monkeypatch: pytest.MonkeyPatch) -> _Router:
    fake = _Router()
    monkeypatch.setattr("omrs.compose_runtimes.router_lease_for", lambda settings: fake)
    return fake


def _gguf(tmp_path: Path, name: str, quantisation: str = "Q8_0") -> str:
    path = tmp_path / name
    path.write_bytes(header_with_type(quantisation))
    return str(path)


def _settings(tmp_path: Path, *, images: bool = False, **listed: Any) -> SimpleNamespace:
    """A managed decision entry ``m`` that names the list entry ``clef``."""
    clef = {
        "model": CLEF, "file": _gguf(tmp_path, "clef.gguf"), "sha256": SHA,
        "projector": None, "projector_sha256": None, "preset": {"parallel": 1},
    }  # fmt: skip
    clef.update(listed)
    entry = {
        "kind": "llamacpp", "address": ENTRY_ADDRESS, "model": CLEF,
        "images": images, "server": "managed",
    }  # fmt: skip
    router = {"model": "m", "question": "Right?", "threshold": 0.172, "images": images}
    return SimpleNamespace(
        document_router="r",
        document_routers={"r": router},
        decision_models={"m": entry},
        llamacpp_models={"clef": SimpleNamespace(**clef)},
    )


# ── Requests go to the router with the model name ────────────────────────


def test_a_page_question_goes_to_the_router_systemone_with_the_model_name(
    tmp_path: Path, router: _Router
) -> None:
    """Spec llamacpp-router "Clef-Flash on the router"."""
    server = _Server()
    judge = compose_decision.build_page_judge(_settings(tmp_path), transport=server.transport)
    assert router.models == [], "building the judge sends nothing"

    assert judge.status is None
    assert judge.judge("page text", None) == pytest.approx(0.7)

    assert router.models == [CLEF, CLEF]  # the text probe, then the page
    assert [url for url, _ in server.calls] == [f"{ROUTER_BASE}/v1/systemone"] * 2
    assert {body["model"] for _, body in server.calls} == {CLEF}


def test_the_projector_smoke_test_passes_through_the_router(
    tmp_path: Path, router: _Router
) -> None:
    """Task 5.2: the smoke test runs against the router address with the model name."""
    settings = _settings(
        tmp_path, images=True, projector=_gguf(tmp_path, "mmproj.gguf"), projector_sha256=SHA
    )
    server = _Server()

    result = compose_decision.test_decision_model(settings, "m", transport=server.transport)

    assert (result["status"], result["projector"]) == ("ok", "Projector smoke test passed.")
    image_calls = [body for _, body in server.calls if body.get("images")]
    assert len(image_calls) == 2
    assert all(url == f"{ROUTER_BASE}/v1/systemone" for url, _ in server.calls)


def test_a_model_the_router_cannot_serve_reads_unreachable_and_sends_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    refusing = _Router(refusal="model-load-failed")
    monkeypatch.setattr("omrs.compose_runtimes.router_lease_for", lambda settings: refusing)
    server = _Server()
    judge = compose_decision.build_page_judge(_settings(tmp_path), transport=server.transport)

    assert judge.status == "unreachable"
    assert judge.judge("page text", None) is None
    assert server.calls == []


# ── Checks on the list entry's file ──────────────────────────────────────


def test_the_quantisation_check_reads_the_list_entry_file(tmp_path: Path, router: _Router) -> None:
    settings = _settings(tmp_path, file=_gguf(tmp_path, "clef-q4.gguf", "Q4_K_M"))

    judge = compose_decision.build_page_judge(settings, transport=_Server().transport)

    assert judge.status == "quantisation-refused"
    assert router.models == []


def test_an_image_entry_whose_list_entry_has_no_projector_is_refused(
    tmp_path: Path, router: _Router
) -> None:
    judge = compose_decision.build_page_judge(
        _settings(tmp_path, images=True), transport=_Server().transport
    )

    assert judge.status == "projector-not-loaded"
    assert router.models == []


def test_the_identity_holds_the_list_entry_sha256(tmp_path: Path) -> None:
    """Design D9: a managed entry's identity carries its files' SHA-256 from the list."""
    from omrs.core.ingestion.ocr_identity import document_router_payload

    settings = _settings(tmp_path, projector_sha256="b" * 64)

    payload = document_router_payload(settings)["document_router"]["model"]

    assert payload == {
        "kind": "llamacpp",
        "model": CLEF,
        "model_sha256": SHA,
        "projector_sha256": "b" * 64,
    }


def test_the_page_judge_identity_equals_the_reading_identity(
    tmp_path: Path, router: _Router
) -> None:
    from omrs.core.ingestion.ocr_identity import document_router_payload

    settings = _settings(tmp_path)

    judge = compose_decision.build_page_judge(settings)

    assert judge.identity == document_router_payload(settings)["document_router"]["model"]


# ── The build floor (real fake router) ───────────────────────────────────


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from composed_rig(tmp_path, monkeypatch)


@pytest.mark.parametrize(
    ("build", "line"),
    [
        (11900, "llama.cpp build b11900 is below the floor b11941."),
        (11960, "llama.cpp build b11960."),
    ],
)
def test_the_router_build_floor_applies_with_a_listed_decision_model(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch, build: int, line: str
) -> None:
    """Spec llamacpp-runtimes "Old build": the router refuses ``wrong-build``; b11960 starts."""
    from omrs import compose
    from omrs.integrations.llamacpp_runtime.hashes import hash_file

    rig.set_env(FAKE_LLAMA_BUILD=build)
    decision = {
        "m": {"kind": "llamacpp", "address": "http://127.0.0.1:8080", "model": CLEF,
              "server": "managed"},
    }  # fmt: skip
    entries = rig.entries()
    entries[2]["sha256"] = hash_file(entries[2]["file"])  # a decision entry needs one
    point_at(rig, monkeypatch, entries=entries, decision=decision)

    result = compose_decision.test_decision_model(compose.get_settings(), "m")

    assert result["build"] == line
    if build < 11941:
        assert result["status"] == "wrong-build"
        assert rig.starts() == 0
    else:
        assert result["status"] != "wrong-build"
        assert rig.starts() == 1


# ── The Settings list of decision models ─────────────────────────────────


def test_the_decision_list_reads_the_files_from_the_named_list_entry() -> None:
    """``router_maps``: a managed item's file fields come from its ``llamacpp_models`` entry."""
    from omrs.transports.api.router_maps import decision_model_list

    managed = {"kind": "llamacpp", "address": ENTRY_ADDRESS, "model": CLEF, "server": "managed"}
    outside = {"kind": "llamacpp", "address": ENTRY_ADDRESS, "model": CLEF}
    listed = {"model": CLEF, "file": "/m/clef.gguf", "projector": "/m/mmproj.gguf",
              "sha256": SHA, "projector_sha256": "b" * 64}  # fmt: skip
    file = SimpleNamespace(
        maps={"decision_models": {"m": managed, "x": outside}, "llamacpp_models": {"c": listed}},
        directory=Path("/unused"),
        revision="r1",
    )

    items = {item["name"]: item for item in decision_model_list(file)["models"]}

    assert (items["m"]["model_file"], items["m"]["projector_file"]) == (
        "/m/clef.gguf", "/m/mmproj.gguf",
    )  # fmt: skip
    assert (items["m"]["model_sha256"], items["m"]["projector_sha256"]) == (SHA, "b" * 64)
    assert items["x"]["model_file"] is None
