"""OCR routes get their runtime lease from the process's one runtime manager (D1, D10).

The ingest path (``capabilities.build_ocr_routes``, which
``core/ingestion/pipeline.py`` calls) and the Engine's OCR pool
(``EnginePipelines.ocr_pool``) both take the manager from ``compose``, so
Chat, embeddings and OCR leases come from one instance per process.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.ocr_worker.runtime_engine import TestEngine, make_engine

from omrs.integrations.llamacpp_runtime import process

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")


@pytest.fixture
def engines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[list[TestEngine]]:
    from omrs import compose_runtimes
    from omrs.capabilities import reset_ocr_fingerprint_cache

    for name in ("OMRS_OCR_MODEL_CACHE", "OMRS_OCR_RUNTIME_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(process, "HEALTH_POLL_SECONDS", 0.05)
    reset_ocr_fingerprint_cache()
    made: list[TestEngine] = []
    try:
        yield made
    finally:
        compose_runtimes.reset()
        for engine in made:
            if engine.fake is not None:
                engine.fake.kill_all()


def _settings(effective_settings: Any, workers: Path, **overrides: Any) -> Any:
    return effective_settings(
        extraction_mode="disabled",
        pdf_reader="pypdf",
        ocr_fallback_enabled=True,
        ocr_workers_dir=str(workers),
        ocr_engine_primary="engine-a",
        ocr_engine_fallback="",
        ocr_worker_request_timeout=20.0,
        **overrides,
    )


def _pdf(tmp_path: Path) -> str:
    path = tmp_path / "a.pdf"
    path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    return str(path)


def test_the_ingest_routes_get_a_working_lease_from_the_process_manager(
    engines: list[TestEngine], effective_settings: Any, tmp_path: Path
) -> None:
    from omrs import compose_runtimes
    from omrs.capabilities import build_ocr_routes

    engine = make_engine(tmp_path / "workers", "engine-a")
    engines.append(engine)
    routes = build_ocr_routes(_settings(effective_settings, tmp_path / "workers"))
    try:
        result = routes.select().parse(_pdf(tmp_path), timeout=20)
        lease = routes.primary.lease
        assert lease is not None and lease.manager is compose_runtimes.runtime_manager()
        assert f"url={lease.base_url}\n" in result.markdown
        assert len(engine.fake.starts()) == 1
        folder = compose_runtimes.runtime_manager().root / "runtimes" / "ocr-engine-a"
        assert (folder / "server.json").exists()
    finally:
        routes.close()


def test_the_engine_ocr_pool_uses_the_process_manager(
    engines: list[TestEngine], effective_settings: Any, tmp_path: Path
) -> None:
    from omrs import compose_runtimes
    from omrs.compose_pipelines import EnginePipelines

    engines.append(make_engine(tmp_path / "workers", "engine-a"))
    pipelines = EnginePipelines()
    try:
        routes = pipelines.ocr_pool().routes(_settings(effective_settings, tmp_path / "workers"))
        assert routes.primary.lease is not None
        assert routes.primary.lease.manager is compose_runtimes.runtime_manager()
    finally:
        pipelines.release()


def test_the_runtime_url_reaches_the_effective_settings_and_makes_the_route_external(
    engines: list[TestEngine], effective_settings: Any, tmp_path: Path
) -> None:
    from omrs import compose
    from omrs.capabilities import build_ocr_routes
    from omrs.config import Settings

    url = "http://127.0.0.1:9/"
    effective = compose.settings_to_effective(Settings(_env_file=None, ocr_runtime_url=url))
    assert effective.ocr_runtime_url == url

    engines.append(make_engine(tmp_path / "workers", "engine-a"))
    settings = _settings(effective_settings, tmp_path / "workers", ocr_runtime_url=url)
    routes = build_ocr_routes(settings)
    try:
        assert routes.primary.lease is not None
        spec = routes.primary.lease.spec
        assert (spec.mode, spec.url_base) == ("external", url)
    finally:
        routes.close()
