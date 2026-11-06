"""Per-model client and request locks across processes (task 4.1; design D8).

Each listed model has ``models/<model id>/clients.lock`` and, for a one-slot
entry (``parallel = 1``), ``request.lock``. A one-slot model serialises
requests across processes; a request to another model does not wait.
"""

from __future__ import annotations

import random
import sys
import time
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

from omrs.integrations.llamacpp_runtime.locks import LockFile
from omrs.integrations.llamacpp_runtime.router_lease import open_router
from omrs.integrations.llamacpp_runtime.router_spec import model_dir, model_id
from omrs.integrations.llamacpp_runtime.state import state_root

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

HOLD = 1.5


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from rig_fixture(tmp_path, monkeypatch)


def test_model_folder_name_is_shared_by_every_process(rig: RouterRig) -> None:
    """Spec scenario "Same model folder in every process"."""
    one = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    with one.model_session(CHAT):
        pass
    folder = model_dir(state_root(), CHAT)
    assert folder.name == model_id(CHAT)
    assert (folder / "clients.lock").exists()
    assert not (folder / "request.lock").exists()  # parallel = 2: no request lock


def test_session_holds_the_model_clients_lock(rig: RouterRig) -> None:
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    with router.model_session(CHAT):
        pass
    probe = LockFile(model_dir(state_root(), CHAT) / "clients.lock")
    try:
        assert probe.acquire(shared=False, blocking=False) is False  # held until leave
    finally:
        probe.close()
    router.leave()
    probe = LockFile(model_dir(state_root(), CHAT) / "clients.lock")
    try:
        assert probe.acquire(shared=False, blocking=False) is True
    finally:
        probe.close()


def test_one_slot_model_serialises_across_processes(rig: RouterRig) -> None:
    """Spec scenario "Second decision request waits"."""
    first, second = rig.worker(), rig.worker()
    assert first.call("request", model=CLEF)["ok"]  # load before timing
    a = first.send("request", model=CLEF, hold=HOLD)
    time.sleep(0.3)
    b = second.send("request", model=CLEF, hold=0)
    one, two = first.read(a), second.read(b)
    assert one["ok"] and two["ok"], (one, two)
    assert two["entered"] >= one["left"]


def test_second_model_does_not_wait(rig: RouterRig) -> None:
    """Spec scenario "Decision requests do not block embeddings"."""
    first, second = rig.worker(), rig.worker()
    assert first.call("request", model=CLEF)["ok"]
    assert second.call("request", model=EMBED, path="/v1/embeddings")["ok"]
    a = first.send("request", model=CLEF, hold=HOLD)
    time.sleep(0.3)
    b = second.send("request", model=EMBED, path="/v1/embeddings", hold=0)
    two = second.read(b)
    one = first.read(a)
    assert one["ok"] and two["ok"], (one, two)
    assert two["entered"] < one["left"]


def test_two_slot_model_does_not_serialise(rig: RouterRig) -> None:
    first, second = rig.worker(), rig.worker()
    assert first.call("request", model=CHAT)["ok"]
    a = first.send("request", model=CHAT, hold=HOLD)
    time.sleep(0.3)
    two = second.read(second.send("request", model=CHAT, hold=0))
    one = first.read(a)
    assert two["entered"] < one["left"]


def _stress(rig: RouterRig, seconds: float) -> None:
    """Workers mix requests, preset edits and leaves; every command must answer."""
    workers = [rig.worker() for _ in range(4)]
    chooser = random.Random(7)  # noqa: S311 - a test schedule, not a secret
    models = [(EMBED, "/v1/embeddings"), (CHAT, "/v1/chat/completions"), (CLEF, "/v1/systemone")]
    deadline = time.monotonic() + seconds
    pending: list[tuple[object, str]] = []
    while time.monotonic() < deadline:
        for worker in workers:
            roll = chooser.random()
            if roll < 0.7:
                model, path = chooser.choice(models)
                tag = worker.send("request", model=model, path=path, hold=chooser.random() * 0.05)
            elif roll < 0.85:
                ctx = chooser.choice([4096, 8192])
                tag = worker.send("update", entries=rig.entries(chat_ctx=ctx))
            else:
                tag = worker.send("leave")
            pending.append((worker, tag))
        while len(pending) > 32:
            worker, tag = pending.pop(0)
            worker.read(tag, timeout=60)  # type: ignore[attr-defined]
        time.sleep(0.02)
    served = 0
    for worker, tag in pending:
        answer = worker.read(tag, timeout=60)  # type: ignore[attr-defined]
        assert "reason" not in answer or answer["reason"] in {"version-busy"}, answer
        served += "status" in answer
    assert served > 0  # requests ran, not only refusals


def test_lock_order_stress_short(rig: RouterRig) -> None:
    """A short run of the lock-order stress test (fast suite)."""
    _stress(rig, 3.0)


@pytest.mark.slow
def test_lock_order_stress_twenty_seconds(rig: RouterRig) -> None:
    """Task 4.1: the 20-second stress test ends without deadlock."""
    _stress(rig, 20.0)
