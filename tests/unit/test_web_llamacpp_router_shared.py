"""The router is shared by ``omrs web`` and other OMRS processes (task 7.1, design D4, D9).

A worker process (``test_llamacpp_router_worker.py``) stands in for the CLI. The
web app adopts the router the worker started, and its start-up sweep stops an
orphan that no process uses.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.fixtures.llamacpp.harness import pid_alive, wait_until  # noqa: E402
from tests.unit import test_web_llamacpp_router_support as support  # noqa: E402
from tests.unit.test_llamacpp_router_worker import (  # noqa: E402
    CHAT,
    EMBED,
    RouterRig,
    rig_fixture,
)

from omrs.integrations.llamacpp_runtime.router_spec import router_dir  # noqa: E402
from omrs.integrations.llamacpp_runtime.state import read_server_record, state_root  # noqa: E402

harness = support.harness
rig = support.rig

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")


@pytest.fixture
def worker_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from rig_fixture(tmp_path / "worker", monkeypatch)


def _overrides(shared: RouterRig) -> dict[str, Any]:
    """Settings that make the web app's router the one the worker runs."""
    return {
        "llamacpp_server_binary": str(shared.binary),
        "llamacpp_router_url": f"http://127.0.0.1:{shared.port}/v1",
        "llamacpp_router_memory_margin_mib": 0,  # the worker's spec uses 0
    }


def test_a_worker_and_the_web_app_share_one_router(rig: Any, worker_rig: RouterRig) -> None:
    worker = worker_rig.worker()
    assert worker.call("request", model=CHAT)["ok"] is True
    record = read_server_record(router_dir(state_root()))
    assert record is not None
    pid = record.pid

    with rig(**_overrides(worker_rig)) as r:  # the start-up sweep leaves a held router
        assert pid_alive(pid)
        assert r.get()["state"] == "running"
        body = r.post("start").json()
        assert body["state"] == "running"
        assert body["pending_restart"] is False
        assert worker_rig.starts() == 1  # adopted, not started again
        assert worker.call("request", model=EMBED, path="/v1/embeddings")["ok"] is True

    # The web app left its lease; the worker still holds the router.
    assert pid_alive(pid)
    assert worker.call("request", model=CHAT)["ok"] is True
    assert worker_rig.starts() == 1


def test_the_web_start_up_sweep_stops_an_orphan_with_no_client(
    rig: Any, worker_rig: RouterRig
) -> None:
    worker = worker_rig.worker()
    assert worker.call("request", model=CHAT)["ok"] is True
    record = read_server_record(router_dir(state_root()))
    assert record is not None
    pid = record.pid
    worker.send("abandon")  # no leave runs, so the router is an orphan
    worker.proc.wait(timeout=15)
    assert pid_alive(pid)

    with rig(**_overrides(worker_rig)) as r:
        assert wait_until(lambda: not pid_alive(pid), 10)
        assert r.get()["state"] == "stopped"

    after = read_server_record(router_dir(state_root()))
    assert after is not None and after.stopped_by == "last-client"
