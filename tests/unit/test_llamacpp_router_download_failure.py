"""A failed automatic download ends the wait and queues nothing again (one-llamacpp-router).

Spec ``llamacpp-server``, "A first start waits for its downloads", scenario "Every
download fails". The defect: when the model host could not be read, a waiting Start
retried about 90 times a second, because ``RouterControl.load`` started the router
again and the start asked for the same download again. These tests count the download
attempts. The Hugging Face calls are faked at their module and a fake router
``llama-server`` stands in; no network is used.
"""

from __future__ import annotations

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
from omrs.integrations import huggingface_models as hf  # noqa: E402
from omrs.transports.api.routes import model_downloads as download_routes  # noqa: E402

harness = support.harness
rig = support.rig

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

REV = "e" * 40
SIZE = 4_000_000
EMBED_REPO = "Qwen/Qwen3-Embedding-4B-GGUF"
CHAT_REPO = "Qwen/Qwen3-4B-GGUF"
FAILED_LINE = "No model is downloaded yet."
SETTLE_SECONDS = 0.6  # a spin makes about 90 attempts in this time


class Hub:
    """The Hugging Face calls of the download job, with a count of each attempt.

    Attributes:
        plan_fails: Repos whose file listing raises ``network`` (the plan fails).
        transfer_fails: Repos whose transfer raises ``network``.
        listed: Every repo an attempt read first (no pinned revision), in order.
        transfers: Every repo a transfer started for, in order.
        hold: While clear, a listing waits (a slow host).
    """

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.plan_fails: set[str] = set()
        self.transfer_fails: set[str] = set()
        self.listed: list[str] = []
        self.transfers: list[str] = []
        self.hold = threading.Event()
        self.hold.set()

    def list_repo_files(self, repo: str, *, revision: str | None = None, **_: Any) -> Any:
        if revision is not None:  # the pinned read inside the planner, not a new attempt
            return hf.RepoFiles(repo, REV, False, ((self._name(repo), SIZE),))
        self.listed.append(repo)
        assert self.hold.wait(10)
        if repo in self.plan_fails:
            raise hf.ModelHostError("network")
        return hf.RepoFiles(repo, REV, False, ((self._name(repo), SIZE),))

    @staticmethod
    def _name(repo: str) -> str:
        return repo.split("/")[1].removesuffix("-GGUF") + "-Q8_0.gguf"

    def bytes_to_download(self, repo: str, revision: str, files: Any, *, token: Any) -> int:
        return SIZE

    def download_files(self, repo: str, revision: str, files: Any, **_: Any) -> str:
        self.transfers.append(repo)
        if repo in self.transfer_fails:
            raise hf.ModelHostError("network")
        path = self.folder / files[0]
        path.write_bytes(b"GGUF " + repo.encode())
        return str(path)


@pytest.fixture
def hub(rig: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Hub]:
    fake = Hub(tmp_path / "hub")
    fake.folder.mkdir()
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(hf, "list_repo_files", fake.list_repo_files)
    monkeypatch.setattr(hf, "bytes_to_download", fake.bytes_to_download)
    monkeypatch.setattr(hf, "download_files", fake.download_files)
    monkeypatch.setattr(hf, "hub_cache_folder", lambda: str(fake.folder))
    monkeypatch.setattr(download_routes, "_free_bytes", lambda _path: 100 * 1000**3)
    yield fake
    fake.hold.set()
    compose_runtimes.reset()


def _attempts(hub: Hub) -> int:
    """Return the downloads that were asked for: one first read per attempt."""
    return len(hub.listed)


def _settled(hub: Hub) -> int:
    """Wait a short while, then return the attempt count (a spin would raise it)."""
    time.sleep(SETTLE_SECONDS)
    return _attempts(hub)


def _fail_both(hub: Hub, kind: str) -> None:
    target = hub.plan_fails if kind == "plan" else hub.transfer_fails
    target.update({EMBED_REPO, CHAT_REPO})


@pytest.mark.parametrize("kind", ["plan", "transfer"])
def test_every_download_failing_ends_failed_with_one_attempt_per_model(
    rig: Any, hub: Hub, kind: str
) -> None:
    """Spec "Every download fails": the wait ends, and nothing asks again by itself."""
    _fail_both(hub, kind)
    with rig() as r:
        first = r.post("start").json()
        assert first["reason"] == "not-downloaded"
        # No status read while the attempts run: a read ends the wait by itself and
        # would hide the loop.
        assert wait_until(lambda: _attempts(hub) >= 2, 10), hub.listed

        assert _settled(hub) == 2  # the embedding model and the chat model, once each
        body = r.get()
        assert (body["state"], body["reason"]) == ("failed", "not-downloaded")
        assert body["reason_text"] == FAILED_LINE
        assert r.pids() == []
        assert {m["note"] for m in body["models"]} == {None}  # nothing is downloading


@pytest.mark.parametrize("kind", ["plan", "transfer"])
def test_a_new_start_after_the_failure_asks_once_more_for_each_model(
    rig: Any, hub: Hub, kind: str
) -> None:
    _fail_both(hub, kind)
    with rig() as r:
        r.post("start")
        assert wait_until(lambda: _attempts(hub) >= 2, 10), hub.listed
        assert _settled(hub) == 2
        assert r.get()["state"] == "failed"

        r.post("start")

        assert wait_until(lambda: _attempts(hub) >= 4, 10), hub.listed
        assert _settled(hub) == 4
        assert r.get()["state"] == "failed"
        assert r.get()["reason_text"] == FAILED_LINE


def test_a_transfer_that_fails_is_counted_once_per_model(rig: Any, hub: Hub) -> None:
    _fail_both(hub, "transfer")
    with rig() as r:
        r.post("start")
        assert wait_until(lambda: len(hub.transfers) >= 2, 10), hub.transfers

        assert _settled(hub) == 2
        assert r.get()["state"] == "failed"
        assert sorted(hub.transfers) == sorted([EMBED_REPO, CHAT_REPO])


def test_stop_ends_a_wait_at_once_and_the_failed_plans_start_nothing(rig: Any, hub: Hub) -> None:
    """A slow host keeps the wait open; Stop ends it; the plans then fail into silence."""
    _fail_both(hub, "plan")
    hub.hold.clear()
    with rig() as r:
        body = r.post("start").json()
        assert (body["state"], body["reason"]) == ("starting", "not-downloaded")
        assert wait_until(lambda: bool(hub.listed), 10)

        stopped = r.post("stop").json()
        hub.hold.set()

        assert stopped["state"] == "stopped"
        assert _settled(hub) == 2
        body = r.get()
        assert (body["state"], body["reason"]) == ("stopped", None)
        assert r.pids() == []


def test_stop_ends_the_failed_state_too(rig: Any, hub: Hub) -> None:
    _fail_both(hub, "plan")
    with rig() as r:
        r.post("start")
        assert wait_until(lambda: _attempts(hub) >= 2, 10), hub.listed
        assert _settled(hub) == 2
        assert r.get()["state"] == "failed"

        assert r.post("stop").json()["state"] == "stopped"

        assert _settled(hub) == 2
        assert r.get()["state"] == "stopped"


def test_the_first_model_arrives_and_the_second_fails_so_it_is_asked_for_once(
    rig: Any, hub: Hub
) -> None:
    """The router starts with the file that arrived; the failed model gets no second try."""
    hub.plan_fails.add(CHAT_REPO)
    with rig() as r:
        r.post("start")

        def states() -> dict[str, str]:
            return {m["id"]: m["state"] for m in r.get()["models"]}

        expected = {"qwen3-embedding-4b": "loaded", "qwen3-4b": "not-downloaded"}
        assert wait_until(lambda: states() == expected, 30), r.get()

        assert _settled(hub) == 2  # the embedding model once, the chat model once
        assert hub.listed.count(CHAT_REPO) == 1
        assert r.get()["state"] == "running"
