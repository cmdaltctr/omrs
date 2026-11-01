"""The OCR host seam for a declared llama.cpp runtime (managed-llamacpp-runtimes, 6.2, 6.4, 6.5).

A test engine folder declares the fake ``llama-server`` in its manifest. The
worker is a fake that posts to ``$OMRS_OCR_RUNTIME_URL``, so each test sees
what the host handed to the worker and what reached the server.
"""

from __future__ import annotations

import ast
import logging
import os
import re
import signal
import socket
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.fixtures.llamacpp.harness import FakeRuntime, pid_alive, wait_until
from tests.fixtures.ocr_worker.runtime_engine import OcrRuntimeHarness, clean_environ

from omrs.integrations.llamacpp_runtime import manager as manager_module
from omrs.integrations.llamacpp_runtime import process

OCR_WORKER_DIR = (
    Path(__file__).resolve().parents[1] / "src" / "omrs" / "integrations" / "ocr_worker"
)


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[OcrRuntimeHarness]:
    for name in ("OMRS_OCR_MODEL_CACHE", "OMRS_OCR_RUNTIME_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(process, "HEALTH_POLL_SECONDS", 0.05)
    env = OcrRuntimeHarness(tmp_path)
    try:
        yield env
    finally:
        env.cleanup()


# ── 6.2 Worker environment, probe, restart, idle leave ───────────────────────


def test_worker_environment_holds_the_runtime_url(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    engine = harness.engine("engine-a")
    routes = harness.pool().routes(harness.settings(effective_settings, "engine-a"))
    pdf = harness.pdf("a.pdf")

    result = routes.select().parse(pdf, timeout=20)

    url = routes.primary.lease.base_url
    assert url is not None and re.fullmatch(r"http://127\.0\.0\.1:\d+", url)
    assert f"url={url}\n" in result.markdown
    assert engine.requests() == [pdf], "the worker used the URL it was given"
    assert len(engine.fake.starts()) == 1


def test_probe_and_route_build_start_no_server(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    engine = harness.engine("engine-a")
    routes = harness.pool().routes(harness.settings(effective_settings, "engine-a"))

    assert routes.fingerprint.available, "the capability probe ran the fake worker"
    assert engine.fake.starts() == []
    assert not routes.primary.lease.joined
    assert not (harness.state / "runtimes").exists()


def test_a_restart_on_a_new_port_restarts_the_worker(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    engine = harness.engine("engine-a")
    routes = harness.pool().routes(harness.settings(effective_settings, "engine-a"))
    first = routes.select().parse(harness.pdf("a.pdf"), timeout=20)
    lease = routes.primary.lease
    old_url = lease.base_url
    server_pid = int(engine.fake.starts()[0]["pid"])
    os.killpg(server_pid, signal.SIGKILL)
    assert wait_until(lambda: not pid_alive(server_pid))
    assert lease.restart_if_crashed() is True
    assert lease.base_url != old_url

    second = routes.select().parse(harness.pdf("b.pdf"), timeout=20)

    assert f"url={lease.base_url}\n" in second.markdown
    assert re.search(r"pid=(\d+)", first.markdown).group(1) != re.search(
        r"pid=(\d+)", second.markdown
    ).group(1), "the worker restarted"
    assert routes.primary.process_generations == 2


def test_the_worker_closes_before_the_idle_leave(
    harness: OcrRuntimeHarness, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(manager_module, "IDLE_STOP_SECONDS", 0.3)
    monkeypatch.setattr(manager_module, "IDLE_CHECK_SECONDS", 0.1)
    engine = harness.engine("engine-a")
    routes = harness.pool().routes(harness.settings(effective_settings, "engine-a"))
    routes.select().parse(harness.pdf("a.pdf"), timeout=20)
    client, lease = routes.primary, routes.primary.lease
    assert client.is_started
    real_leave = lease.leave
    seen: list[bool] = []

    def spy(*args: Any, **kwargs: Any) -> None:
        seen.append(client.is_started)
        real_leave(*args, **kwargs)

    lease.leave = spy  # type: ignore[method-assign]
    assert wait_until(lambda: bool(seen), timeout=10)

    assert seen == [False], "the worker was closed when the lease left"
    server_pid = int(engine.fake.starts()[0]["pid"])
    assert wait_until(lambda: not pid_alive(server_pid))
    lease.leave = real_leave  # type: ignore[method-assign]
    again = routes.select().parse(harness.pdf("b.pdf"), timeout=20)
    assert "url=http://127.0.0.1:" in again.markdown
    assert len(engine.fake.starts()) == 2, "the next request starts the runtime again"


def test_a_declaration_that_breaks_a_rule_makes_the_route_unavailable(
    harness: OcrRuntimeHarness, effective_settings: Any, caplog: pytest.LogCaptureFixture
) -> None:
    engine = harness.engine("engine-a")
    manifest = engine.folder / "pyproject.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("bin/llama-server", "../llama-server"),
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        routes = harness.pool().routes(harness.settings(effective_settings, "engine-a"))

    assert routes.select() is None
    assert "path rule" in caplog.text
    assert engine.fake.starts() == []


def test_a_pool_without_a_manager_leaves_a_declared_runtime_unavailable(
    harness: OcrRuntimeHarness, effective_settings: Any, caplog: pytest.LogCaptureFixture
) -> None:
    engine = harness.engine("engine-a")
    with caplog.at_level(logging.WARNING):
        routes = harness.pool(with_manager=False).routes(
            harness.settings(effective_settings, "engine-a")
        )

    assert routes.select() is None
    assert "runtime manager" in caplog.text
    assert engine.fake.starts() == []


def test_no_host_module_names_an_engine_or_the_props_field() -> None:
    engines = re.compile(r"dots|paddle|surya|docling|mineru", re.IGNORECASE)
    hits: list[str] = []
    for path in sorted(OCR_WORKER_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            text = None
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = None if id(node) in docstrings else node.value
            elif isinstance(node, ast.Name):
                text = node.id
            elif isinstance(node, ast.Attribute):
                text = node.attr
            if text and (engines.search(text) or "build_info" in text):
                hits.append(f"{path.name}: {text!r}")
    assert hits == [], "host code names an engine or the /props field"


# ── 6.4 External runtime (the real-binary /props check waits for the operator) ──


@contextmanager
def _external_server(folder: Path, **env: object) -> Iterator[tuple[str, FakeRuntime]]:
    """Run the fake ``llama-server`` on a free port and yield its base URL."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    fake = FakeRuntime(folder)
    fake.set_env(FAKE_LLAMA_REQUESTS=str(fake.logs / "requests.txt"), **env)
    proc = subprocess.Popen(  # noqa: S603 - fixture binary, fixed argv
        [str(fake.binary), "--host", "127.0.0.1", "--port", str(port)],
        env=clean_environ(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    url = f"http://127.0.0.1:{port}"

    def healthy() -> bool:
        try:
            return httpx.get(f"{url}/health", timeout=1).status_code == 200
        except httpx.HTTPError:
            return False

    try:
        assert wait_until(healthy)
        yield url, fake
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)


def test_a_matching_external_build_passes_the_url_and_starts_nothing(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    engine = harness.engine("engine-a")
    with _external_server(harness.tmp_path / "ext") as (url, external):
        settings = harness.settings(effective_settings, "engine-a", ocr_runtime_url=url)
        routes = harness.pool().routes(settings)
        pdf = harness.pdf("a.pdf")

        result = routes.select().parse(pdf, timeout=20)

        assert f"url={url}\n" in result.markdown
        assert engine.fake.starts() == [], "OMRS started nothing"
        recorded = (external.logs / "requests.txt").read_text(encoding="utf-8")
        assert pdf in recorded, "the request reached the external server"
        assert not (harness.state / "runtimes" / "ocr-engine-a" / "server.json").exists()


def test_another_external_build_gives_wrong_build_and_the_fallback_serves(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    harness.engine("engine-a")
    harness.engine("engine-b", runtime=False)
    with _external_server(harness.tmp_path / "ext", FAKE_LLAMA_BUILD=11960) as (url, external):
        settings = harness.settings(effective_settings, "engine-a", "engine-b", ocr_runtime_url=url)
        routes = harness.pool().routes(settings)

        client = routes.select()
        result = client.parse(harness.pdf("a.pdf"), timeout=20)

        assert "url=<absent>" in result.markdown, "the fallback engine served the file"
        assert not (external.logs / "requests.txt").exists(), "the wrong build got no request"
        with pytest.raises(Exception) as caught:  # noqa: PT011 - the type is the subject
            routes.primary.lease.join()
        assert getattr(caught.value, "reason", None) == "wrong-build"


def test_an_external_runtime_reports_its_mode_and_checks_no_files(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    harness.engine("engine-a")
    with _external_server(harness.tmp_path / "ext") as (url, _external):
        routes = harness.pool().routes(
            harness.settings(effective_settings, "engine-a", ocr_runtime_url=url)
        )
        item = harness.manager.status([routes.primary.lease.spec])[0]

        assert item["mode"] == "external"
        assert item["files_checked"] is False
        assert item["id"] == "ocr-engine-a"


def test_a_blank_url_gives_a_managed_runtime(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    harness.engine("engine-a")
    routes = harness.pool().routes(harness.settings(effective_settings, "engine-a"))
    spec = routes.primary.lease.spec
    item = harness.manager.status([spec])[0]

    assert spec.mode == "managed"
    assert item["mode"] == "managed" and item["files_checked"] is True


# ── 6.5 An engine without a runtime block ────────────────────────────────────


def test_an_engine_without_a_block_starts_no_server_and_gets_no_url(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    harness.engine("engine-p", runtime=False)
    routes = harness.pool().routes(harness.settings(effective_settings, "engine-p"))

    result = routes.select().parse(harness.pdf("a.pdf"), timeout=20)

    assert "url=<absent>" in result.markdown, (
        "OMRS_OCR_RUNTIME_URL is not in the worker environment"
    )
    assert routes.primary.lease is None
    assert not (harness.state / "runtimes").exists()
