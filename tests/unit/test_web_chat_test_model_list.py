"""The llama.cpp Chat test reads the server's model list first (ADR-108 D7).

A server you run (the Llama app) answers an unknown name with an error, and a
single-model server answers any name with the model it loaded. So with the
choice ``external`` the test reads ``/models`` first and refuses a name the
server does not list. With ``managed``, OMRS's server loads the Chat model by
rule, so the test skips the list. An in-process fake server records each path.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit import test_web_chat_settings as chat  # noqa: E402

LISTED = "Qwen/Qwen3-0.6B-GGUF:Q8_0"
configure = chat.configure
setup = chat.setup


class FakeLlamacpp:
    """A local server that lists one model and answers any completion with OK."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        paths = self.paths

        class Handler(BaseHTTPRequestHandler):
            def _send(self, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                paths.append(self.path)
                self._send({"object": "list", "data": [{"id": LISTED, "object": "model"}]})

            def do_POST(self) -> None:  # noqa: N802
                paths.append(self.path)
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                choice: dict[str, Any] = {"index": 0, "finish_reason": "stop", "logprobs": None}
                if self.path.endswith("/chat/completions"):
                    choice["message"] = {"role": "assistant", "content": "OK"}
                    kind = "chat.completion"
                else:
                    choice["text"] = "OK"
                    kind = "text_completion"
                self._send(
                    {"id": "x", "object": kind, "created": 0, "model": LISTED, "choices": [choice]}
                )

            def log_message(self, *args: Any) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def completions(self) -> list[str]:
        return [p for p in self.paths if p.endswith("completions")]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeLlamacpp]:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    server = FakeLlamacpp()
    yield server
    server.server.shutdown()


def run(client: Any, model: str) -> dict[str, Any]:
    response = client.post(
        "/v1/settings/chat/test",
        json={"provider": "llamacpp", "model": model},
        headers=chat.ORIGIN,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_a_name_the_server_does_not_list_is_refused_without_a_prompt(
    setup: Any, configure: Any, fake: FakeLlamacpp
) -> None:
    configure(llamacpp_chat_url=fake.url, llamacpp_chat_server="external")
    body = run(setup, "qwen3:4b")
    assert (body["ok"], body["reason"]) == (False, "model-not-listed")
    assert fake.paths == ["/v1/models"]
    assert fake.completions() == []


def test_a_listed_name_gets_the_prompt(setup: Any, configure: Any, fake: FakeLlamacpp) -> None:
    configure(llamacpp_chat_url=fake.url, llamacpp_chat_server="external")
    body = run(setup, LISTED)
    assert (body["ok"], body["reason"]) == (True, None)
    assert fake.paths[0] == "/v1/models"
    assert len(fake.completions()) == 1


def test_managed_skips_the_list(setup: Any, configure: Any, fake: FakeLlamacpp) -> None:
    configure(llamacpp_chat_url=fake.url, llamacpp_chat_server="managed")
    body = run(setup, "Qwen/Qwen3-4B-GGUF:Q4_K_M")
    assert (body["ok"], body["reason"]) == (True, None)
    assert "/v1/models" not in fake.paths
    assert len(fake.completions()) == 1
