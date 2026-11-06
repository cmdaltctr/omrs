"""A listed model with no file downloads automatically (one-llamacpp-router, task 6.2a).

Spec ``llamacpp-router``, "A listed model with no file downloads automatically".
When the managed router starts, or a listed entry is first needed, and the entry
has no file, the Get a model job downloads it at a pinned revision. The path and
SHA-256 go into the entry through the Use this model writer, the entry goes into
``models.ini`` by file path and the model loads. The Hugging Face calls are faked
at their module and a fake router ``llama-server`` stands in; no network is used.
"""

from __future__ import annotations

import hashlib
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.fixtures.llamacpp.harness import wait_until  # noqa: E402
from tests.unit import test_web_llamacpp_router_support as support  # noqa: E402

from omrs import compose_runtimes  # noqa: E402
from omrs.config.llamacpp_models import CLASSIFY_MODEL, EMBED_MODEL  # noqa: E402
from omrs.core import runtime_gate  # noqa: E402
from omrs.integrations import huggingface_models as hf  # noqa: E402
from omrs.integrations.llamacpp_runtime import process  # noqa: E402
from omrs.transports.api.routes import model_downloads as download_routes  # noqa: E402

harness = support.harness
rig = support.rig

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

REV = "c" * 40
SIZE = 4_000_000
CURRENT = "/v1/model-downloads/current"
NEW_MODEL = "Qwen/Qwen3-1.7B-GGUF:Q8_0"


def _content(repo: str) -> bytes:
    return b"GGUF " + repo.encode()


class FakeHub:
    """The Hugging Face calls of the download job; each download waits on ``gate``."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.gate = threading.Event()
        self.listed: list[tuple[str, str | None]] = []
        self.downloads: list[tuple[str, str, tuple[str, ...]]] = []

    def list_repo_files(self, repo: str, *, revision: str | None = None, **_: Any) -> Any:
        self.listed.append((repo, revision))
        name = repo.split("/")[1].removesuffix("-GGUF") + "-Q8_0.gguf"
        return hf.RepoFiles(repo, REV, False, ((name, SIZE),))

    def bytes_to_download(self, repo: str, revision: str, files: Any, *, token: Any) -> int:
        return SIZE

    def download_files(
        self, repo: str, revision: str, files: Any, *, on_bytes: Any, cancel: Any, token: Any
    ) -> str:
        self.downloads.append((repo, revision, tuple(files)))
        on_bytes(10)
        while not self.gate.is_set():
            if cancel.is_set():
                raise hf.DownloadCancelled
            time.sleep(0.01)
        path = self.folder / files[0]
        path.write_bytes(_content(repo))
        return str(path)


@pytest.fixture
def hub(rig: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeHub]:
    fake = FakeHub(tmp_path / "hub")
    fake.folder.mkdir()
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(hf, "list_repo_files", fake.list_repo_files)
    monkeypatch.setattr(hf, "bytes_to_download", fake.bytes_to_download)
    monkeypatch.setattr(hf, "download_files", fake.download_files)
    monkeypatch.setattr(hf, "hub_cache_folder", lambda: str(fake.folder))
    monkeypatch.setattr(download_routes, "_free_bytes", lambda _path: 100 * 1000**3)
    yield fake
    fake.gate.set()
    compose_runtimes.reset()


def _embed_file_only(r: Any) -> None:
    body = {"model": EMBED_MODEL, "file": r.model_file("e.gguf")}
    assert r.put_model("qwen3-embedding-4b", body).status_code == 200


def _current(r: Any) -> dict[str, Any]:
    return r.client.get(CURRENT).json()  # type: ignore[no-any-return]


def test_a_missing_file_at_start_downloads_records_and_loads_the_model(
    rig: Any, hub: FakeHub
) -> None:
    """Spec scenario "First start downloads missing models"."""
    with rig() as r:
        _embed_file_only(r)
        assert r.post("start").json()["state"] == "running"
        assert wait_until(lambda: _current(r)["state"] == "running", 10), _current(r)
        assert _current(r)["model"] == CLASSIFY_MODEL
        assert hub.listed[0] == ("Qwen/Qwen3-4B-GGUF", None)
        assert wait_until(lambda: bool(hub.downloads), 10)
        assert hub.downloads[0] == ("Qwen/Qwen3-4B-GGUF", REV, ("Qwen3-4B-Q8_0.gguf",))
        entry = r.entry("qwen3-4b")
        assert (entry["state"], entry["note"]) == ("not-downloaded", "Downloading")

        hub.gate.set()

        assert wait_until(lambda: r.entry("qwen3-4b")["state"] == "loaded", 20), r.entry("qwen3-4b")
        saved = r.jsonc()["llamacpp_models"]["qwen3-4b"]
        assert saved["file"] == str(hub.folder / "Qwen3-4B-Q8_0.gguf")
        assert saved["sha256"] == hashlib.sha256(_content("Qwen/Qwen3-4B-GGUF")).hexdigest()
        assert f"model = {saved['file']}" in r.preset_text()
        assert len(r.pids()) == 1  # the running router reloaded its list; it did not restart
        assert r.entry("qwen3-4b")["note"] is None


def test_a_slow_download_is_not_timeout_and_requests_do_not_wait(
    rig: Any, hub: FakeHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec scenario "A slow download does not time out the router"."""
    monkeypatch.setattr(process, "HEALTH_TIMEOUT_SECONDS", 1.0)
    with rig() as r:
        _embed_file_only(r)
        assert r.post("start").json()["state"] == "running"
        assert wait_until(lambda: bool(hub.downloads), 10)
        time.sleep(1.5)  # the router start wait has passed; the download still runs

        body = r.get()
        assert (body["state"], body["reason"]) == ("running", None)
        assert r.entry("qwen3-4b")["note"] == "Downloading"
        compose_runtimes.install_gates(r.h.app.state.runtime.providers.source)
        gate = runtime_gate.gate_for("classification")
        assert gate is not None
        began = time.monotonic()
        with pytest.raises(runtime_gate.GateRefused) as refused:
            gate.request(lambda url: url, model=CLASSIFY_MODEL)
        assert refused.value.reason == "not-downloaded"
        assert time.monotonic() - began < 1.0  # refused at once, not after a wait
        assert len(hub.downloads) == 1  # the running download is not started twice


def test_with_no_file_at_all_both_download_and_the_router_then_serves(
    rig: Any, hub: FakeHub
) -> None:
    """No listed model has a file: the start is ``not-downloaded``, never ``timeout``."""
    with rig() as r:
        body = r.post("start").json()
        assert (body["state"], body["reason"]) == ("failed", "not-downloaded")
        assert body["reason_text"] == "Models are still downloading."
        assert wait_until(lambda: bool(hub.downloads), 10)
        notes = {m["id"]: m["note"] for m in r.get()["models"]}
        assert notes == {"qwen3-embedding-4b": "Downloading", "qwen3-4b": "Downloading"}

        hub.gate.set()

        def both_loaded() -> bool:
            return {m["state"] for m in r.get()["models"]} == {"loaded"}

        assert wait_until(both_loaded, 30), r.get()
        assert r.get()["state"] == "running"
        assert [d[0] for d in hub.downloads] == [
            "Qwen/Qwen3-Embedding-4B-GGUF",
            "Qwen/Qwen3-4B-GGUF",
        ]


def test_a_request_for_a_listed_model_with_no_file_starts_its_download(
    rig: Any, hub: FakeHub
) -> None:
    """The other trigger: an entry is first needed while the router runs."""
    with rig() as r:
        r.save_files()
        assert r.post("start").json()["state"] == "running"
        assert r.put_model("qwen3-1-7b", {"model": NEW_MODEL}).status_code == 200
        assert hub.downloads == []
        compose_runtimes.install_gates(r.h.app.state.runtime.providers.source)
        gate = runtime_gate.gate_for("classification")
        assert gate is not None
        with pytest.raises(runtime_gate.GateRefused):
            gate.request(lambda url: url, model=NEW_MODEL)

        assert wait_until(lambda: bool(hub.downloads), 10)
        assert hub.downloads[0][:2] == ("Qwen/Qwen3-1.7B-GGUF", REV)
        hub.gate.set()
        assert wait_until(lambda: r.entry("qwen3-1-7b")["state"] == "loaded", 20)
