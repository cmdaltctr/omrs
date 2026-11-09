"""A status read answers while a Start waits for the router (one-llamacpp-router, design D8).

``RouterControl.start`` holds the control lock for the whole join, which can wait up
to 180 s for ``llama-server`` health. The Settings panel polls ``status`` during that
time and must see ``starting``, not hang until the Start ends. A fake router whose
``join`` blocks on an event stands in for the slow start; no process is started.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_llamacpp_router_worker import CHAT, EMBED, RouterRig, rig_fixture  # noqa: E402

from omrs.config.llamacpp_models import LlamaCppModelEntry  # noqa: E402
from omrs.transports.api import llamacpp_server  # noqa: E402
from omrs.transports.api.llamacpp_server import RouterConfig, RouterControl  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

START_SECONDS = 1.5  # how long the fake join blocks
PROMPT_SECONDS = 0.5  # a status read must come back well inside the start


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from rig_fixture(tmp_path, monkeypatch)


def _config(rig: RouterRig) -> RouterConfig:
    entries = {
        "embed": LlamaCppModelEntry(model=EMBED, file=rig.file("e.gguf")),
        "chat": LlamaCppModelEntry(model=CHAT, file=rig.file("c.gguf")),
    }
    return RouterConfig(
        mode="managed",
        binary=str(rig.binary),
        url=f"http://127.0.0.1:{rig.port}",
        models_max=4,
        memory_margin_mib=0,
        entries=entries,
    )


class _SlowRouter:
    """Stands in for the router lease: ``join`` blocks, as a wait for health does."""

    def __init__(self, entered: threading.Event, release: threading.Event) -> None:
        self.base = SimpleNamespace(operator_stopped=False)
        self.ask_downloads = True
        self._entered = entered
        self._release = release

    def join(self) -> None:
        self._entered.set()
        self._release.wait(START_SECONDS)

    def leave(self) -> None:
        return None


def test_a_status_read_answers_while_a_start_is_inside_the_join(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The poll returns at once; it does not wait for the Start to finish."""
    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(
        llamacpp_server, "open_router", lambda *a, **k: _SlowRouter(entered, release)
    )
    control = RouterControl(rig.manager())
    config = _config(rig)
    starter = threading.Thread(target=control.start, args=(config,), daemon=True)
    starter.start()
    try:
        assert entered.wait(10), "the Start never reached the join"

        began = time.monotonic()
        control.status(config)
        waited = time.monotonic() - began

        assert waited < PROMPT_SECONDS, f"status waited {waited:.2f} s for the Start"
        assert starter.is_alive(), "the Start ended before the status read"
    finally:
        release.set()
        starter.join(10)
