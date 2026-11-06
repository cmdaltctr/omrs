"""A first Start waits for the downloads and then starts by itself (one-llamacpp-router).

Operator decision A (2026-11-06), spec ``llamacpp-server`` "Start moves to running or
failed" and ``llamacpp-router`` "A listed model with no file downloads automatically".
While a Start waits only for the automatic downloads of listed models, the router is
``starting`` with the reason ``not-downloaded``, never ``failed``. When the last
download is recorded, the router starts by itself, unless the operator stopped it, the
mode became ``external``, or a download failed or was cancelled (then the state is
``failed`` ``not-downloaded``). After a server restart nothing shows a failure from
before. A fake router ``llama-server`` stands in; no network is used.
"""

from __future__ import annotations

import dataclasses
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_llamacpp_router_worker import CHAT, EMBED, RouterRig, rig_fixture  # noqa: E402

from omrs.config.llamacpp_models import LlamaCppModelEntry  # noqa: E402
from omrs.integrations.llamacpp_runtime.router_lease import install_downloader  # noqa: E402
from omrs.integrations.llamacpp_runtime.router_spec import router_dir  # noqa: E402
from omrs.integrations.llamacpp_runtime.state import (  # noqa: E402
    ServerRecord,
    read_server_record,
    state_root,
    write_server_record,
)
from omrs.transports.api.llamacpp_server import RouterConfig, RouterControl  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

DOWNLOADING_LINE = "Models are still downloading."
NOT_DOWNLOADED_LINE = "No model is downloaded yet."


class Downloader:
    """The process's downloader: a model is active from its request until the test ends it."""

    def __init__(self) -> None:
        self.active: set[str] = set()
        self.requests: list[str] = []

    def request(self, model: str) -> None:
        self.requests.append(model)
        self.active.add(model)

    def downloading(self, model: str) -> bool:
        return model in self.active


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from rig_fixture(tmp_path, monkeypatch)


@pytest.fixture
def downloader() -> Iterator[Downloader]:
    fake = Downloader()
    install_downloader(fake)
    try:
        yield fake
    finally:
        install_downloader(None)


def _config(
    rig: RouterRig, *, embed: bool = False, chat: bool = False, **change: str
) -> RouterConfig:
    """The shipped two entries; a flag gives the entry its file (its download is recorded)."""
    entries = {
        "embed": LlamaCppModelEntry(model=EMBED, file=rig.file("e.gguf") if embed else None),
        "chat": LlamaCppModelEntry(model=CHAT, file=rig.file("c.gguf") if chat else None),
    }
    config = RouterConfig(
        mode="managed",
        binary=str(rig.binary),
        url=f"http://127.0.0.1:{rig.port}",
        models_max=4,
        memory_margin_mib=0,
        entries=entries,
    )
    return dataclasses.replace(config, **change)


def _triple(status: object) -> tuple[object, object, object]:
    return (status.state, status.reason, status.reason_text)  # type: ignore[attr-defined]


def test_a_start_that_waits_for_downloads_is_starting_not_failed(
    rig: RouterRig, downloader: Downloader
) -> None:
    control = RouterControl(rig.manager())

    status = control.start(_config(rig))

    assert _triple(status) == ("starting", "not-downloaded", DOWNLOADING_LINE)
    assert {m.note for m in status.models.values()} == {"Downloading"}
    assert rig.starts() == 0
    assert downloader.active == {EMBED, CHAT}


def test_a_refused_start_leaves_no_failure_record_behind(
    rig: RouterRig, downloader: Downloader
) -> None:
    RouterControl(rig.manager()).start(_config(rig))

    record = read_server_record(router_dir(state_root()))
    assert record is None or record.reason is None


def test_the_last_download_starts_the_router_and_loads_both_models(
    rig: RouterRig, downloader: Downloader
) -> None:
    control = RouterControl(rig.manager())
    control.start(_config(rig))

    control.load(_config(rig, embed=True), EMBED)  # chat still downloads

    assert rig.starts() == 0
    assert _triple(control.status(_config(rig, embed=True))) == (
        "starting",
        "not-downloaded",
        DOWNLOADING_LINE,
    )

    downloader.active.discard(EMBED)
    control.load(_config(rig, embed=True, chat=True), CHAT)  # the last one

    assert rig.starts() == 1
    done = control.status(_config(rig, embed=True, chat=True))
    assert (done.state, done.reason) == ("running", None)
    assert {m.state for m in done.models.values()} == {"loaded"}


def test_a_stop_while_it_waits_means_no_start_after_the_download(
    rig: RouterRig, downloader: Downloader
) -> None:
    control = RouterControl(rig.manager())
    control.start(_config(rig))

    stopped = control.stop(_config(rig))
    assert _triple(stopped)[0] == "stopped"

    control.load(_config(rig, embed=True, chat=True), CHAT)

    assert rig.starts() == 0
    assert control.status(_config(rig, embed=True, chat=True)).state == "stopped"


def test_a_download_that_ends_after_a_change_to_external_starts_nothing(
    rig: RouterRig, downloader: Downloader
) -> None:
    control = RouterControl(rig.manager())
    control.start(_config(rig))

    control.load(_config(rig, embed=True, chat=True, mode="external"), CHAT)

    assert rig.starts() == 0
    back = control.status(_config(rig, embed=True, chat=True))  # managed again
    assert _triple(back) == ("stopped", None, None)


def test_reading_the_external_mode_ends_a_waiting_start(
    rig: RouterRig, downloader: Downloader
) -> None:
    control = RouterControl(rig.manager())
    control.start(_config(rig))

    control.status(_config(rig, mode="external"))  # the mode row, read

    assert _triple(control.status(_config(rig))) == ("stopped", None, None)
    assert rig.starts() == 0


def test_a_failed_or_cancelled_download_is_failed_not_downloaded(
    rig: RouterRig, downloader: Downloader
) -> None:
    control = RouterControl(rig.manager())
    control.start(_config(rig))

    downloader.active.clear()  # the downloads ended and left no file

    assert _triple(control.status(_config(rig))) == (
        "failed",
        "not-downloaded",
        NOT_DOWNLOADED_LINE,
    )
    assert _triple(control.status(_config(rig))) == (
        "failed",
        "not-downloaded",
        NOT_DOWNLOADED_LINE,
    )
    assert rig.starts() == 0


def test_a_start_with_no_downloader_is_failed_at_once(rig: RouterRig) -> None:
    status = RouterControl(rig.manager()).start(_config(rig))

    assert _triple(status) == ("failed", "not-downloaded", NOT_DOWNLOADED_LINE)


def test_after_a_restart_with_no_download_the_router_is_stopped_not_failed(
    rig: RouterRig, downloader: Downloader
) -> None:
    RouterControl(rig.manager()).start(_config(rig))
    downloader.active.clear()  # the server restarted: no download runs

    fresh = RouterControl(rig.manager()).status(_config(rig))

    assert _triple(fresh) == ("stopped", None, None)


def test_a_stored_not_downloaded_failure_from_an_older_start_is_ignored(rig: RouterRig) -> None:
    folder = router_dir(state_root())
    folder.mkdir(parents=True, exist_ok=True)
    write_server_record(
        folder,
        ServerRecord(
            pid=0,
            port=0,
            binary=str(rig.binary),
            digest="x",
            build=None,
            state="stopped",
            generation=1,
            reason="not-downloaded",
            reason_text="No model is downloaded yet.",
        ),
    )

    status = RouterControl(rig.manager()).status(_config(rig))

    assert _triple(status) == ("stopped", None, None)


def test_a_download_with_no_pending_start_does_not_start_the_router(
    rig: RouterRig, downloader: Downloader
) -> None:
    control = RouterControl(rig.manager())

    control.load(_config(rig, embed=True, chat=True), CHAT)

    assert rig.starts() == 0


def test_a_download_loads_its_model_into_a_router_that_already_runs(
    rig: RouterRig, downloader: Downloader
) -> None:
    control = RouterControl(rig.manager())
    assert control.start(_config(rig, chat=True)).state == "running"  # one file is enough

    control.load(_config(rig, embed=True, chat=True), EMBED)

    states = {
        m: s.state for m, s in control.status(_config(rig, embed=True, chat=True)).models.items()
    }
    assert states[EMBED] == "loaded"


def test_a_failed_download_reported_after_the_start_is_not_asked_for_again(
    rig: RouterRig, downloader: Downloader
) -> None:
    """The last download failed while the first succeeded: the router starts with the first.

    The report of a failed model must not call ``ensure_ready`` on it, because that asks for
    its download again, and a failure would then report again without end.
    """
    control = RouterControl(rig.manager())
    control.start(_config(rig))
    control.load(_config(rig, embed=True), EMBED)  # the first one is in; chat still downloads
    downloader.active.clear()  # chat failed: no download runs any more

    control.load(_config(rig, embed=True), CHAT)  # the failed one reports, with no file

    assert rig.starts() == 1
    done = control.status(_config(rig, embed=True))
    assert (done.state, done.reason) == ("running", None)
    assert done.models[EMBED].state == "loaded"
    assert done.models[CHAT].state == "not-downloaded"

    asked = list(downloader.requests)
    downloader.active.clear()
    control.load(_config(rig, embed=True), CHAT)  # it fails again

    assert downloader.requests == asked
