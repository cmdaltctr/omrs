"""Idle stop (task 4.4; design D7)."""

from __future__ import annotations

import ast
import socket
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from tests.fixtures.llamacpp.harness import RuntimeEnv, pid_alive, runtime_env_fixture, wait_until
from tests.unit.test_llamacpp_router_worker import fixed_spec

from omrs.integrations.llamacpp_runtime import manager as manager_module
from omrs.integrations.llamacpp_runtime.state import read_server_record, runtime_dir, state_root

MANAGER_SOURCE = Path(manager_module.__file__)


@pytest.fixture()
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimeEnv]:
    yield from runtime_env_fixture(tmp_path, monkeypatch)


@pytest.fixture()
def short_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manager_module, "IDLE_STOP_SECONDS", 2.0)
    monkeypatch.setattr(manager_module, "IDLE_CHECK_SECONDS", 0.1)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _chat(base_url: str) -> httpx.Response:
    return httpx.post(f"{base_url}/v1/chat/completions", json={"messages": []}, timeout=10)


def test_the_shipped_idle_stop_is_ten_minutes_and_not_a_setting() -> None:
    assert manager_module.IDLE_STOP_SECONDS == 600
    tree = ast.parse(MANAGER_SOURCE.read_text(encoding="utf-8"))
    # One literal assignment at module level, and nothing else assigns it.
    assigned = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "IDLE_STOP_SECONDS"
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
    ]
    assert len(assigned) == 1
    assert isinstance(assigned[0].value, ast.Constant)
    assert assigned[0] in tree.body
    from omrs.config import Settings

    assert not [name for name in Settings.model_fields if "idle_stop" in name]


@pytest.mark.usefixtures("short_idle")
def test_the_only_client_leaves_after_the_idle_time(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    lease = runtime_env.manager().lease(fixed_spec(fake, _free_port()))
    assert lease.request(_chat).status_code == 200
    server_pid = int(fake.starts()[0]["pid"])
    assert pid_alive(server_pid)
    assert wait_until(lambda: not pid_alive(server_pid), timeout=8)
    folder = runtime_dir(state_root(), "router")

    def stopped_by() -> str | None:
        record = read_server_record(folder)
        return record.stopped_by if record is not None else None

    assert wait_until(lambda: stopped_by() == "idle")
    assert lease.joined is False


@pytest.mark.usefixtures("short_idle")
def test_a_second_active_client_keeps_the_server(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fixed_spec(fake, _free_port())
    other = runtime_env.client()  # its idle stop stays at 600 s
    assert other.join(spec)["ok"]
    lease = runtime_env.manager().lease(spec)
    assert lease.request(_chat).status_code == 200
    assert wait_until(lambda: lease.joined is False, timeout=8), "the idle lease did not leave"
    assert pid_alive(int(fake.starts()[0]["pid"]))
    assert other.chat()["ok"] is True
    assert len(fake.starts()) == 1


@pytest.mark.usefixtures("short_idle")
def test_the_next_request_after_an_idle_stop_starts_again(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    lease = runtime_env.manager().lease(fixed_spec(fake, _free_port()))
    assert lease.request(_chat).status_code == 200
    first_pid = int(fake.starts()[0]["pid"])
    assert wait_until(lambda: not pid_alive(first_pid), timeout=8)
    assert lease.request(_chat).status_code == 200
    assert len(fake.starts()) == 2


@pytest.mark.usefixtures("short_idle")
def test_a_request_in_progress_holds_off_the_idle_stop(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_REQUEST_DELAY="3")
    lease = runtime_env.manager().lease(fixed_spec(fake, _free_port()))
    lease.join()
    assert lease.request(_chat).status_code == 200  # 3 s, longer than the idle time
    assert len(fake.starts()) == 1


@pytest.mark.usefixtures("short_idle")
def test_an_idle_hook_runs_before_the_leave(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    lease = runtime_env.manager().lease(fixed_spec(fake, _free_port()))
    seen: list[bool] = []
    lease.on_idle_leave(lambda: seen.append(lease.joined))
    assert lease.request(_chat).status_code == 200
    assert wait_until(lambda: seen != [], timeout=8)
    assert seen == [True], "the hook must run while the lease still holds the runtime"
