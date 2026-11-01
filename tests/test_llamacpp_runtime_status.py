"""Runtime status, external mode and the platform guard (design D2, D11).

``RuntimeManager.status`` feeds ``GET /v1/runtimes``: one item per runtime in
force with a fixed field set. It starts nothing and writes nothing.
"""

from __future__ import annotations

import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from tests.fixtures.llamacpp.harness import RuntimeEnv, runtime_env_fixture, wait_until

from omrs.integrations.llamacpp_runtime import locks
from omrs.integrations.llamacpp_runtime.manager import RuntimeUnavailable
from omrs.integrations.llamacpp_runtime.rules import REASONS
from omrs.integrations.llamacpp_runtime.spec import RuntimeSpec
from omrs.integrations.llamacpp_runtime.state import (
    ServerRecord,
    runtime_dir,
    state_root,
    write_server_record,
)

FIELDS = {
    "id",
    "role",
    "mode",
    "state",
    "reason",
    "reason_text",
    "memory_bytes",
    "clients",
    "used_by",
    "address",
    "files_checked",
}


@pytest.fixture()
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimeEnv]:
    yield from runtime_env_fixture(tmp_path, monkeypatch)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    if not root.exists():
        return {}
    return {
        str(path): (path.stat().st_mtime_ns, path.stat().st_size)
        for path in root.rglob("*")
        if path.is_file()
    }


def _external(port: int, *, role: str = "ocr", build: int | None = 11941) -> RuntimeSpec:
    runtime_id = "ocr-fake-engine" if role == "ocr" else role
    return RuntimeSpec(
        id=runtime_id,
        role=role,  # type: ignore[arg-type]
        mode="external",
        binary="",
        url_base=f"http://127.0.0.1:{port}",
        build=build,
    )


def _start_fake(runtime_env: RuntimeEnv, port: int, **env: str) -> subprocess.Popen:  # type: ignore[type-arg]
    fake = runtime_env.fake()
    fake.set_env(**env)
    proc = subprocess.Popen(  # noqa: S603 - test fixture, fixed argv
        [str(fake.binary), "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    def healthy() -> bool:
        try:
            return httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200
        except httpx.HTTPError:
            return False

    assert wait_until(healthy)
    return proc


def test_a_stopped_runtime_reads_without_starting_or_writing(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    before = _snapshot(state_root())
    items = runtime_env.manager().status([fake.chat(_free_port()), fake.ocr()])
    assert _snapshot(state_root()) == before
    assert fake.starts() == []
    assert [set(item) for item in items] == [FIELDS, FIELDS]
    chat = items[0]
    assert chat["state"] == "stopped"
    assert (chat["reason"], chat["memory_bytes"], chat["address"]) == (None, None, None)
    assert chat["clients"] == "none"


def test_a_running_runtime_reports_memory_address_and_clients(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fake.ocr()
    manager = runtime_env.manager()
    url = manager.lease(spec).join()
    before = _snapshot(state_root())
    item = runtime_env.manager().status([spec], {"ocr-fake-engine": ["OCR_ENGINE"]})[0]
    assert _snapshot(state_root()) == before
    assert item["state"] == "running"
    assert item["address"] == url.removeprefix("http://")
    assert isinstance(item["memory_bytes"], int) and item["memory_bytes"] > 0
    assert item["clients"] == "some"
    assert item["used_by"] == ["OCR_ENGINE"]
    assert (item["mode"], item["role"], item["files_checked"]) == ("managed", "ocr", True)


def test_an_orphan_reports_no_client(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fake.chat(_free_port())
    starter = runtime_env.client()
    assert starter.join(spec)["ok"]
    starter.send({"cmd": "abandon"})
    starter.wait()
    item = runtime_env.manager().status([spec])[0]
    assert (item["state"], item["clients"]) == ("running", "none")
    assert item["files_checked"] is False


def test_a_crashed_server_reads_failed_exited(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fake.chat(_free_port())
    gone = subprocess.Popen(["true"])  # noqa: S603, S607 - a pid that is gone
    gone.wait()
    folder = runtime_dir(state_root(), spec.id)
    folder.mkdir(parents=True, exist_ok=True)
    record = ServerRecord(
        pid=gone.pid,
        port=spec.port,
        binary=spec.binary,
        digest=spec.digest,
        build=None,
        state="running",
        stopped_by=None,
        generation=1,
        reason=None,
    )
    write_server_record(folder, record)
    item = runtime_env.manager().status([spec])[0]
    assert (item["state"], item["reason"]) == ("failed", "exited")
    assert item["reason_text"]
    assert (item["address"], item["memory_bytes"]) == (None, None)


def test_every_reason_is_from_the_fixed_set(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_BUILD="11960")
    spec = fake.ocr()
    with pytest.raises(RuntimeUnavailable) as caught:
        runtime_env.manager().lease(spec).join()
    assert caught.value.reason in REASONS
    item = runtime_env.manager().status([spec])[0]
    assert item["reason"] in REASONS
    assert item["reason_text"]


def test_external_ocr_with_the_declared_build_starts_nothing(runtime_env: RuntimeEnv) -> None:
    port = _free_port()
    proc = _start_fake(runtime_env, port)
    try:
        spec = _external(port)
        lease = runtime_env.manager().lease(spec)
        assert lease.join() == f"http://127.0.0.1:{port}"
        item = runtime_env.manager().status([spec])[0]
        assert (item["mode"], item["files_checked"]) == ("external", False)
        assert item["state"] == "running"
        assert item["address"] == f"127.0.0.1:{port}"
        assert list((state_root() / "runtimes").glob("*/server.json")) == []
    finally:
        proc.kill()
        proc.wait()


def test_external_ocr_with_another_build_is_refused(runtime_env: RuntimeEnv) -> None:
    port = _free_port()
    proc = _start_fake(runtime_env, port, FAKE_LLAMA_BUILD="11960")
    try:
        with pytest.raises(RuntimeUnavailable) as caught:
            runtime_env.manager().lease(_external(port)).join()
        assert caught.value.reason == "wrong-build"
    finally:
        proc.kill()
        proc.wait()


def test_external_chat_is_never_started_or_stopped(runtime_env: RuntimeEnv) -> None:
    port = _free_port()
    spec = _external(port, role="chat", build=None)
    manager = runtime_env.manager()
    assert manager.lease(spec).join() == f"http://127.0.0.1:{port}"
    assert manager.status([spec])[0]["state"] == "stopped"
    assert manager.stop("chat") is False


def test_managed_mode_without_file_locks_is_not_supported(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(locks, "LOCKS_SUPPORTED", False)
    fake = runtime_env.fake()
    spec = fake.chat(_free_port())
    with pytest.raises(RuntimeUnavailable) as caught:
        runtime_env.manager().lease(spec).join()
    assert caught.value.reason == "not-supported"
    assert fake.starts() == []
    item = runtime_env.manager().status([spec])[0]
    assert (item["state"], item["reason"]) == ("failed", "not-supported")
    external = _external(_free_port(), role="chat", build=None)
    assert runtime_env.manager().lease(external).join().startswith("http://127.0.0.1:")
