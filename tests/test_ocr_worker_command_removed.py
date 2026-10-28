"""The explicit OCR worker command is gone (integrations-show-runtime-components, D7).

Routes resolve only from the workers folder and an engine name, so a step's
chosen engine always applies. A leftover variable fails start-up and names
its replacement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from omrs.config import Settings, check_legacy_env_vars
from omrs.core.settings import EffectiveSettings
from omrs.integrations.ocr_worker.routes import resolve_route_command

REMOVED = ("OCR_WORKER_COMMAND", "OCR_WORKER_ENV_DIR")


@pytest.mark.parametrize("name", REMOVED)
def test_a_leftover_variable_fails_and_names_the_replacement(name: str) -> None:
    with pytest.raises(ValueError) as refused:
        check_legacy_env_vars({name: "/old/worker"})

    message = str(refused.value)
    assert name in message
    assert "OCR_WORKERS_DIR" in message
    assert "OCR_ENGINE_PRIMARY" in message
    assert "/old/worker" not in message


@pytest.mark.parametrize("field", ["ocr_worker_command", "ocr_worker_env_dir"])
def test_neither_settings_model_has_the_field(field: str) -> None:
    assert field not in Settings.model_fields
    assert field not in EffectiveSettings.model_fields


def test_the_primary_engine_always_resolves_from_the_workers_folder(
    tmp_path: Path, effective_settings: Any
) -> None:
    python = tmp_path / "engines" / "paddleocr-vl" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    settings = effective_settings(ocr_workers_dir=str(tmp_path))
    object.__setattr__(settings, "ocr_worker_command", "/old/worker --serve")

    route = resolve_route_command("paddleocr-vl", settings)

    assert route.command[0] == str(python)
