"""``experiments/_lib/run_guard.py`` (experiment-35 task 2.7).

A fake llama.cpp server on a loopback port answers ``/props`` and
``/v1/models``, as in ``test_experiment_llamacpp_runtime.py``. A temporary
git repository gives ``record_run_start`` a commit to read.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from experiments._lib.preflight import PreflightError
from experiments._lib.run_guard import guard_run

from omrs.core.experiment_records.runtime_block import RuntimeBlock

_FILE = "Qwen3-Embedding-0.6B-Q8_0.gguf"
_BUILD = 11671


class _Fake:
    """What the fake server answers."""

    def __init__(self) -> None:
        self.props: dict[str, Any] = {}
        self.models: dict[str, Any] = {}


@pytest.fixture
def fake() -> Iterator[tuple[_Fake, str]]:
    state = _Fake()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            body = {"/props": state.props, "/v1/models": state.models}.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - base name
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _git(repo: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        check=True,
    )


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    _git(tmp_path, "init", "-q")
    path = tmp_path / "experiments" / "35-full-rag-benchmark-2026-11-10"
    path.mkdir(parents=True)
    (path / "plan.json").write_text('{"hypothesis": "x"}\n', encoding="utf-8")
    (tmp_path / ".gitignore").write_text("output/\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "--no-verify", "-m", "start")
    return path


def _serve(state: _Fake, weights: Path) -> None:
    state.props = {"role": "router", "model_path": "none", "build_info": f"b{_BUILD}-ba3c05f71"}
    state.models = {
        "data": [
            {
                "id": "model-0",
                "status": {
                    "value": "loaded",
                    "args": ["llama-server", "--model", str(weights), "--pooling", "last"],
                },
            }
        ]
    }


def _block(sha: str) -> RuntimeBlock:
    return RuntimeBlock.model_validate(
        {
            "models": [
                {
                    "role": "embedding",
                    "repository": "Qwen/Qwen3-Embedding-0.6B-GGUF",
                    "file": _FILE,
                    "sha256": sha,
                    "runtime": "llama.cpp",
                    "build": _BUILD,
                }
            ],
            "tolerance": [{"metric": "recall_at_10", "max_abs_change": 0.01}],
        }
    )


def _run(folder: Path, block: RuntimeBlock, url: str) -> None:
    """A runner in miniature: guard first, then write the score file."""
    guard_run(folder, block, base_url=url, command="run-exp35")
    (folder / "output").mkdir(exist_ok=True)
    (folder / "output" / "scores.json").write_text("{}", encoding="utf-8")


def test_wrong_gguf_hash_stops_before_scoring(
    fake: tuple[_Fake, str], folder: Path, tmp_path: Path
) -> None:
    state, url = fake
    weights = tmp_path / "snapshots" / _FILE
    weights.parent.mkdir()
    weights.write_bytes(b"gguf weights")
    _serve(state, weights)
    with pytest.raises(PreflightError, match="SHA-256"):
        _run(folder, _block("1" * 64), url)
    assert not (folder / "output" / "scores.json").exists()
    assert not (folder / "output" / "run-records.jsonl").exists()


def test_matching_hash_records_the_runtime_then_scoring_proceeds(
    fake: tuple[_Fake, str], folder: Path, tmp_path: Path
) -> None:
    state, url = fake
    weights = tmp_path / "snapshots" / _FILE
    weights.parent.mkdir()
    weights.write_bytes(b"gguf weights")
    sha = hashlib.sha256(b"gguf weights").hexdigest()
    _serve(state, weights)
    _run(folder, _block(sha), url)
    (line,) = (folder / "output" / "run-records.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert record["command"] == "run-exp35"
    assert record["runtime"] == {"build": _BUILD, "models": [{"file": _FILE, "sha256": sha}]}
    assert (folder / "output" / "scores.json").exists()
