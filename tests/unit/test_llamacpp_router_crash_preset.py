"""A crash restart keeps the section of a model another process uses (design D7, D8).

Two OMRS processes share the state folder and hold different presets for one
model. When the router crashes, the process that starts it again writes
``models.ini`` before the start. It must obey the same rule as a normal join:
it may change a model's section only when no other process uses that model.
Otherwise the section in force stays and this process gets ``version-busy`` for
that model only. A fake router ``llama-server`` stands in; no network is used.
"""

from __future__ import annotations

import os
import signal
import sys
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from tests.fixtures.llamacpp.harness import pid_alive, wait_until
from tests.unit.test_llamacpp_router_worker import (
    CHAT,
    EMBED,
    RouterRig,
    as_entries,
    rig_fixture,
)

from omrs.integrations.llamacpp_runtime.model_reasons import ModelUnavailable
from omrs.integrations.llamacpp_runtime.preset_writer import (
    read_preset,
    section_digest,
    split_sections,
)
from omrs.integrations.llamacpp_runtime.router_lease import RouterLease, open_router
from omrs.integrations.llamacpp_runtime.router_spec import router_dir
from omrs.integrations.llamacpp_runtime.state import read_server_record, state_root

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from rig_fixture(tmp_path, monkeypatch)


def _sections() -> dict[str, str]:
    return split_sections(read_preset(router_dir(state_root())))


def _crash_and_restart(web: RouterLease) -> None:
    """Kill the router and its model children, then let *web* start it again."""
    record = read_server_record(router_dir(state_root()))
    assert record is not None and record.pid > 0
    os.killpg(record.pid, signal.SIGKILL)
    assert wait_until(lambda: not pid_alive(record.pid), 10)
    assert web.base.restart_if_crashed() is True


def test_a_crash_restart_keeps_the_section_another_process_uses(rig: RouterRig) -> None:
    cli = rig.worker(entries=rig.entries(chat_ctx=8192))
    assert cli.call("request", model=CHAT)["ok"]  # the CLI holds the Chat model
    web = open_router(rig.manager(), rig.spec(), as_entries(rig.entries(chat_ctx=4096)))
    with web.model_session(EMBED):
        pass

    _crash_and_restart(web)

    chat = _sections()[CHAT]
    assert "ctx-size = 8192" in chat  # the CLI's section stays in force
    record = read_server_record(router_dir(state_root()))
    assert record is not None and record.models[CHAT] == section_digest(chat)
    status = {item["model"]: item for item in web.model_status()}
    assert status[CHAT]["reload_pending"] is True  # shown before any Chat request
    assert status[EMBED]["reload_pending"] is False
    with pytest.raises(ModelUnavailable) as caught:
        with web.model_session(CHAT):
            pass
    assert caught.value.reason == "version-busy"  # never served with the wrong preset
    with web.model_session(EMBED) as url:
        assert httpx.post(f"{url}/v1/embeddings", json={"model": EMBED}).status_code == 200
    assert cli.call("request", model=CHAT)["ok"]


def test_a_crash_restart_writes_its_own_section_when_no_one_else_uses_it(
    rig: RouterRig,
) -> None:
    cli = rig.worker(entries=rig.entries(chat_ctx=8192))
    assert cli.call("request", model=EMBED)["ok"]  # the CLI never used the Chat model
    web = open_router(rig.manager(), rig.spec(), as_entries(rig.entries(chat_ctx=4096)))
    with web.model_session(EMBED):
        pass

    _crash_and_restart(web)

    assert "ctx-size = 4096" in _sections()[CHAT]
    with web.model_session(CHAT):
        pass
