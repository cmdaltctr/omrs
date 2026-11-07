"""One lock order inside one process, and no needless list update (review fix 1).

Two threads of one process must never wait on each other's locks. ``flock``
blocks between two descriptors of one process, so ``start.lock`` serialises
threads as well as processes. The order is: the runtime lease lock, then
``start.lock``, then the router lease lock. A crash restart (start.lock, then
the router lease lock) and the first request to another model must therefore
both end. A fake router ``llama-server`` stands in; no network is used.

Each test that could wait on a lock runs with a hard time limit, so a deadlock
fails at once instead of hanging the suite.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, TypeVar

import pytest
from tests.fixtures.llamacpp.harness import pid_alive, wait_until
from tests.unit.test_llamacpp_router_worker import (
    CHAT,
    EMBED,
    RouterRig,
    as_entries,
    rig_fixture,
)

from omrs.config.llamacpp_models import LlamaCppModelEntry
from omrs.integrations.llamacpp_runtime.locks import LockFile
from omrs.integrations.llamacpp_runtime.router_lease import RouterLease, open_router
from omrs.integrations.llamacpp_runtime.router_spec import router_dir
from omrs.integrations.llamacpp_runtime.state import read_server_record, state_root

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

T = TypeVar("T")

#: Longest a test thread may run before the test calls it a deadlock.
LIMIT = 30.0


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from rig_fixture(tmp_path, monkeypatch)


def _abandon(rig: RouterRig) -> None:
    """Forget the rig's managers: closing one would wait on a stuck thread's lock."""
    rig.managers.clear()


def within(rig: RouterRig, work: Callable[[], T], seconds: float = LIMIT) -> T:
    """Run *work* in a daemon thread; fail when it does not end in *seconds*.

    On a time-out the rig's managers are forgotten, so the fixture cleanup does
    not wait on a lock that a stuck thread holds.
    """
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["value"] = work()
        except BaseException as error:  # noqa: BLE001 - raised again in the test thread
            box["error"] = error

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        _abandon(rig)
        pytest.fail(f"the work did not end in {seconds} s: a lock wait never ended")
    if "error" in box:
        raise box["error"]
    return box["value"]


def kill_router() -> int:
    """Kill the running router and its model children; return its pid."""
    record = read_server_record(router_dir(state_root()))
    assert record is not None and record.pid > 0
    os.killpg(record.pid, signal.SIGKILL)
    assert wait_until(lambda: not pid_alive(record.pid), 10)
    return record.pid


def test_crash_restart_and_first_use_of_another_model_both_end(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T1 restarts a crashed router while T2 joins a model for the first time.

    T2 is stopped just before it waits on ``start.lock``, until T1 holds
    ``start.lock`` in its pre-start step. If T2 holds the router lease lock at
    that point, T1 waits for it while T2 waits for ``start.lock``: a deadlock.
    """
    web = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    with web.model_session(EMBED):  # start the router; Chat is not used yet
        pass
    kill_router()

    t1_holds_start = threading.Event()
    t2_at_start = threading.Event()
    stopped: list[threading.Thread] = []
    acquire = LockFile.acquire

    def stopped_acquire(lock: LockFile, **kwargs: Any) -> bool:
        me = threading.current_thread()
        if lock.path.name == "start.lock" and me.name == "T2" and not stopped:
            stopped.append(me)
            t2_at_start.set()
            if not t1_holds_start.wait(LIMIT):
                raise AssertionError("T1 never reached its pre-start step")
        return acquire(lock, **kwargs)

    before_start = web.base.before_start
    assert before_start is not None

    def marked_before_start() -> dict[str, Any]:
        t1_holds_start.set()
        return before_start()

    monkeypatch.setattr(LockFile, "acquire", stopped_acquire)
    web.base.before_start = marked_before_start
    errors: list[BaseException] = []
    restarted: list[bool] = []

    def first_chat() -> None:
        try:
            with web.model_session(CHAT):
                pass
        except BaseException as error:  # noqa: BLE001 - checked below
            errors.append(error)

    def crash_restart() -> None:
        try:
            restarted.append(web.base.restart_if_crashed())
        except BaseException as error:  # noqa: BLE001 - checked below
            errors.append(error)

    t2 = threading.Thread(target=first_chat, name="T2", daemon=True)
    t2.start()
    assert t2_at_start.wait(LIMIT), "T2 never reached start.lock"
    t1 = threading.Thread(target=crash_restart, name="T1", daemon=True)
    t1.start()
    t1.join(LIMIT)
    t2.join(LIMIT)
    if t1.is_alive() or t2.is_alive():
        _abandon(rig)
        pytest.fail("deadlock: the crash restart and the first Chat request wait on each other")
    assert errors == []
    assert restarted == [True]
    assert rig.starts() == 2


def _typed(items: list[dict[str, Any]]) -> list[LlamaCppModelEntry]:
    return [LlamaCppModelEntry(**item) for item in items]


def test_equal_entries_of_another_type_do_not_update(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate passes plain objects, the router panel passes typed entries."""
    manager = rig.manager()
    open_router(manager, rig.spec(), as_entries(rig.entries()))
    calls: list[list[Any]] = []
    monkeypatch.setattr(
        RouterLease, "update_entries", lambda self, entries, *_: calls.append(list(entries))
    )

    open_router(manager, rig.spec(), _typed(rig.entries()))
    open_router(manager, rig.spec(), as_entries(rig.entries()))
    assert calls == []

    open_router(manager, rig.spec(), _typed(rig.entries(chat_ctx=4096)))
    assert len(calls) == 1  # a real change still updates
