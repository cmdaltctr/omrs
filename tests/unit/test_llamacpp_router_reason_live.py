"""The ``not-downloaded`` line follows the live download state (one-llamacpp-router).

Spec ``llamacpp-server``, "Start moves to a running or failed state": the line
reads "Models are still downloading." while an automatic download of a listed
model is queued or runs, and "No model is downloaded yet." otherwise; the status
computes the line from the download state at the time of the read. A start
refused while a download ran stores the first line in ``server.json``. After the
download fails or is cancelled, the status must not show it any more. A fake
router ``llama-server`` stands in; nothing starts because the start is refused.
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
    yield fake
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
        "failed",
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
    other = RouterControl(rig.manager()).status(config)  # reads server.json only
    assert (other.reason, other.reason_text) == ("not-downloaded", NOT_DOWNLOADED_LINE)


def test_a_download_that_starts_later_shows_the_downloading_line(
    rig: RouterRig, downloader: SwitchDownloader
) -> None:
    config = _config(rig)
    downloader.running = False
    control = RouterControl(rig.manager())
    assert control.start(config).reason_text == NOT_DOWNLOADED_LINE

    downloader.running = True  # a later request queued the download

    assert control.status(config).reason_text == DOWNLOADING_LINE
