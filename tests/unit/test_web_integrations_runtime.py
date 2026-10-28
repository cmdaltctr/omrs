"""The ``runtime`` block and provider readiness on ``GET /v1/integrations``.

Change integrations-show-runtime-components, tasks 1.5 and 2.1. Every local
server address points at a closed port, so no test reaches a real Ollama or
llama.cpp server. Responses are validated against ``openapi.yaml``.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

from omrs.transports.api import runtime_components  # noqa: E402


def _closed_address() -> str:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def chat_url() -> str:
    return f"{_closed_address()}/v1"


@pytest.fixture
def client(tmp_path: Path, effective_settings: Any, chat_url: str):
    settings = effective_settings(
        ollama_base_url=_closed_address(),
        llamacpp_embed_url=f"{_closed_address()}/v1",
        llamacpp_chat_url=chat_url,
        openrouter_api_key="",
    )
    app, policy = build_app(tmp_path, make_engine(lance_store(tmp_path), settings))
    with TestClient(app, base_url=BASE) as test_client:
        login(test_client, policy)
        yield test_client


def _body(client: TestClient) -> dict[str, Any]:
    response = client.get("/v1/integrations")
    assert response.status_code == 200, response.text
    return response.json()


def test_runtime_block_has_three_groups_with_every_field(client: TestClient) -> None:
    runtime = _body(client)["runtime"]

    assert set(runtime) == {"ocr_engines", "model_files", "local_servers"}
    items = [item for group in runtime.values() for item in group]
    assert items
    for item in items:
        assert set(item) == {"name", "purpose", "status", "reason", "fix", "used_by"}


def test_a_runtime_probe_that_raises_gives_unknown(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(_: Any) -> Any:
        raise RuntimeError("probe exploded: secret-detail")

    monkeypatch.setattr(runtime_components, "_tokenizer_item", explode)
    response = client.get("/v1/integrations")

    assert response.status_code == 200
    assert "secret-detail" not in response.text
    files = {item["name"]: item for item in response.json()["runtime"]["model_files"]}
    assert files[runtime_components.TOKENIZER_NAME]["status"] == "unknown"


def test_llamacpp_card_reports_the_server_down(client: TestClient, chat_url: str) -> None:
    entries = {entry["id"]: entry for entry in _body(client)["integrations"]}
    llamacpp = entries["llamacpp"]

    assert llamacpp["readiness"]["ready"] is False
    assert llamacpp["readiness"]["line"].startswith("Not running at ")
    assert llamacpp["base"] is True
    assert llamacpp["availability"] in {"available", "not-installed"}


def test_openrouter_card_without_a_key(client: TestClient) -> None:
    openrouter = {entry["id"]: entry for entry in _body(client)["integrations"]}["openrouter"]

    assert openrouter["readiness"] == {"ready": False, "line": "No key set"}
    assert openrouter["base"] is True


def test_other_cards_carry_no_readiness(client: TestClient) -> None:
    entries = {entry["id"]: entry for entry in _body(client)["integrations"]}

    assert "readiness" not in entries["hybrid"]


def test_runtime_response_conforms(client: TestClient) -> None:
    body = ContractChecker().check(client.get("/v1/integrations"), 200)

    assert body["status"] == "ok"
