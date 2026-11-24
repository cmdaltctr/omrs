"""The live router wiring of the Experiment 35 runner (``live35.LiveDeps``).

Rule under test (task 7.4, A5 R-5, H-17): ``LiveDeps.router`` holds one
router session (``router_config.held``) around the whole stage body, so the
600-second idle stop cannot end the router mid-stage. The router object is a
stub; nothing starts llama-server or opens a socket.
"""

from __future__ import annotations

import contextlib
import importlib
from collections.abc import Iterator
from typing import Any

import pytest
from tests._exp35_fixtures import load

live35 = load("live35")

ENTRY = {
    "role": "embedding",
    "file": "Qwen3-Embedding-4B-Q8_0.gguf",
    "repository": "Qwen/Qwen3-Embedding-4B-GGUF",
}


class _Router:
    """A router lease stub that records each session it opens and closes."""

    def __init__(self, events: list[Any]) -> None:
        self.events = events

    @contextlib.contextmanager
    def model_session(self, name: str) -> Iterator[None]:
        self.events.append(("open", name))
        yield
        self.events.append(("close", name))


def test_the_live_router_holds_one_session_around_the_stage_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from experiments._lib import router_env

    monkeypatch.syspath_prepend(str(live35.EXP48_DIR))
    router_config = importlib.import_module("router_config")
    events: list[Any] = []
    started: list[list[str]] = []

    def start_router(files: list[str], plan: Any) -> _Router:
        started.append(list(files))
        return _Router(events)

    monkeypatch.setattr(router_config, "start_router", start_router)
    with live35.LiveDeps().router(ENTRY) as endpoint:
        events.append("body")
        events.append("body")
    name = router_config.model_name(ENTRY)
    assert started == [[ENTRY["file"]]]
    assert endpoint == router_env.ROUTER_URL
    assert events == [("open", name), "body", "body", ("close", name)]
