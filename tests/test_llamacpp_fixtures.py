"""Self-tests of the fake ``llama-server`` and client fixtures.

The runtime manager tests (``tests/test_llamacpp_runtime_*.py``) drive real
subprocesses through these fixtures, so the fixtures themselves are tested
here first: a start, ``/health``, ``/props``, ``--version`` and each
behaviour variable (task 1.1), and the client process line protocol
(task 1.2 plumbing; its join path needs the manager and is covered by the
lease tests).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from tests.fixtures.llamacpp.fake_llama_server import BIND_ERROR_LINE, PROPS_BUILD_FIELD
from tests.fixtures.llamacpp.install import install_fake_server, touch_count_file

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT = REPO_ROOT / "tests" / "fixtures" / "llamacpp" / "client.py"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class FakeServer:
    """The fake server as a directly started process (no manager)."""

    def __init__(self, tmp_path: Path, **env: str) -> None:
        self.binary = install_fake_server(tmp_path / "bin")
        self.port = _free_port()
        self.starts = touch_count_file(tmp_path / "logs", "starts.txt", 0)
        self.requests = tmp_path / "logs" / "requests.jsonl"
        self.env = {
            "FAKE_LLAMA_STARTS": str(self.starts),
            "FAKE_LLAMA_REQUESTS": str(self.requests),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            **env,
        }
        self.proc: subprocess.Popen | None = None

    def start(self, *, wait_healthy: bool = True) -> None:
        assert self.proc is None
        self.proc = subprocess.Popen(  # noqa: S603 - test fixture, fixed argv
            [str(self.binary), "--host", "127.0.0.1", "--port", str(self.port)],
            env=self.env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        if not wait_healthy:
            time.sleep(0.3)
            return
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
        raise AssertionError("the fake server never became healthy")

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            os.killpg(self.proc.pid, 15)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover
                os.killpg(self.proc.pid, 9)
        self.proc = None

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"


@pytest.fixture()
def server(tmp_path: Path) -> FakeServer:
    fake = FakeServer(tmp_path)
    fake.start()
    try:
        yield fake
    finally:
        fake.stop()


def test_health_and_props_report_the_build(server: FakeServer) -> None:
    answer = httpx.get(server.url("/health"), timeout=2)
    assert answer.status_code == 200
    props = httpx.get(server.url("/props"), timeout=2)
    assert props.status_code == 200
    # The field name sits in one constant; task 6.4 confirms it on a real binary.
    assert props.json()[PROPS_BUILD_FIELD] == "b11941-fake"


def test_llama_flags_are_accepted_and_each_start_is_logged(tmp_path: Path) -> None:
    fake = FakeServer(tmp_path)
    flags = [
        "-m",
        "/m/e.gguf",
        "--mmproj",
        "/m/p.gguf",
        "--embedding",
        "-np",
        "1",
        "-c",
        "2048",
        "--temp",
        "0",
        "--image-min-tokens",
        "4",
    ]
    fake.proc = subprocess.Popen(  # noqa: S603 - test fixture, fixed argv
        [str(fake.binary), *flags, "--host", "127.0.0.1", "--port", str(fake.port)],
        env=fake.env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if httpx.get(fake.url("/health"), timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
        else:  # pragma: no cover
            pytest.fail("the fake server never became healthy")
    finally:
        fake.stop()
    lines = fake.starts.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    pid, argv = lines[0].split(" ", 1)
    assert pid.isdigit()
    assert json.loads(argv)[: len(flags)] == flags


def test_version_reports_the_build_and_it_changes(tmp_path: Path) -> None:
    binary = install_fake_server(tmp_path / "bin")
    plain = subprocess.run(  # noqa: S603 - fixed argv
        [str(binary), "--version"], capture_output=True, text=True, check=True
    )
    assert "(build 11941" in plain.stdout
    other = subprocess.run(  # noqa: S603 - fixed argv
        [str(binary), "--version"],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "FAKE_LLAMA_BUILD": "11960"},
    )
    assert "(build 11960" in other.stdout


def test_health_delay_holds_the_503_answer(tmp_path: Path) -> None:
    fake = FakeServer(tmp_path, FAKE_LLAMA_HEALTH_DELAY="1.5")
    fake.start(wait_healthy=False)
    try:
        first = httpx.get(fake.url("/health"), timeout=2)
        assert first.status_code == 503
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if httpx.get(fake.url("/health"), timeout=2).status_code == 200:
                break
            time.sleep(0.1)
        else:
            pytest.fail("health never turned 200 after the delay")
    finally:
        fake.stop()


def test_embeddings_returns_a_fixed_vector(server: FakeServer) -> None:
    answer = httpx.post(server.url("/v1/embeddings"), json={"input": "hello"}, timeout=5)
    assert answer.status_code == 200
    assert answer.json()["data"][0]["embedding"] == [0.1, 0.2, 0.3]


def test_request_delay_holds_the_answer(tmp_path: Path) -> None:
    fake = FakeServer(tmp_path, FAKE_LLAMA_REQUEST_DELAY="1.5")
    fake.start()
    try:
        begun = time.monotonic()
        answer = httpx.post(fake.url("/v1/chat/completions"), json={"messages": []}, timeout=10)
        assert answer.status_code == 200
        assert time.monotonic() - begun >= 1.4
    finally:
        fake.stop()


def test_bind_fails_exits_with_the_bind_error_then_succeeds(tmp_path: Path) -> None:
    binary = install_fake_server(tmp_path / "bin")
    fails = touch_count_file(tmp_path / "logs", "bind-fails.txt", 2)
    env = {**os.environ, "FAKE_LLAMA_BIND_FAILS": str(fails)}
    for _ in range(2):
        port = _free_port()
        run = subprocess.run(  # noqa: S603 - fixed argv
            [str(binary), "--port", str(port)],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert run.returncode == 1
        assert BIND_ERROR_LINE.format(port=port) in run.stderr
    assert fails.read_text().strip() == "0"
    port = _free_port()
    good = subprocess.Popen(  # noqa: S603 - fixed argv
        [str(binary), "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
        else:  # pragma: no cover
            pytest.fail("third start never became healthy")
    finally:
        os.killpg(good.pid, 15)
        good.wait(timeout=5)


def test_exit_after_dies_after_n_answers(tmp_path: Path) -> None:
    fake = FakeServer(tmp_path / "crash", FAKE_LLAMA_EXIT_AFTER="1")
    fake.port = _free_port()
    fake.proc = subprocess.Popen(  # noqa: S603 - fixed argv
        [str(fake.binary), "--host", "127.0.0.1", "--port", str(fake.port)],
        env=fake.env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if httpx.get(fake.url("/health"), timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    else:  # pragma: no cover
        pytest.fail("crash fake never became healthy")
    httpx.post(fake.url("/v1/chat/completions"), json={"messages": []}, timeout=5)
    assert fake.proc.wait(timeout=5) == 1


def _run_client(commands: list[dict]) -> list[dict]:
    lines = "\n".join(json.dumps(c) for c in commands) + "\n"
    run = subprocess.run(  # noqa: S603 - fixed argv, repo fixture
        [sys.executable, str(CLIENT)],
        input=lines,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stderr
    return [json.loads(line) for line in run.stdout.splitlines()]


def test_client_answers_ping_and_refuses_unknown_commands() -> None:
    answers = _run_client([{"cmd": "ping"}, {"cmd": "nope"}, {"cmd": "exit"}])
    assert answers[0]["ok"] is True
    assert "pid" in answers[0]
    assert answers[1] == {"ok": False, "reason": "bad-command"}
    assert answers[2] == {"ok": True}


def test_client_refuses_a_request_before_a_join() -> None:
    answers = _run_client(
        [{"cmd": "request", "path": "/v1/chat/completions", "body": {}}, {"cmd": "exit"}]
    )
    assert answers[0] == {"ok": False, "reason": "not-joined"}
