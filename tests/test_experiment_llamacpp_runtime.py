"""``experiments/_lib/llamacpp_runtime.py`` (reproducible-experiment-runtime, task 3.1, D5).

A fake llama.cpp server on a loopback port answers ``/props`` and
``/v1/models``. Small temporary files stand in for the GGUF weights.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from experiments._lib.llamacpp_runtime import FoundRuntime, verify_llamacpp_runtime
from experiments._lib.preflight import PreflightError

from omrs.core.experiment_records.runtime_block import RuntimeBlock

_FILE = "Qwen3-Embedding-0.6B-Q8_0.gguf"


class _Fake:
    """What the fake server answers. Tests change the fields."""

    def __init__(self) -> None:
        self.props: dict[str, Any] = {}
        self.models: dict[str, Any] | None = None
        self.paths: list[str] = []


@pytest.fixture
def fake() -> Iterator[tuple[_Fake, str]]:
    state = _Fake()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            state.paths.append(self.path)
            if self.path == "/props":
                body: Any = state.props
            elif self.path == "/v1/models" and state.models is not None:
                body = state.models
            else:
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


def _weights(tmp_path: Path, name: str = _FILE, content: bytes = b"gguf weights") -> Path:
    path = tmp_path / "snapshots" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _block(sha: str, build: int = 11671, **extra: Any) -> RuntimeBlock:
    data: dict[str, Any] = {
        "models": [
            {
                "role": "embedding",
                "repository": "Qwen/Qwen3-Embedding-0.6B-GGUF",
                "file": _FILE,
                "sha256": sha,
                "runtime": "llama.cpp",
                "build": build,
            }
        ],
        "tolerance": [{"metric": "recall_at_10", "max_abs_change": 0.01}],
    }
    data.update(extra)
    return RuntimeBlock.model_validate(data)


def _router(state: _Fake, *paths: Path, build: str = "b11671-ba3c05f71") -> None:
    state.props = {"role": "router", "model_path": "none", "build_info": build}
    state.models = {
        "data": [
            {
                "id": f"model-{n}",
                "status": {
                    "value": "loaded",
                    "args": ["llama-server", "--port", "1", "--model", str(p), "--pooling", "last"],
                },
            }
            for n, p in enumerate(paths)
        ]
    }


def test_matching_build_and_hash_returns_found_values(
    fake: tuple[_Fake, str], tmp_path: Path
) -> None:
    state, url = fake
    path = _weights(tmp_path)
    _router(state, path)
    found = verify_llamacpp_runtime(_block(_sha(path)), base_url=url)
    assert isinstance(found, FoundRuntime)
    assert found.build == 11671
    assert found.models == [{"file": _FILE, "sha256": _sha(path)}]
    assert found.as_run_record() == {
        "build": 11671,
        "models": [{"file": _FILE, "sha256": _sha(path)}],
    }


def test_wrong_build_names_both_builds(fake: tuple[_Fake, str], tmp_path: Path) -> None:
    state, url = fake
    path = _weights(tmp_path)
    _router(state, path, build="b11510-0123abc")
    with pytest.raises(PreflightError) as caught:
        verify_llamacpp_runtime(_block(_sha(path), build=11671), base_url=url)
    message = str(caught.value)
    assert "11671" in message
    assert "11510" in message


def test_wrong_hash_names_file_and_both_hashes(fake: tuple[_Fake, str], tmp_path: Path) -> None:
    state, url = fake
    path = _weights(tmp_path)
    _router(state, path)
    expected = "1" * 64
    with pytest.raises(PreflightError) as caught:
        verify_llamacpp_runtime(_block(expected), base_url=url)
    message = str(caught.value)
    assert _FILE in message
    assert expected in message
    assert _sha(path) in message


def test_router_mode_reads_the_path_from_v1_models(fake: tuple[_Fake, str], tmp_path: Path) -> None:
    state, url = fake
    other = _weights(tmp_path, "Other-Q4_K_M.gguf", b"other")
    path = _weights(tmp_path)
    _router(state, other, path)
    found = verify_llamacpp_runtime(_block(_sha(path)), base_url=url)
    assert found.models == [{"file": _FILE, "sha256": _sha(path)}]
    assert "/v1/models" in state.paths


def test_router_mode_accepts_the_equals_form(fake: tuple[_Fake, str], tmp_path: Path) -> None:
    state, url = fake
    path = _weights(tmp_path)
    _router(state, path)
    state.models = {"data": [{"id": "m", "status": {"args": [f"--model={path}"]}}]}
    found = verify_llamacpp_runtime(_block(_sha(path)), base_url=url)
    assert found.models[0]["sha256"] == _sha(path)


def test_single_model_mode_reads_model_path_from_props(
    fake: tuple[_Fake, str], tmp_path: Path
) -> None:
    state, url = fake
    path = _weights(tmp_path)
    state.props = {"model_path": str(path), "build_info": "b11671-ba3c05f71"}
    found = verify_llamacpp_runtime(_block(_sha(path)), base_url=url)
    assert found.models == [{"file": _FILE, "sha256": _sha(path)}]
    assert "/v1/models" not in state.paths


def test_model_the_server_does_not_list_is_refused(fake: tuple[_Fake, str], tmp_path: Path) -> None:
    state, url = fake
    other = _weights(tmp_path, "Other-Q4_K_M.gguf", b"other")
    _router(state, other)
    with pytest.raises(PreflightError, match=_FILE):
        verify_llamacpp_runtime(_block("1" * 64), base_url=url)


def test_unreadable_build_info_is_refused(fake: tuple[_Fake, str], tmp_path: Path) -> None:
    state, url = fake
    path = _weights(tmp_path)
    _router(state, path, build="unknown")
    with pytest.raises(PreflightError, match="build_info"):
        verify_llamacpp_runtime(_block(_sha(path)), base_url=url)


def test_runtime_under_test_arm_and_references_are_skipped(
    fake: tuple[_Fake, str], tmp_path: Path
) -> None:
    state, url = fake
    path = _weights(tmp_path)
    _router(state, path)
    block = RuntimeBlock.model_validate(
        {
            "runtime_under_test": True,
            "models": [
                _block(_sha(path)).models[0].model_dump(),
                {
                    "role": "decision",
                    "repository": "mlx-community/x",
                    "file": "model.safetensors",
                    "sha256": "1" * 64,
                    "runtime": "mlx",
                    "version": "0.29.1",
                },
            ],
            "references": [{"role": "reference", "provider": "cloudflare", "model": "m"}],
            "tolerance": [{"metric": "recall_at_10", "max_abs_change": 0.01}],
        }
    )
    found = verify_llamacpp_runtime(block, base_url=url)
    assert [m["file"] for m in found.models] == [_FILE]
    # The skipped arm stays in the run record as planned and not checked.
    assert found.as_run_record()["unchecked"] == [
        {
            "role": "decision",
            "runtime": "mlx",
            "version": "0.29.1",
            "file": "model.safetensors",
            "sha256": "1" * 64,
        }
    ]


def test_run_record_has_no_unchecked_key_when_every_arm_is_checked(
    fake: tuple[_Fake, str], tmp_path: Path
) -> None:
    state, url = fake
    path = _weights(tmp_path)
    _router(state, path)
    found = verify_llamacpp_runtime(_block(_sha(path)), base_url=url)
    assert "unchecked" not in found.as_run_record()


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.10:9931",
        "http://example.com:9931",
        "http://0.0.0.0:9931",
        "http://127.0.0.1.example.com:9931",
        "file:///etc/passwd",
    ],
)
def test_non_loopback_address_is_refused(url: str) -> None:
    with pytest.raises(PreflightError, match="loopback"):
        verify_llamacpp_runtime(_block("1" * 64), base_url=url)


@pytest.mark.parametrize("host", ["localhost", "[::1]"])
def test_other_loopback_names_pass_the_address_rule(host: str) -> None:
    # Nothing listens on port 9 here; the error must be about the connection.
    with pytest.raises(PreflightError) as caught:
        verify_llamacpp_runtime(_block("1" * 64), base_url=f"http://{host}:9")
    assert "loopback" not in str(caught.value)
