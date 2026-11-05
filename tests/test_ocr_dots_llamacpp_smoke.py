"""Tests for the dots-mocr smoke script on llama.cpp (tasks 2.6 and 2b.6).

Change dots-mocr-llamacpp-backend.
The script is not an installable package, so the tests load it by path. They
never provision the engine, start a real llama-server or use the network. The
runtime session test starts the shared fake server through the host's runtime
manager. The sandbox test runs a real ``sandbox-exec`` on macOS only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from tests.fixtures.llamacpp.harness import pid_alive, wait_until
from tests.fixtures.ocr_worker.dots_llamacpp import stand_in_engine

from omrs.integrations.llamacpp_runtime import process
from omrs.integrations.llamacpp_runtime.state import read_server_record, runtime_dir

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / "ocr-workers" / "engines" / "dots-mocr"
SCRIPT = ENGINE_DIR / "smoke_test.py"
PROVISION_TEXT = "python3 ocr-workers/provision.py dots-mocr --accept-model-licence"

needs_sandbox = pytest.mark.skipif(
    sys.platform != "darwin" or not shutil.which("sandbox-exec"),
    reason="the offline check needs macOS sandbox-exec",
)


@pytest.fixture(name="smoke")
def _smoke() -> Iterator[ModuleType]:
    """Load the script by path without writing bytecode into the engine folder."""
    spec = importlib.util.spec_from_file_location("dots_llamacpp_smoke", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    saved = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved
    yield module


def snapshot(folder: Path) -> dict[str, tuple[int, int]]:
    """Return every path under *folder* with its size and mtime in nanoseconds."""
    return {
        str(path.relative_to(folder)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(folder.rglob("*"))
    }


def _refuse(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("plan only must not start a process or use the network")


def test_plan_only_lists_steps_and_touches_nothing(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subprocess, "run", _refuse)
    monkeypatch.setattr(subprocess, "Popen", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(tempfile, "mkdtemp", _refuse)
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _refuse)
    before = snapshot(ENGINE_DIR)

    assert smoke.main(["--case", "eq01=/x/y.pdf:2", "--case", "eq01=/x/y.pdf:3"]) == 0

    out = capsys.readouterr().out
    assert PROVISION_TEXT in out
    assert "4.4 GB" in out
    assert "--capabilities" in out
    assert "dots_mocr_llamacpp" in out
    assert "eq01" in out and "page 2" in out and "page 3" in out
    assert "sandbox-exec" in out
    assert "clean exit" in out
    assert "RuntimeManager" in out and "OMRS_STATE_DIR" in out and "OMRS_OCR_RUNTIME_URL" in out
    for name in ("capabilities.json", "run.json", "worker-stderr.log", "eq01-p002.md"):
        assert name in out
    assert "plan only" in out
    assert snapshot(ENGINE_DIR) == before


def test_plan_only_as_a_real_subprocess(tmp_path: Path) -> None:
    before = snapshot(ENGINE_DIR)
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-B", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert PROVISION_TEXT in result.stdout
    assert snapshot(ENGINE_DIR) == before
    assert list(tmp_path.iterdir()) == []


class FakeSession:
    """Stands for :class:`RuntimeSession`: records the start, the pid and the leave."""

    url = "http://127.0.0.1:12345"

    def __init__(self, calls: list[str], fail: str = "") -> None:
        self.calls = calls
        self.fail = fail

    def start(self) -> str:
        self.calls.append("runtime")
        if self.fail:
            raise RuntimeError(self.fail)
        return self.url

    def pid(self) -> int | None:
        return None

    def leave(self) -> None:
        self.calls.append("leave")


class Fakes:
    """Replace the slow parts of the script and record what ran, in order."""

    def __init__(self, smoke: ModuleType, folder: Path) -> None:
        self.smoke = smoke
        self.calls: list[str] = []
        self.backend_id = "dots_mocr_llamacpp"
        self.pdf = folder / "doc.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n")
        self.evidence = folder / "evidence"
        self.state = folder / "scratch-state"
        self.session = FakeSession(self.calls)
        self.worker_urls: list[str] = []
        self.session_state: Path | None = None

    def make_session(self, state: Path) -> FakeSession:
        self.session_state = state
        return self.session

    def run(self, argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if "--capabilities" in argv:
            self.calls.append("probe")
            body = json.dumps({"backend_id": self.backend_id, "pipeline": {"revision": "x"}})
            return subprocess.CompletedProcess(argv, 0, body + "\n", "")
        self.calls.append("provision")
        assert "--accept-model-licence" in argv and "dots-mocr" in argv
        return subprocess.CompletedProcess(argv, 0, "", "")

    def worker(
        self, cases: list[tuple[str, Path, int]], session: FakeSession | None = None
    ) -> dict[str, Any]:
        self.calls.append("worker")
        self.worker_urls.append(getattr(session, "url", ""))
        results = [
            {"case": n, "page": p, "ok": True, "seconds": 1.0, "chars": 5} for n, _, p in cases
        ]
        for name, _, page in cases:
            (self.evidence / f"{name}-p{page:03d}.md").write_text("hello", encoding="utf-8")
        return {"results": results, "stderr": "", "peak": {"method": "fake"}}

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(self.smoke, "EVIDENCE_DIR", self.evidence)
        monkeypatch.setattr(self.smoke, "sandbox_available", lambda: True)
        monkeypatch.setattr(self.smoke, "engine_ready", lambda: True)
        monkeypatch.setattr(self.smoke, "list_processes", lambda: [])
        monkeypatch.setattr(self.smoke, "CLEAN_EXIT_WAIT_SECONDS", 0.0)
        monkeypatch.setattr(self.smoke.subprocess, "run", self.run)
        monkeypatch.setattr(self.smoke, "run_worker", self.worker)
        monkeypatch.setattr(self.smoke, "RuntimeSession", self.make_session)
        monkeypatch.setattr(self.smoke.tempfile, "mkdtemp", lambda **_k: str(self.state))
        monkeypatch.setenv("OMRS_STATE_DIR", "/not/the/scratch/folder")


@pytest.fixture(name="fakes")
def _fakes(smoke: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    fakes = Fakes(smoke, tmp_path)
    fakes.install(monkeypatch)
    return fakes


def test_provision_runs_before_the_probe(smoke: ModuleType, fakes: Fakes) -> None:
    assert smoke.main(["--provision", "--case", f"eq01={fakes.pdf}:2"]) == 0
    assert fakes.calls == ["provision", "probe", "runtime", "worker", "leave"]


def test_run_does_not_provision(smoke: ModuleType, fakes: Fakes) -> None:
    assert smoke.main(["--run", "--case", f"eq01={fakes.pdf}:2"]) == 0
    assert fakes.calls == ["probe", "runtime", "worker", "leave"]
    evidence = json.loads((fakes.evidence / "run.json").read_text(encoding="utf-8"))
    assert evidence["clean_exit"] is True
    assert (fakes.evidence / "capabilities.json").is_file()


def test_run_needs_a_case(smoke: ModuleType, fakes: Fakes) -> None:
    with pytest.raises(SystemExit) as stopped:
        smoke.main(["--run"])
    assert stopped.value.code == 2
    assert fakes.calls == []


def test_wrong_backend_id_fails_the_run(smoke: ModuleType, fakes: Fakes) -> None:
    fakes.backend_id = "dots_mocr"
    assert smoke.main(["--run", "--case", f"eq01={fakes.pdf}:2"]) != 0
    assert fakes.calls == ["probe"]


def test_empty_markdown_fails_the_run(
    smoke: ModuleType, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def empty(cases: list[tuple[str, Path, int]], session: FakeSession) -> dict[str, Any]:
        out = fakes.worker(cases, session)
        out["results"][0]["chars"] = 0
        return out

    monkeypatch.setattr(smoke, "run_worker", empty)
    assert smoke.main(["--run", "--case", f"eq01={fakes.pdf}:2"]) != 0


def test_a_leftover_server_fails_the_run(
    smoke: ModuleType, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    leftover = f"123 {smoke.llama_dir()}/llama-server --port 1"
    monkeypatch.setattr(smoke, "list_processes", lambda: [leftover])
    assert smoke.main(["--run", "--case", f"eq01={fakes.pdf}:2"]) != 0
    evidence = json.loads((fakes.evidence / "run.json").read_text(encoding="utf-8"))
    assert evidence["clean_exit"] is False


def test_run_without_sandbox_exec_says_so(
    smoke: ModuleType,
    fakes: Fakes,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(smoke, "sandbox_available", lambda: False)
    assert smoke.main(["--provision", "--case", f"eq01={fakes.pdf}:2"]) != 0
    assert "sandbox-exec" in capsys.readouterr().err
    assert fakes.calls == []


def test_the_runtime_starts_after_the_probe_and_its_url_goes_to_the_worker(
    smoke: ModuleType, fakes: Fakes
) -> None:
    assert smoke.main(["--run", "--case", f"eq01={fakes.pdf}:2"]) == 0
    assert fakes.worker_urls == [FakeSession.url]


def test_the_runtime_uses_a_scratch_state_folder_and_not_the_real_one(
    smoke: ModuleType, fakes: Fakes
) -> None:
    assert smoke.main(["--run", "--case", f"eq01={fakes.pdf}:2"]) == 0
    assert os.environ["OMRS_STATE_DIR"] == str(fakes.state)
    assert fakes.session_state == fakes.state
    evidence = json.loads((fakes.evidence / "run.json").read_text(encoding="utf-8"))
    assert evidence["state_dir"] == str(fakes.state)


def test_the_runtime_is_left_when_the_worker_raises(smoke: ModuleType, fakes: Fakes) -> None:
    def boom(_cases: object, _session: object) -> dict[str, Any]:
        fakes.calls.append("worker")
        raise RuntimeError("worker broke")

    fakes.smoke.run_worker = boom
    with pytest.raises(RuntimeError, match="worker broke"):
        smoke.main(["--run", "--case", f"eq01={fakes.pdf}:2"])
    assert fakes.calls == ["probe", "runtime", "worker", "leave"]


def test_a_runtime_that_does_not_start_fails_the_run_with_its_reason(
    smoke: ModuleType, fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    fakes.session.fail = "A model file changed: dots-mocr-Q8_0.gguf."
    assert smoke.main(["--run", "--case", f"eq01={fakes.pdf}:2"]) != 0
    assert "dots-mocr-Q8_0.gguf" in capsys.readouterr().err
    assert fakes.calls == ["probe", "runtime", "leave"]


def test_the_worker_gets_the_runtime_url_in_its_environment(smoke: ModuleType) -> None:
    env = smoke.worker_env("http://127.0.0.1:4321")
    assert env["OMRS_OCR_RUNTIME_URL"] == "http://127.0.0.1:4321"
    assert env["PATH"] == os.environ["PATH"]


class FakePopen:
    """Stands for the sandboxed worker process: answers each request with one page."""

    started: list[dict[str, Any]] = []  # noqa: RUF012 - reset by the test

    def __init__(self, argv: list[str], **kwargs: Any) -> None:
        self.argv, self.kwargs = argv, kwargs
        FakePopen.started.append(kwargs)
        self.requests: list[dict[str, Any]] = []
        self.stdin = self
        self.stdout = self

    def write(self, line: str) -> None:
        self.requests.append(json.loads(line))

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass

    def readline(self) -> str:
        request = self.requests[-1]
        return json.dumps({"id": request["id"], "ok": True, "pages_markdown": ["page text"]}) + "\n"

    def wait(self, timeout: float | None = None) -> int:
        return 0


def test_the_real_worker_launch_passes_the_runtime_url_in_its_environment(
    smoke: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakePopen.started = []
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    monkeypatch.setattr(smoke, "EVIDENCE_DIR", evidence)
    monkeypatch.setattr(smoke.subprocess, "Popen", FakePopen)
    session = FakeSession([])
    session.start()

    outcome = smoke.run_worker([("eq01", tmp_path / "x.pdf", 2)], session)

    (launch,) = FakePopen.started
    assert launch["env"]["OMRS_OCR_RUNTIME_URL"] == FakeSession.url
    assert outcome["results"][0]["ok"] is True and outcome["results"][0]["chars"] == 9
    assert (evidence / "eq01-p002.md").read_text(encoding="utf-8") == "page text"


def test_the_script_has_no_pid_file_reader(smoke: ModuleType) -> None:
    assert not hasattr(smoke, "server_pid")
    assert "llama-server.pid" not in SCRIPT.read_text(encoding="utf-8")


def test_the_runtime_session_starts_the_declared_server_and_leaves_it(
    smoke: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Against the shared fake: the host manager starts it, the pid is known, leaving stops it."""
    folder = tmp_path / "engines" / "dots-mocr"
    folder.mkdir(parents=True)
    fake = stand_in_engine(folder)
    monkeypatch.setattr(smoke, "ENGINE_DIR", folder)
    monkeypatch.delenv("OMRS_OCR_MODEL_CACHE", raising=False)
    monkeypatch.setattr(process, "HEALTH_POLL_SECONDS", 0.05)
    state = tmp_path / "state"
    session = smoke.RuntimeSession(state)
    try:
        url = session.start()
        assert url.startswith("http://127.0.0.1:")
        (started,) = fake.starts()
        assert started["argv"][-2:] != []  # the declared flags travel with the start
        assert "-np" in started["argv"] and "24576" in started["argv"]
        pid = session.pid()
        assert pid == started["pid"] and pid_alive(pid)
        record = read_server_record(runtime_dir(state, "ocr-dots-mocr"))
        assert record is not None and record.pid == pid
    finally:
        session.leave()
    assert wait_until(lambda: not pid_alive(pid))
    after = read_server_record(runtime_dir(state, "ocr-dots-mocr"))
    assert after is not None and after.stopped_by == "last-client"
    fake.kill_all()


def test_a_runtime_session_refuses_a_changed_model_file_and_starts_nothing(
    smoke: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "engines" / "dots-mocr"
    folder.mkdir(parents=True)
    fake = stand_in_engine(folder)
    (folder / ".model-cache" / "models" / "dots-mocr-Q8_0.gguf").write_bytes(b"changed")
    monkeypatch.setattr(smoke, "ENGINE_DIR", folder)
    monkeypatch.delenv("OMRS_OCR_MODEL_CACHE", raising=False)
    session = smoke.RuntimeSession(tmp_path / "state")
    try:
        with pytest.raises(Exception, match="dots-mocr-Q8_0.gguf"):
            session.start()
    finally:
        session.leave()
    assert fake.starts() == []


@needs_sandbox
def test_sandbox_profile_allows_loopback_and_denies_the_rest(smoke: ModuleType) -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    port = listener.getsockname()[1]

    def under_profile(code: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                "/usr/bin/sandbox-exec",
                "-p",
                smoke.SANDBOX_PROFILE,
                sys.executable,
                "-I",
                "-c",
                code,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    try:
        loopback = under_profile(
            f"import socket; socket.create_connection(('127.0.0.1', {port}), 2)"
        )
        assert loopback.returncode == 0, loopback.stderr
        server = under_profile("import socket; s = socket.socket(); s.bind(('127.0.0.1', 0))")
        assert server.returncode != 0, "the worker has no reason to listen"
        outside = under_profile("import socket; socket.create_connection(('203.0.113.1', 9), 2)")
    finally:
        listener.close()
    assert outside.returncode != 0
    assert "PermissionError" in outside.stderr or "Operation not permitted" in outside.stderr
    assert "timed out" not in outside.stderr


def test_case_parser(smoke: ModuleType) -> None:
    assert smoke.parse_case("eq01=/x/y.pdf:2") == ("eq01", Path("/x/y.pdf"), 2)
    with pytest.raises(argparse.ArgumentTypeError):
        smoke.parse_case("bad")


def test_clean_exit_helper(smoke: ModuleType) -> None:
    folder = Path("/cache/dots-mocr/llama.cpp")
    busy = ["1 /sbin/launchd", f"77 {folder}/llama-server --port 9", "5 python -m other"]
    quiet = ["1 /sbin/launchd", "5 /other/cache/llama.cpp/llama-server --port 9"]
    assert smoke.leftover_processes(folder, busy) == [busy[1]]
    assert smoke.leftover_processes(folder, quiet) == []


def test_llama_folder_follows_the_cache_variable(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OMRS_OCR_MODEL_CACHE", str(tmp_path))
    assert smoke.llama_dir() == tmp_path / "dots-mocr" / "llama.cpp"
    monkeypatch.delenv("OMRS_OCR_MODEL_CACHE")
    assert smoke.llama_dir() == ENGINE_DIR / ".model-cache" / "llama.cpp"


def test_peak_parser_reads_time_output(smoke: ModuleType) -> None:
    text = "       1.0 real\n  123456789  peak memory footprint\n"
    assert smoke.parse_time_peak(text) == 123456789
    assert smoke.parse_time_peak("nothing here") is None
