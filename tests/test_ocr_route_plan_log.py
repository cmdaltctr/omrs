"""The start-up OCR route line (integrations-show-runtime-components, follow-up to D5).

The Engine-owned pool starts workers on first use, so the line is built from
the engine folders alone: no worker process starts and nothing is probed.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.ocr_worker.runtime_engine import make_engine

from omrs.integrations.ocr_worker.routes import log_route_plan, reset_route_log

LOGGER = "omrs.integrations.ocr_worker.routes"


@pytest.fixture(autouse=True)
def _fresh_log() -> Iterator[None]:
    reset_route_log()
    yield
    reset_route_log()


def _provision(root: Path, name: str) -> None:
    python = root / "engines" / name / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")  # never run: the line only checks the file


def _lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("OCR routes:")]


def test_the_line_names_both_engines_once_without_starting_a_worker(
    tmp_path: Path, effective_settings: Any, caplog: pytest.LogCaptureFixture
) -> None:
    _provision(tmp_path, "paddleocr-vl")
    settings = effective_settings(ocr_fallback_enabled=True, ocr_workers_dir=str(tmp_path))

    with caplog.at_level(logging.INFO, logger=LOGGER):
        log_route_plan(settings)
        log_route_plan(settings)

    assert _lines(caplog) == [
        "OCR routes: primary=dots-mocr [not provisioned], fallback=paddleocr-vl [provisioned]"
    ]


def test_an_engine_with_a_runtime_is_provisioned_and_the_line_raises_no_manager_warning(
    tmp_path: Path,
    effective_settings: Any,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The start-up line has no runtime manager; it must not call the route unavailable."""
    for name in ("OMRS_OCR_MODEL_CACHE", "OMRS_OCR_RUNTIME_URL"):
        monkeypatch.delenv(name, raising=False)
    make_engine(tmp_path, "llama-engine")
    settings = effective_settings(
        ocr_fallback_enabled=True,
        ocr_workers_dir=str(tmp_path),
        ocr_engine_primary="llama-engine",
        ocr_engine_fallback="",
    )

    with caplog.at_level(logging.INFO, logger=LOGGER):
        log_route_plan(settings)

    assert _lines(caplog) == [
        "OCR routes: primary=llama-engine [provisioned], fallback=- [not provisioned]"
    ]
    assert not [r for r in caplog.records if "no runtime manager" in r.getMessage()]


def test_no_workers_folder_says_so(
    effective_settings: Any, caplog: pytest.LogCaptureFixture
) -> None:
    settings = effective_settings(ocr_fallback_enabled=True, ocr_workers_dir="")

    with caplog.at_level(logging.INFO, logger=LOGGER):
        log_route_plan(settings)

    assert _lines(caplog) == [
        "OCR routes: primary=dots-mocr [not provisioned], "
        "fallback=paddleocr-vl [not provisioned] (OCR workers folder not set)"
    ]


def test_ocr_off_logs_nothing(effective_settings: Any, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER):
        log_route_plan(effective_settings(ocr_fallback_enabled=False))

    assert _lines(caplog) == []


def test_build_engine_logs_the_line(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    from tests.test_compose import _EngineParts, _provider_base

    from omrs.compose import ProviderValues
    from omrs.compose_engine import build_engine

    base = _provider_base(tmp_path)
    object.__setattr__(base, "ocr_fallback_enabled", True)
    with _EngineParts(base), caplog.at_level(logging.INFO, logger=LOGGER):
        engine = build_engine(provider_source=lambda: ProviderValues())
    engine.close()

    assert len(_lines(caplog)) == 1
