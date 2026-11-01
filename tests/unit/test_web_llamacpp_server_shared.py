"""The managed Chat server is shared by ``omrs web`` and CLI processes (task 5.1, design D4, D9).

A CLI process stands in as ``tests/fixtures/llamacpp/client.py``. The web app
adopts the server the CLI started, leaves it when its lifespan ends, and its
start-up sweep stops an owned server that no process uses.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.fixtures.llamacpp.harness import (  # noqa: E402
    FakeRuntime,
    RuntimeEnv,
    pid_alive,
    runtime_env_fixture,
    wait_until,
)
from tests.unit import test_web_llamacpp_server as server  # noqa: E402
from tests.unit.llamacpp_fake import free_port  # noqa: E402

from omrs.core.answer.settings import AnswerSettings  # noqa: E402
from omrs.integrations.llamacpp_runtime import (  # noqa: E402
    read_server_record,
    runtime_dir,
    state_root,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

harness = server.harness
rig = server.rig


@pytest.fixture
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimeEnv]:
    yield from runtime_env_fixture(tmp_path, monkeypatch)


def _overrides(fake: FakeRuntime, port: int) -> dict[str, Any]:
    """Settings that make the web app's Chat server the fake on *port*."""
    return {
        "llamacpp_chat_url": f"http://127.0.0.1:{port}/v1",
        "answer": AnswerSettings(enabled=True, provider="llamacpp", model=str(fake.model)),
    }


def test_a_cli_client_and_the_web_app_share_one_chat_server(
    rig: Any, runtime_env: RuntimeEnv
) -> None:
    fake = runtime_env.fake("shared")
    port = free_port()
    cli = runtime_env.client()
    assert cli.join(fake.chat(port))["ok"] is True
    pid = int(fake.starts()[0]["pid"])

    with rig(**_overrides(fake, port)) as r:  # the start-up sweep leaves a held server
        assert pid_alive(pid)
        assert r.put({"binary": str(fake.binary), "context_window": 2048}).status_code == 200
        body = r.post("start").json()
        assert (body["state"], body["pid_running"]) == ("running", True)
        assert body["running_with"] == {"context_window": 2048, "model_kind": "file"}
        assert len(fake.starts()) == 1  # adopted, not started again
        assert cli.chat()["ok"] is True

    # The web app left its lease; the CLI still holds the server.
    assert pid_alive(pid)
    assert cli.chat()["ok"] is True
    assert len(fake.starts()) == 1


def test_the_web_start_up_sweep_stops_an_orphan_with_no_client(
    rig: Any, runtime_env: RuntimeEnv
) -> None:
    fake = runtime_env.fake("orphan")
    port = free_port()
    cli = runtime_env.client()
    assert cli.join(fake.chat(port))["ok"] is True
    pid = int(fake.starts()[0]["pid"])
    cli.proc.kill()  # SIGKILL: no leave runs, so the server is an orphan
    cli.wait()
    assert pid_alive(pid)

    with rig(**_overrides(fake, port)) as r:
        assert wait_until(lambda: not pid_alive(pid))
        assert r.get()["state"] == "stopped"

    record = read_server_record(runtime_dir(state_root(), "chat"))
    assert record is not None and record.stopped_by == "last-client"


def test_leaving_the_app_with_no_other_client_stops_the_server_as_last_client(
    rig: Any, runtime_env: RuntimeEnv
) -> None:
    fake = runtime_env.fake("alone")
    port = free_port()
    with rig(**_overrides(fake, port)) as r:
        assert r.put({"binary": str(fake.binary), "context_window": 2048}).status_code == 200
        assert r.post("start").json()["state"] == "running"
        pid = int(fake.starts()[0]["pid"])

    assert wait_until(lambda: not pid_alive(pid))
    record = read_server_record(runtime_dir(state_root(), "chat"))
    assert record is not None and record.stopped_by == "last-client"
