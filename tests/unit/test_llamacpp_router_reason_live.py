"""The ``not-downloaded`` line follows live download state (one-llamacpp-router).

Spec ``llamacpp-server``, "Start moves to running or to a failed state", and the
operator decision of 2026-11-06 (A). While an automatic download of a listed model is
queued or runs, a Start that waits for it shows ``starting`` with the reason
``not-downloaded`` and the line "Models are still downloading.". After the download
fails or is cancelled, the status is ``failed`` with "No model is downloaded yet.".
The status is computed from the download state at read time. A fake router
``llama-server`` stands in; nothing starts because the start is refused.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_llamacpp_router_worker import EMBED, RouterRig, rig_fixture  # noqa: E402

from omrs.config.llamacpp_models import LlamaCppModelEntry  # noqa: E402
from omrs.integrations.llamacpp_runtime.router_lease import install_downloader  # noqa: E402
from omrs.transports.api.llamacpp_server import RouterConfig, RouterControl  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

DOWNLOADING_LINE = "Models are still downloading."
NOT_DOWNLOADED_LINE = "No model is downloaded yet."


class SwitchDownloader:
    """A downloader whose download runs until the test ends it."""

    def __init__(self) -> None:
        self.running = True

    def request(self, model: str) -> None:
        """Queue nothing: the download already runs."""

    def downloading(self, model: str) -> bool:
        return self.running


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from rig_fixture(tmp_path, monkeypatch)


@pytest.fixture
def downloader() -> Iterator[SwitchDownloader]:
    fake = SwitchDownloader()
    install_downloader(fake)
    try:
        yield fake
    finally:
        install_downloader(None)


def _config(rig: RouterRig) -> RouterConfig:
    return RouterConfig(
        mode="managed",
        binary=str(rig.binary),
        url=f"http://127.0.0.1:{rig.port}",
        models_max=4,
        memory_margin_mib=0,
        entries={"qwen3-embedding-4b": LlamaCppModelEntry(model=EMBED)},
    )


def test_the_line_changes_when_the_download_ends(
    rig: RouterRig, downloader: SwitchDownloader
) -> None:
    config = _config(rig)
    control = RouterControl(rig.manager())
    first = control.start(config)
    assert (first.state, first.reason, first.reason_text) == (
        "starting",
        "not-downloaded",
        DOWNLOADING_LINE,
    )
    assert rig.starts() == 0

    downloader.running = False  # the download failed or was cancelled

    later = control.status(config)
    assert (later.state, later.reason, later.reason_text) == (
        "failed",
        "not-downloaded",
        NOT_DOWNLOADED_LINE,
    )
    other = RouterControl(rig.manager()).status(config)  # another process reads the files only
    assert (other.state, other.reason, other.reason_text) == ("stopped", None, None)


def test_a_start_with_no_download_running_is_failed_at_once(
    rig: RouterRig, downloader: SwitchDownloader
) -> None:
    downloader.running = False
    status = RouterControl(rig.manager()).start(_config(rig))
    assert (status.state, status.reason_text) == ("failed", NOT_DOWNLOADED_LINE)
