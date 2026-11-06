"""Shared rig of the ``/v1/llamacpp/router`` route tests. It holds no test.

``rig()`` builds one app whose settings name a managed router on a free
loopback port and a fake ``llama-server`` (router mode, ``tests/fixtures/llamacpp``).
Model files are small files on disk. No real ``llama-server`` starts, no model
loads and no network is used.
"""

from __future__ import annotations

import os
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.llamacpp.harness import wait_until
from tests.fixtures.llamacpp.install import install_fake_server, read_start_log, write_fake_env
from tests.unit import test_web_connections_edit as edit
from tests.unit.test_llamacpp_router_worker import free_port

from omrs.config.llamacpp_models import CLASSIFY_MODEL, EMBED_MODEL
from omrs.core.answer.settings import AnswerSettings
from omrs.integrations import huggingface_models as hf_models
from omrs.integrations.llamacpp_runtime import process
from omrs.integrations.llamacpp_runtime.router_spec import router_dir
from omrs.integrations.llamacpp_runtime.state import state_root

harness = edit.harness
ORIGIN = edit.ORIGIN
URL = "/v1/llamacpp/router"
MODELS = f"{URL}/models"


class Rig:
    """One app, its fake program, its model files and its helper calls."""

    def __init__(self, h: Any, binary: Path, folder: Path, port: int) -> None:
        self.h, self.binary, self.folder, self.port = h, binary, folder, port
        self.client = h.client
        self.starts_file = folder / "starts.txt"

    # calls ------------------------------------------------------------

    def get(self) -> dict[str, Any]:
        response = self.client.get(URL)
        assert response.status_code == 200, response.text
        return response.json()

    def put(self, body: dict[str, Any]) -> Any:
        return self.client.put(URL, json=body, headers=ORIGIN)

    def post(self, action: str) -> Any:
        return self.client.post(f"{URL}/{action}", headers=ORIGIN)

    def put_model(self, entry_id: str, body: dict[str, Any]) -> Any:
        return self.client.put(f"{MODELS}/{entry_id}", json=body, headers=ORIGIN)

    def delete_model(self, entry_id: str, **params: str) -> Any:
        return self.client.delete(f"{MODELS}/{entry_id}", params=params, headers=ORIGIN)

    def wait_state(self, state: str) -> dict[str, Any]:
        assert wait_until(lambda: self.get()["state"] == state, 10), self.get()
        return self.get()

    # files ------------------------------------------------------------

    def model_file(self, name: str, content: bytes | None = None) -> str:
        """Return the path of a small ``.gguf`` file, created on first use."""
        path = self.folder / "models" / name
        path.parent.mkdir(exist_ok=True)
        if not path.exists():
            path.write_bytes(content if content is not None else b"GGUF " + name.encode())
        return str(path)

    def save_files(self) -> None:
        """Give both shipped entries a file, so the router has something to serve."""
        for entry_id, name in (("qwen3-embedding-4b", "e.gguf"), ("qwen3-4b", "c.gguf")):
            body = {"model": self.entry(entry_id)["model"], "file": self.model_file(name)}
            response = self.put_model(entry_id, body)
            assert response.status_code == 200, response.text

    def entry(self, entry_id: str) -> dict[str, Any]:
        return next(m for m in self.get()["models"] if m["id"] == entry_id)

    # state ------------------------------------------------------------

    def file_text(self) -> str:
        return self.h.file_text()

    def preset_text(self) -> str:
        path = router_dir(state_root()) / "models.ini"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def starts(self) -> list[dict[str, object]]:
        return read_start_log(self.starts_file)

    def pids(self) -> list[int]:
        return [int(entry["pid"]) for entry in self.starts()]  # type: ignore[call-overload]

    def jsonc(self) -> dict[str, Any]:
        """The parsed ``omrs.jsonc`` (comments stripped by the real parser)."""
        from omrs.config.user_config import parse_jsonc

        text = self.file_text()
        return parse_jsonc(text) if text else {}


def kill_all(rig: Rig) -> None:
    for pid in rig.pids():
        for kill in (os.killpg, os.kill):
            try:
                kill(pid, signal.SIGKILL)
                break
            except (ProcessLookupError, PermissionError):
                continue


@pytest.fixture
def rig(harness: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Return a factory: ``with rig(**settings) as r``.

    The app keeps its own runtime manager under this test's ``OMRS_STATE_DIR``. A
    start with an entry that has no file asks for its download (task 6.2a); the model
    host is refused here, so no test reaches the network unless it fakes the host.
    """
    monkeypatch.setattr(process, "HEALTH_POLL_SECONDS", 0.05)

    def no_network(*_args: Any, **_kwargs: Any) -> Any:
        raise hf_models.ModelHostError("network")

    for name in ("list_repo_files", "bytes_to_download", "download_files"):
        monkeypatch.setattr(hf_models, name, no_network)

    @contextmanager
    def build(**overrides: Any) -> Iterator[Rig]:
        binary = install_fake_server(tmp_path / "bin")
        write_fake_env(binary, FAKE_LLAMA_STARTS=str(tmp_path / "starts.txt"))
        port = free_port()
        overrides.setdefault("llamacpp_router_server", "managed")
        overrides.setdefault("llamacpp_router_url", f"http://127.0.0.1:{port}/v1")
        overrides.setdefault("llamacpp_server_binary", str(binary))
        overrides.setdefault("llamacpp_embed_model", EMBED_MODEL)
        overrides.setdefault("llamacpp_chat_model", CLASSIFY_MODEL)
        overrides.setdefault("answer", AnswerSettings(enabled=True, provider="llamacpp", model=""))
        with harness(**overrides) as h:
            state = Rig(h, binary, tmp_path, port)
            try:
                yield state
            finally:
                kill_all(state)

    return build


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


__all__ = ["MODELS", "ORIGIN", "URL", "Rig", "alive", "harness", "rig"]
