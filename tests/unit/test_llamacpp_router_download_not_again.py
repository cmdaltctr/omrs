"""A failed or cancelled automatic download is not asked for again by a request.

Spec ``llamacpp-router``, "A listed model with no file downloads automatically".
``RouterLease.model_session`` asks for the download of an entry with no file on every
request. The defect: after a failed or cancelled download each next request queued the
same download again. Only the user's next Start asks again. These tests count the
attempts at the faked model host. No network is used.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.fixtures.llamacpp.harness import wait_until  # noqa: E402
from tests.unit import test_llamacpp_router_download_failure as failure  # noqa: E402

from omrs.config.llamacpp_models import CLASSIFY_MODEL, EMBED_MODEL  # noqa: E402
from omrs.integrations import huggingface_models as hf  # noqa: E402
from omrs.integrations.llamacpp_runtime.router_lease import ask_download  # noqa: E402

rig = failure.rig
harness = failure.harness
hub = failure.hub

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

MODELS = (EMBED_MODEL, CLASSIFY_MODEL)


def _cancel_every_transfer(hub: failure.Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    def cancelled(repo: str, *_: Any, **__: Any) -> str:
        hub.transfers.append(repo)
        raise hf.DownloadCancelled

    monkeypatch.setattr(hf, "download_files", cancelled)


def _request_path_asks(times: int) -> None:
    """Ask as ``RouterLease.model_session`` does for each entry with no file."""
    for _ in range(times):
        for model in MODELS:
            ask_download(model)


def _calls(hub: failure.Hub) -> tuple[int, int]:
    return len(hub.listed), len(hub.transfers)


def test_a_cancelled_download_is_not_queued_again_by_requests(
    rig: Any, hub: failure.Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cancel_every_transfer(hub, monkeypatch)
    with rig() as r:
        r.post("start")
        assert wait_until(lambda: len(hub.transfers) >= 2, 10), hub.transfers
        assert failure._settled(hub) == 2
        assert r.get()["state"] == "failed"
        before = _calls(hub)

        _request_path_asks(2)

        assert failure._settled(hub) == 2
        assert _calls(hub) == before
        assert r.entry("qwen3-4b")["note"] is None  # nothing is queued or running


def test_a_failed_plan_is_not_asked_for_again_and_makes_no_host_call(
    rig: Any, hub: failure.Hub
) -> None:
    failure._fail_both(hub, "plan")
    with rig() as r:
        r.post("start")
        assert wait_until(lambda: len(hub.listed) >= 2, 10), hub.listed
        assert failure._settled(hub) == 2
        before = _calls(hub)

        _request_path_asks(2)

        assert failure._settled(hub) == 2
        assert _calls(hub) == before
        assert r.entry("qwen3-4b")["note"] is None


def test_the_users_next_start_clears_the_record_and_asks_once(rig: Any, hub: failure.Hub) -> None:
    failure._fail_both(hub, "plan")
    with rig() as r:
        r.post("start")
        assert wait_until(lambda: len(hub.listed) >= 2, 10), hub.listed
        assert failure._settled(hub) == 2
        _request_path_asks(2)
        assert failure._settled(hub) == 2

        r.post("start")

        assert wait_until(lambda: len(hub.listed) >= 4, 10), hub.listed
        assert failure._settled(hub) == 4  # once for each model
        _request_path_asks(2)
        assert failure._settled(hub) == 4  # and the requests after it stay quiet


class _Loop:
    """An event loop stand-in that records what is queued."""

    def __init__(self) -> None:
        self.queued: list[str] = []

    def call_soon_threadsafe(self, _call: Any, model: str) -> None:
        self.queued.append(model)


def _downloads(manual: dict[str, Any] | None) -> tuple[Any, _Loop]:
    """Return a downloader whose Get a model job shows *manual*, and its loop."""
    from types import SimpleNamespace

    from omrs.transports.api.router_autodownload import RouterDownloads

    job = SimpleNamespace(snapshot=lambda: manual or {"state": "idle", "model": None})
    app = SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(model_downloads=job)))
    loop = _Loop()
    return RouterDownloads(app, loop), loop  # type: ignore[arg-type]


def test_a_get_a_model_download_of_that_model_lets_a_request_ask_again() -> None:
    downloads, loop = _downloads({"state": "running", "model": EMBED_MODEL})
    downloads._failed.update(MODELS)

    downloads.request(EMBED_MODEL)
    downloads.request(CLASSIFY_MODEL)  # the manual job is for the other model

    assert loop.queued == [EMBED_MODEL]
    assert downloads._failed == {CLASSIFY_MODEL}


def test_a_finished_get_a_model_download_does_not_clear_the_record() -> None:
    downloads, loop = _downloads({"state": "cancelled", "model": EMBED_MODEL})
    downloads._failed.add(EMBED_MODEL)

    downloads.request(EMBED_MODEL)

    assert loop.queued == []
