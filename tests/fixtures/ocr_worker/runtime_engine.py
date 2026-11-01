"""Build test engine folders for the OCR runtime seam (change managed-llamacpp-runtimes).

An engine folder holds a ``pyproject.toml`` and a ``.venv/bin/python`` launcher.
The launcher runs ``runtime_worker.py`` (a fake worker that is a client of a
``llama-server``). An engine with a runtime declares the fake ``llama-server``
of ``tests/fixtures/llamacpp`` inside its model cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.fixtures.llamacpp.harness import FakeRuntime

from omrs.capabilities import probe_ocr_worker, reset_ocr_fingerprint_cache
from omrs.integrations.llamacpp_runtime.manager import RuntimeManager
from omrs.integrations.ocr_worker.pool import OcrClientPool

WORKER = Path(__file__).resolve().parent / "runtime_worker.py"

#: The build the fake server reports by default.
BUILD = 11941


@dataclass
class TestEngine:
    """One engine folder and, when it declares a runtime, its fake server."""

    __test__ = False  # not a pytest class

    name: str
    folder: Path
    fake: FakeRuntime | None

    @property
    def model(self) -> Path:
        """The declared model file."""
        assert self.fake is not None
        return self.fake.model

    @property
    def runtime_id(self) -> str:
        """The runtime id the host gives this engine."""
        return f"ocr-{self.name}"

    def set_fake(self, **values: object) -> None:
        """Replace the fake server's behaviour values; keep the request record."""
        assert self.fake is not None
        self.fake.set_env(FAKE_LLAMA_REQUESTS=str(self.fake.logs / "requests.txt"), **values)

    def requests(self) -> list[str]:
        """Return the PDF paths the fake server received, in order."""
        assert self.fake is not None
        path = self.fake.logs / "requests.txt"
        if not path.exists():
            return []
        return [
            json.loads(line)["messages"][0]["content"]
            for line in path.read_text(encoding="utf-8").splitlines()
        ]


def _manifest(name: str, runtime: FakeRuntime | None, build: int) -> str:
    head = f'[project]\nname = "omrs-ocr-{name}"\nversion = "0"\n'
    if runtime is None:
        return head + "\n[tool.omrs-ocr]\nrequires-acceptance = false\n"
    digest = hashlib.sha256(runtime.model.read_bytes()).hexdigest()
    return (
        head
        + "\n[tool.omrs-ocr.runtime]\n"
        + 'program = "bin/llama-server"\n'
        + f"build = {build}\n"
        + 'flags = ["-np", "1"]\n'
        + '\n[[tool.omrs-ocr.runtime.files]]\nflag = "-m"\n'
        + 'path = "models/q.gguf"\n'
        + f'sha256 = "{digest}"\n'
    )


def make_engine(
    workers_dir: Path,
    name: str,
    *,
    runtime: bool = True,
    mode: str = "echo",
    backend_id: str | None = None,
    build: int = BUILD,
    **fake_env: object,
) -> TestEngine:
    """Create ``<workers_dir>/engines/<name>`` and return it.

    Args:
        workers_dir: The workers directory.
        name: The engine folder name.
        runtime: Declare a runtime that points at a fake ``llama-server``.
        mode: The worker mode (``echo`` or ``crash``).
        backend_id: The fingerprint ``backend_id``; the folder name by default.
        build: The declared build.
        **fake_env: Extra ``FAKE_LLAMA_*`` values for the fake server.
    """
    folder = workers_dir / "engines" / name
    python = folder / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    launcher = (
        f'#!/bin/sh\nexec "{sys.executable}" "{WORKER}" '
        f'--mode {mode} --backend-id {backend_id or name.replace("-", "_")} "$@"\n'
    )
    python.write_text(launcher, encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    fake = FakeRuntime(folder / ".model-cache") if runtime else None
    if fake is not None:
        fake.set_env(FAKE_LLAMA_REQUESTS=str(fake.logs / "requests.txt"), **fake_env)
    (folder / "pyproject.toml").write_text(_manifest(name, fake, build), encoding="utf-8")
    return TestEngine(name=name, folder=folder, fake=fake)


def clean_environ() -> dict[str, str]:
    """Return the process environment without the cache and URL variables."""
    drop = {"OMRS_OCR_MODEL_CACHE", "OMRS_OCR_RUNTIME_URL"}
    return {k: v for k, v in os.environ.items() if k not in drop}


class OcrRuntimeHarness:
    """A workers folder, a runtime manager and the pools built on them."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.workers = tmp_path / "workers"
        self.engines: list[TestEngine] = []
        self.pools: list[OcrClientPool] = []
        self.state = tmp_path / "state"
        self.manager = RuntimeManager(self.state, environ=clean_environ(), exit_hook=False)
        reset_ocr_fingerprint_cache()

    def engine(self, name: str, **kwargs: Any) -> TestEngine:
        """Create one engine folder under the workers folder."""
        engine = make_engine(self.workers, name, **kwargs)
        self.engines.append(engine)
        return engine

    def pool(self, *, with_manager: bool = True) -> OcrClientPool:
        """Return a pool on the real capability probe, with or without the manager."""
        pool = OcrClientPool(
            probe=probe_ocr_worker, runtime_manager=self.manager if with_manager else None
        )
        self.pools.append(pool)
        return pool

    def settings(
        self, effective_settings: Any, primary: str, fallback: str = "", **overrides: Any
    ) -> Any:
        """Return settings that route to *primary* and *fallback*."""
        base = effective_settings(
            extraction_mode="disabled",
            pdf_reader="pypdf",
            ocr_fallback_enabled=True,
            ocr_workers_dir=str(self.workers),
            ocr_engine_primary=primary,
            ocr_engine_fallback=fallback,
            ocr_worker_request_timeout=20.0,
        )
        return base.model_copy(update=overrides) if overrides else base

    def pdf(self, name: str) -> str:
        """Create a small PDF file and return its path."""
        path = self.tmp_path / name
        path.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return str(path)

    def cleanup(self) -> None:
        """Close pools and the manager, then kill every fake server left."""
        for pool in self.pools:
            pool.close()
        self.manager.close()
        for engine in self.engines:
            if engine.fake is not None:
                engine.fake.kill_all()
