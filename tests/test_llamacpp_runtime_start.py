"""Start checks and bind retries (tasks 4.1 and 4.2; design D5).

These tests run the manager in the test process. Two managers in one process
hold separate lock descriptors, so they behave as two OMRS processes would.
"""

from __future__ import annotations

import json
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.fixtures.llamacpp.harness import RuntimeEnv, pid_alive, runtime_env_fixture
from tests.fixtures.llamacpp.install import touch_count_file
from tests.unit.test_llamacpp_router_worker import fixed_spec

from omrs.integrations.llamacpp_runtime import process
from omrs.integrations.llamacpp_runtime.manager import RuntimeUnavailable
from omrs.integrations.llamacpp_runtime.state import read_server_record, runtime_dir, state_root


@pytest.fixture()
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimeEnv]:
    yield from runtime_env_fixture(tmp_path, monkeypatch)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _refused(runtime_env: RuntimeEnv, spec) -> RuntimeUnavailable:  # type: ignore[no-untyped-def]
    lease = runtime_env.manager().lease(spec)
    with pytest.raises(RuntimeUnavailable) as caught:
        lease.join()
    return caught.value


def _status(runtime_env: RuntimeEnv, spec) -> dict:  # type: ignore[no-untyped-def,type-arg]
    return runtime_env.manager().status([spec])[0]


# ── 4.1 Start checks ────────────────────────────────────────────────────


def test_wrong_build_is_refused_and_nothing_starts(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_BUILD="11960")
    spec = fake.ocr(build=11941)
    error = _refused(runtime_env, spec)
    assert error.reason == "wrong-build"
    assert fake.starts() == []
    status = _status(runtime_env, spec)
    assert (status["state"], status["reason"]) == ("failed", "wrong-build")


def test_a_matching_build_starts(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fake.ocr(build=11941)
    url = runtime_env.manager().lease(spec).join()
    assert url.startswith("http://127.0.0.1:")
    assert len(fake.starts()) == 1


def test_a_changed_model_file_is_refused_and_named(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fake.ocr()
    fake.model.write_bytes(fake.model.read_bytes() + b"!")  # one byte changed
    error = _refused(runtime_env, spec)
    assert error.reason == "file-changed"
    assert "q.gguf" in error.reason_text
    assert fake.starts() == []
    status = _status(runtime_env, spec)
    assert status["reason"] == "file-changed"
    assert "q.gguf" in (status["reason_text"] or "")


def test_a_missing_model_file_is_refused(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fake.ocr()
    fake.model.unlink()
    assert _refused(runtime_env, spec).reason == "file-changed"


def test_a_program_that_breaks_the_rule_is_refused(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fixed_spec(fake, _free_port())
    fake.binary.chmod(0o644)  # no longer executable
    assert _refused(runtime_env, spec).reason == "binary-invalid"
    assert fake.starts() == []


def test_a_port_held_by_another_process_gives_port_in_use(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        spec = fixed_spec(fake, int(holder.getsockname()[1]))
        assert _refused(runtime_env, spec).reason == "port-in-use"
    assert fake.starts() == []


def test_health_timeout_stops_the_process(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(process, "HEALTH_TIMEOUT_SECONDS", 1.0)
    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_NEVER_HEALTHY="1")
    spec = fixed_spec(fake, _free_port())
    assert _refused(runtime_env, spec).reason == "timeout"
    assert len(fake.starts()) == 1
    assert not pid_alive(int(fake.starts()[0]["pid"]))
    record = read_server_record(runtime_dir(state_root(), "router"))
    assert record is not None and record.reason == "timeout"


def test_the_child_has_no_pipe_and_writes_to_server_log(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    fds_file = fake.logs / "fds.json"
    fake.set_env(FAKE_LLAMA_FDS=str(fds_file), FAKE_LLAMA_SPAM_BYTES="300")
    spec = fixed_spec(fake, _free_port())
    runtime_env.manager().lease(spec).join()
    fds = json.loads(fds_file.read_text(encoding="utf-8"))
    assert "fifo" not in fds.values()
    assert fds == {"0": "chr", "1": "reg", "2": "reg"}
    log = runtime_dir(state_root(), "router") / "server.log"
    assert "x" * 99 in log.read_text(encoding="utf-8")


# ── 4.2 Bind retries ────────────────────────────────────────────────────


def test_bind_fails_four_times_then_bind_failed(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    fails = touch_count_file(fake.logs, "bind-fails.txt", 10)
    fake.set_env(FAKE_LLAMA_BIND_FAILS=str(fails))
    error = _refused(runtime_env, fake.ocr())
    assert error.reason == "bind-failed"
    assert fails.read_text().strip() == "6", "the manager must try 4 ports in total"
    assert fake.starts() == []


def test_bind_fails_twice_then_the_third_try_runs(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    fails = touch_count_file(fake.logs, "bind-fails.txt", 2)
    fake.set_env(FAKE_LLAMA_BIND_FAILS=str(fails))
    runtime_env.manager().lease(fake.ocr()).join()
    assert fails.read_text().strip() == "0"
    assert len(fake.starts()) == 1


def test_an_early_exit_without_the_bind_line_is_not_retried(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    counter = touch_count_file(fake.logs, "early.txt", 0)
    fake.set_env(FAKE_LLAMA_EARLY_EXIT=str(counter))
    assert _refused(runtime_env, fake.ocr()).reason == "exited"
    assert counter.read_text().strip() == "1"


def test_a_fixed_port_gets_no_bind_retry(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    fails = touch_count_file(fake.logs, "bind-fails.txt", 10)
    fake.set_env(FAKE_LLAMA_BIND_FAILS=str(fails))
    assert _refused(runtime_env, fixed_spec(fake, _free_port())).reason == "port-in-use"
    assert fails.read_text().strip() == "9"


def test_a_starting_record_whose_starter_died_is_adopted_after_health(
    runtime_env: RuntimeEnv,
) -> None:
    import subprocess

    from omrs.integrations.llamacpp_runtime.state import ServerRecord, write_server_record

    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_HEALTH_DELAY="1")
    spec = fixed_spec(fake, _free_port())
    port = spec.port or 0
    orphan = subprocess.Popen(  # noqa: S603 - the server a dead starter left
        list(spec.launch_argv(port)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    folder = runtime_dir(state_root(), "router")
    write_server_record(
        folder,
        ServerRecord(
            pid=orphan.pid, port=port, binary=spec.binary, digest=spec.digest, state="starting"
        ),
    )
    assert runtime_env.manager().lease(spec).join() == f"http://127.0.0.1:{port}"
    record = read_server_record(folder)
    assert record is not None and (record.pid, record.state) == (orphan.pid, "running")
    assert len(fake.starts()) == 1, "a second server started"
