"""Runtime component probes (change integrations-show-runtime-components, tasks 1.2-1.4).

The probes only read: no download, no install, no process start. Model file
probes read the local Hugging Face cache, and a network guard fails a test
that opens a socket. Server probes talk to a stub HTTP server on localhost.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from omrs.core.settings import EmbeddingBlock
from omrs.transports.api import runtime_components as rc
from omrs.transports.api import runtime_servers as rs

LICENSED = (
    '[project]\nname = "x"\n\n[tool.omrs-ocr]\n'
    'requires-acceptance = true\nlicence-file = "LICENCE-NOTES.md"\n'
)
PLAIN = '[project]\nname = "y"\n'
# The shipped tokenizer identity; the conftest factory pins it empty.
TOKENIZER = {
    "embedding.tokenizer_model": EmbeddingBlock.model_fields["tokenizer_model"].default,
    "embedding.tokenizer_revision": EmbeddingBlock.model_fields["tokenizer_revision"].default,
}


def _engine(root: Path, name: str, manifest: str, *, provisioned: bool = False) -> None:
    folder = root / "engines" / name
    folder.mkdir(parents=True)
    (folder / "pyproject.toml").write_text(manifest, encoding="utf-8")
    if provisioned:
        python = folder / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text("", encoding="utf-8")


def _by_name(items: list[rc.RuntimeItem]) -> dict[str, rc.RuntimeItem]:
    return {item.name: item for item in items}


# ── OCR engines (task 1.2) ───────────────────────────────────────────────


def test_no_workers_folder_gives_not_configured(effective_settings: Any) -> None:
    settings = effective_settings(ocr_workers_dir="", ocr_engine_primary="dots-mocr")

    item = _by_name(rc.ocr_engine_items(settings))["dots-mocr"]

    assert item.status == "not-configured"
    assert "ocr_engine_primary" in item.used_by


def test_licence_engine_without_venv_names_the_licence(
    tmp_path: Path, effective_settings: Any
) -> None:
    _engine(tmp_path, "dots-mocr", LICENSED)
    settings = effective_settings(ocr_workers_dir=str(tmp_path), ocr_engine_primary="dots-mocr")

    item = _by_name(rc.ocr_engine_items(settings))["dots-mocr"]

    assert item.status == "missing"
    assert item.fix == "python3 ocr-workers/provision.py dots-mocr --accept-model-licence"
    assert "LICENCE-NOTES.md" in (item.reason or "")


def test_plain_engine_without_venv_has_plain_fix(tmp_path: Path, effective_settings: Any) -> None:
    _engine(tmp_path, "paddleocr-vl", PLAIN)
    settings = effective_settings(ocr_workers_dir=str(tmp_path))

    item = _by_name(rc.ocr_engine_items(settings))["paddleocr-vl"]

    assert item.status == "missing"
    assert item.fix == "python3 ocr-workers/provision.py paddleocr-vl"


def test_provisioned_engine_is_ready(tmp_path: Path, effective_settings: Any) -> None:
    _engine(tmp_path, "paddleocr-vl", PLAIN, provisioned=True)
    settings = effective_settings(ocr_workers_dir=str(tmp_path), ocr_engine_fallback="paddleocr-vl")

    item = _by_name(rc.ocr_engine_items(settings))["paddleocr-vl"]

    assert item.status == "ready"
    assert item.fix is None
    assert item.used_by == ("ocr_engine_fallback",)


def test_engine_list_holds_the_local_tier(effective_settings: Any) -> None:
    names = [item.name for item in rc.ocr_engine_items(effective_settings())]

    assert rc.LOCAL_TIER_NAME in names


# ── Model files (task 1.3) ───────────────────────────────────────────────


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test when any code opens a network connection."""

    def refuse(*_: Any, **__: Any) -> None:
        raise AssertionError("a model file probe opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _cache(monkeypatch: pytest.MonkeyPatch, cached: set[tuple[str, str]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake(repo_id: str, filename: str, revision: str | None = None, **_: Any) -> Any:
        calls.append({"repo_id": repo_id, "filename": filename, "revision": revision})
        return f"/cache/{repo_id}/{filename}" if (repo_id, filename) in cached else None

    monkeypatch.setattr(rc, "try_to_load_from_cache", fake)
    return calls


def test_cached_tokenizer_is_ready(
    monkeypatch: pytest.MonkeyPatch, no_network: None, effective_settings: Any
) -> None:
    settings = effective_settings(**TOKENIZER)
    model = settings.embedding.tokenizer_model
    calls = _cache(monkeypatch, {(model, "tokenizer.json")})

    item = _by_name(rc.model_file_items(settings))[rc.TOKENIZER_NAME]

    assert item.status == "ready"
    assert {"repo_id": model, "filename": "tokenizer.json"}.items() <= calls[0].items()
    assert calls[0]["revision"] == settings.embedding.tokenizer_revision


def test_uncached_tokenizer_is_missing_with_pinned_fix(
    monkeypatch: pytest.MonkeyPatch, no_network: None, effective_settings: Any
) -> None:
    settings = effective_settings(**TOKENIZER)
    _cache(monkeypatch, set())
    model = settings.embedding.tokenizer_model
    revision = settings.embedding.tokenizer_revision

    item = _by_name(rc.model_file_items(settings))[rc.TOKENIZER_NAME]

    assert item.status == "missing"
    assert item.fix == (
        f"uvx --from huggingface_hub hf download {model} tokenizer.json --revision {revision}"
    )
    assert "legacy splitter" in (item.reason or "")


def test_reranker_and_local_ocr_model_listed(
    monkeypatch: pytest.MonkeyPatch, no_network: None, tmp_path: Path, effective_settings: Any
) -> None:
    _cache(monkeypatch, set())
    monkeypatch.setenv("PDF_INSPECTOR_MODEL_CACHE", str(tmp_path / "none"))
    items = _by_name(rc.model_file_items(effective_settings()))

    assert items[rc.RERANKER_NAME].status == "missing"
    assert "hf download" in (items[rc.RERANKER_NAME].fix or "")
    local = items[rc.LOCAL_MODEL_NAME]
    assert local.status == "missing"
    assert "oar-ocr/releases/download/v0.7.0" in (local.fix or "")


def test_local_ocr_model_in_its_folder_is_ready(
    tmp_path: Path, no_network: None, effective_settings: Any
) -> None:
    for name in rc.LOCAL_MODEL_FILES:
        (tmp_path / name).write_text("x", encoding="utf-8")
    settings = effective_settings(ocr_local_model_directory=str(tmp_path))

    assert _by_name(rc.model_file_items(settings))[rc.LOCAL_MODEL_NAME].status == "ready"


# ── Local servers (task 1.4) ─────────────────────────────────────────────


class _Handler(BaseHTTPRequestHandler):
    delay = 0.0

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        time.sleep(self.delay)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - http.server API
        return


def _serve(delay: float) -> Iterator[str]:
    handler = type("Handler", (_Handler,), {"delay": delay})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def stub() -> Iterator[str]:
    yield from _serve(0.0)


@pytest.fixture
def slow_stub() -> Iterator[str]:
    yield from _serve(3.0)


def _closed_address() -> str:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def _servers(settings: Any) -> dict[str, rc.RuntimeItem]:
    return _by_name(asyncio.run(rs.local_server_items(settings)))


def test_answering_server_is_ready(stub: str, effective_settings: Any) -> None:
    settings = effective_settings(embed_provider="ollama", ollama_base_url=stub)

    item = _servers(settings)[rs.OLLAMA_NAME]

    assert item.status == "ready"
    assert "embed_provider" in item.used_by


def test_closed_port_is_not_running(effective_settings: Any) -> None:
    address = _closed_address()
    settings = effective_settings(llamacpp_chat_url=f"{address}/v1")

    item = _servers(settings)[rs.LLAMACPP_CHAT_NAME]

    assert item.status == "not-running"
    assert f"{address}/v1" in (item.reason or "")


def test_slow_server_is_not_running_within_two_seconds(
    slow_stub: str, effective_settings: Any
) -> None:
    settings = effective_settings(
        ollama_base_url=slow_stub,
        llamacpp_embed_url=f"{slow_stub}/v1",
        llamacpp_chat_url=f"{slow_stub}/v1",
    )

    started = time.monotonic()
    items = _servers(settings)
    elapsed = time.monotonic() - started

    assert {item.status for item in items.values()} == {"not-running"}
    assert elapsed < 2.0


def test_unused_server_has_empty_used_by(effective_settings: Any) -> None:
    settings = effective_settings(
        embed_provider="cloud",
        metadata_llm_provider="cloud",
        ollama_base_url=_closed_address(),
    )
    settings = settings.model_copy(
        update={"answer": settings.answer.model_copy(update={"provider": "openrouter"})}
    )

    assert _servers(settings)[rs.OLLAMA_NAME].used_by == ()


def test_credentials_are_removed_from_the_address(effective_settings: Any) -> None:
    address = _closed_address().replace("http://", "http://user:secret@")
    settings = effective_settings(ollama_base_url=address)

    item = _servers(settings)[rs.OLLAMA_NAME]

    assert "secret" not in (item.reason or "")
    assert "user" not in (item.reason or "")


def test_a_failing_http_client_gives_unknown_servers(
    monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    def broken(*_: Any, **__: Any) -> None:
        raise RuntimeError("client exploded: secret-detail")

    monkeypatch.setattr(rs.httpx, "AsyncClient", broken)

    items = _servers(effective_settings())

    assert {item.status for item in items.values()} == {"unknown"}
    assert all("secret-detail" not in (item.reason or "") for item in items.values())


def test_an_unreadable_engines_folder_keeps_the_engines_in_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    (tmp_path / "engines").mkdir()

    def denied(self: Path) -> Any:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "iterdir", denied)
    settings = effective_settings(ocr_workers_dir=str(tmp_path), ocr_engine_primary="dots-mocr")

    names = [item.name for item in rc.ocr_engine_items(settings)]

    assert "dots-mocr" in names
