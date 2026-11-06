"""A router start with no downloaded model is ``not-downloaded``, not ``not-configured``.

Operator decision D-b (one-llamacpp-router). When no listed model has a file, the
start is refused with the existing reason ``not-downloaded``. Its line is "Models are
still downloading." while the process's downloader has one of the listed models
queued or running, else "No model is downloaded yet.". ``not-configured`` stays for a
list with no entry at all. A fake router ``llama-server`` stands in; nothing starts
here because every start is refused, and no network is used.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.unit.test_llamacpp_router_worker import (
    CHAT,
    CLEF,
    EMBED,
    RouterRig,
    as_entries,
    rig_fixture,
)

from omrs.integrations.llamacpp_runtime import rules
from omrs.integrations.llamacpp_runtime.lease import RuntimeUnavailable, reason_text
from omrs.integrations.llamacpp_runtime.router_lease import install_downloader, open_router
from omrs.integrations.llamacpp_runtime.router_spec import router_dir
from omrs.integrations.llamacpp_runtime.state import read_server_record, state_root

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

NOT_DOWNLOADED_LINE = "No model is downloaded yet."
DOWNLOADING_LINE = "Models are still downloading."


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from rig_fixture(tmp_path, monkeypatch)


class FakeDownloader:
    """The process's downloader: queues every request and reports it as running."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def request(self, model: str) -> None:
        self.asked.append(model)

    def downloading(self, model: str) -> bool:
        return model in self.asked


@pytest.fixture
def downloader() -> Iterator[FakeDownloader]:
    fake = FakeDownloader()
    install_downloader(fake)
    try:
        yield fake
    finally:
        install_downloader(None)


def _no_files(rig: RouterRig) -> list[object]:
    items = rig.entries()
    for item in items:
        item["file"] = None
    return as_entries(items)


def _refused(rig: RouterRig, entries: list[object]) -> RuntimeUnavailable:
    with pytest.raises(RuntimeUnavailable) as caught:
        open_router(rig.manager(), rig.spec(), entries).join()  # type: ignore[arg-type]
    assert rig.starts() == 0
    return caught.value


def test_the_reason_is_in_the_fixed_set_and_has_two_lines() -> None:
    assert "not-downloaded" in rules.REASONS
    assert reason_text("not-downloaded") == NOT_DOWNLOADED_LINE
    assert reason_text("not-downloaded", "downloading") == DOWNLOADING_LINE


def test_no_file_and_no_downloader_is_not_downloaded(rig: RouterRig) -> None:
    refused = _refused(rig, _no_files(rig))
    assert refused.reason == "not-downloaded"
    assert refused.reason_text == NOT_DOWNLOADED_LINE


def test_no_file_while_a_download_runs_says_so(rig: RouterRig, downloader: FakeDownloader) -> None:
    refused = _refused(rig, _no_files(rig))
    assert refused.reason == "not-downloaded"
    assert refused.reason_text == DOWNLOADING_LINE
    assert downloader.asked == [EMBED, CHAT, CLEF]  # the start asked for every model


def test_the_refusal_is_not_stored_so_a_restart_shows_no_old_failure(
    rig: RouterRig, downloader: FakeDownloader
) -> None:
    _refused(rig, _no_files(rig))
    record = read_server_record(router_dir(state_root()))
    assert record is not None
    assert (record.state, record.reason, record.reason_text) == ("stopped", None, None)


def test_a_list_with_no_entry_stays_not_configured(rig: RouterRig) -> None:
    refused = _refused(rig, [])
    assert refused.reason == "not-configured"
    assert refused.reason_text == "No program or model is set."
