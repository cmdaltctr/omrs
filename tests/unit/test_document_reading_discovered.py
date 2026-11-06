"""Discovered reading parts appear in the Document reading lists (change local-ocr-backends).

A backend or PDF reader that an installed package adds through an entry point is
accepted by the rules, so ``GET /v1/settings/document-reading`` must offer it in
the Add lists. Built-in parts come first. No package is installed: a fake
distribution stands in (``test_part_discovery_support``).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tests.unit.test_part_discovery_support import (
    READER_DESCRIPTOR,
    backend_distribution,
    fake_parts_builder,
    run_discovery,
)

from omrs.config import Settings
from omrs.config.settings_file import read_settings_file
from omrs.core import reading_parts
from omrs.integrations.pdf.local_ocr import registry as backend_registry
from omrs.transports.api.document_reading import build_document_reading, reset_reader_in_use
from omrs.transports.api.restart_snapshot import capture

BUILT_IN = [part.name for part in reading_parts.LOCAL_OCR_BACKENDS if part.min_confidence]


@pytest.fixture
def fake_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Yield the fake-distribution builder of ``test_part_discovery_support``."""
    yield from fake_parts_builder(tmp_path, monkeypatch)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Return a launch state that reads a temporary, empty config folder."""
    folder = tmp_path / "omrs-config"
    folder.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(folder))
    empty_env = tmp_path / "none.env"
    empty_env.write_text("", encoding="utf-8")
    reset_reader_in_use()
    file = read_settings_file(folder)
    yield SimpleNamespace(
        launch_settings=Settings(_env_file=empty_env),
        snapshot=capture(file),
        read_file=lambda: read_settings_file(folder),
    )
    reset_reader_in_use()


def test_a_discovered_backend_is_offered_after_the_built_in_ones(fake_parts, state) -> None:
    backend_distribution(fake_parts)
    run_discovery()

    names = [option["name"] for option in build_document_reading(state)["local_ocr_backends"]]

    assert names == [*BUILT_IN, "fake-ocr"]


def test_a_discovered_backend_carries_its_install_state(
    fake_parts, state, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend_distribution(fake_parts)
    run_discovery()
    monkeypatch.setattr(backend_registry.BACKENDS, "installed", lambda name: name == "fake-ocr")

    options = {o["name"]: o for o in build_document_reading(state)["local_ocr_backends"]}

    assert options["fake-ocr"] == {
        "name": "fake-ocr",
        "available": True,
        "reason": None,
        "default_cut": reading_parts.local_backend("fake-ocr").min_confidence,
    }
    assert options[BUILT_IN[0]] == {
        "name": BUILT_IN[0],
        "available": False,
        "reason": "Not installed.",
        "default_cut": reading_parts.local_backend(BUILT_IN[0]).min_confidence,
    }


def test_a_discovered_pdf_reader_is_offered_after_auto(fake_parts, state) -> None:
    fake_parts(
        "fakereader",
        {"omrs.pdf_readers": {"fake-reader": "{mod:desc}:READER"}},
        {"desc": READER_DESCRIPTOR.replace("{name}", "fake-reader").replace("{impl}", "x.y")},
    )
    run_discovery()

    names = [option["name"] for option in build_document_reading(state)["pdf_readers"]]

    assert names[0] == "auto"
    assert "fake-reader" in names


def test_no_discovered_part_leaves_only_the_built_in_backends(fake_parts, state) -> None:
    names = [option["name"] for option in build_document_reading(state)["local_ocr_backends"]]

    assert names == BUILT_IN


def test_the_read_step_names_a_discovered_backend_that_is_not_installed(
    fake_parts, state, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs.engine_lifecycle import local_backend_option_set

    backend_distribution(fake_parts)
    run_discovery()
    monkeypatch.setattr(backend_registry.BACKENDS, "installed", lambda name: name != "fake-ocr")

    options = local_backend_option_set(state.launch_settings)

    assert "fake-ocr" in options.unavailable
    assert "not installed" in options.unavailable["fake-ocr"]
