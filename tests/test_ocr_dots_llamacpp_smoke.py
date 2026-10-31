"""Tests for the dots-mocr-llamacpp smoke script (task 2.6).

Change dots-mocr-llamacpp-backend.
The script is not an installable package, so the tests load it by path. They
never provision the engine, start a llama-server or use the network. The
sandbox test runs a real ``sandbox-exec`` on macOS only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / "ocr-workers" / "engines" / "dots-mocr-llamacpp"
SCRIPT = ENGINE_DIR / "smoke_test.py"
PROVISION_TEXT = "python3 ocr-workers/provision.py dots-mocr-llamacpp --accept-model-licence"

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
    for name in ("capabilities.json", "run.json", "worker-stderr.log", "eq01-p002.md"):
        assert name in out
    assert "plan only" in out
    assert snapshot(ENGINE_DIR) == before
    assert not (ENGINE_DIR / "smoke_evidence").exists()


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


class Fakes:
    """Replace the slow parts of the script and record what ran, in order."""

    def __init__(self, smoke: ModuleType, folder: Path) -> None:
        self.smoke = smoke
        self.calls: list[str] = []
        self.backend_id = "dots_mocr_llamacpp"
        self.pdf = folder / "doc.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n")
        self.evidence = folder / "evidence"

    def run(self, argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if "--capabilities" in argv:
            self.calls.append("probe")
            body = json.dumps({"backend_id": self.backend_id, "pipeline": {"revision": "x"}})
            return subprocess.CompletedProcess(argv, 0, body + "\n", "")
        self.calls.append("provision")
        assert "--accept-model-licence" in argv and "dots-mocr-llamacpp" in argv
        return subprocess.CompletedProcess(argv, 0, "", "")

    def worker(self, cases: list[tuple[str, Path, int]]) -> dict[str, Any]:
        self.calls.append("worker")
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


@pytest.fixture(name="fakes")
def _fakes(smoke: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    fakes = Fakes(smoke, tmp_path)
    fakes.install(monkeypatch)
    return fakes


def test_provision_runs_before_the_probe(smoke: ModuleType, fakes: Fakes) -> None:
    assert smoke.main(["--provision", "--case", f"eq01={fakes.pdf}:2"]) == 0
    assert fakes.calls == ["provision", "probe", "worker"]


def test_run_does_not_provision(smoke: ModuleType, fakes: Fakes) -> None:
    assert smoke.main(["--run", "--case", f"eq01={fakes.pdf}:2"]) == 0
    assert fakes.calls == ["probe", "worker"]
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
    def empty(cases: list[tuple[str, Path, int]]) -> dict[str, Any]:
        out = fakes.worker(cases)
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
        server = under_profile(
            "import socket; s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen(1);"
            " c = socket.create_connection(s.getsockname(), 2); c.send(b'x')"
        )
        assert server.returncode == 0, server.stderr
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
    folder = Path("/cache/dots-mocr-llamacpp/llama.cpp")
    busy = ["1 /sbin/launchd", f"77 {folder}/llama-server --port 9", "5 python -m other"]
    quiet = ["1 /sbin/launchd", "5 /other/cache/llama.cpp/llama-server --port 9"]
    assert smoke.leftover_processes(folder, busy) == [busy[1]]
    assert smoke.leftover_processes(folder, quiet) == []


def test_llama_folder_follows_the_cache_variable(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OMRS_OCR_MODEL_CACHE", str(tmp_path))
    assert smoke.llama_dir() == tmp_path / "dots-mocr-llamacpp" / "llama.cpp"
    monkeypatch.delenv("OMRS_OCR_MODEL_CACHE")
    assert smoke.llama_dir() == ENGINE_DIR / ".model-cache" / "llama.cpp"


def test_peak_parser_reads_time_output(smoke: ModuleType) -> None:
    text = "       1.0 real\n  123456789  peak memory footprint\n"
    assert smoke.parse_time_peak(text) == 123456789
    assert smoke.parse_time_peak("nothing here") is None
