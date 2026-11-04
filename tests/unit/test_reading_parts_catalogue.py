"""Extras catalogue rows and in-use checks of reading parts come from descriptors.

Change local-ocr-backends, task 6.7, design D15. A reading part with an extra
gets a catalogue row and an in-use check without an edit in
``integrations_catalogue.py`` or ``uninstall_plan.py``. Today's rows stay as
they were: ``test_reading_parts_list_pins.py`` pins them.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("fastapi")

from omrs.core import reading_parts
from omrs.core.settings import EffectiveSettings
from omrs.transports.api import integrations_catalogue, uninstall_plan

_FAKE_BACKEND = reading_parts.LocalOcrBackendDescriptor(
    name="fake-ocr",
    import_path="omrs_fake_ocr_backend:BACKEND",
    label="Fake OCR",
    help_key="local_ocr_backend.fake-ocr",
    extra="local-ocr-fake",
    probe_module="omrs_fake_ocr_backend_missing",
    min_confidence=0.8,
    calibrated_by="00-fake-calibration",
    producer="fake_ocr",
)
_FAKE_READER = reading_parts.PdfReaderDescriptor(
    name="fake_reader",
    import_path="omrs_fake_reader:Reader",
    label="fake-reader",
    help_key="pdf_reader.fake_reader",
    extra="pdf-fake",
    probe_module="omrs_fake_reader_missing",
    text_format="markdown",
    page_provenance=True,
)


@pytest.fixture
def fake_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Add one fake backend and one fake reader, each with its own extra."""
    backends = (*reading_parts.LOCAL_OCR_BACKENDS, _FAKE_BACKEND)
    monkeypatch.setattr(reading_parts, "LOCAL_OCR_BACKENDS", backends)
    monkeypatch.setattr(reading_parts, "PDF_READERS", (*reading_parts.PDF_READERS, _FAKE_READER))


def _row(extra: str) -> integrations_catalogue.Integration:
    rows = [item for item in integrations_catalogue.build_catalogue() if item.extra == extra]
    assert len(rows) == 1, extra
    return rows[0]


def _fields(rows: tuple[integrations_catalogue.Integration, ...]) -> list[tuple[Any, ...]]:
    """Return every field but the probe, which is a new function on each build."""
    return [(row.id, row.name, row.purpose, row.extra, row.caution) for row in rows]


def test_the_built_catalogue_equals_the_module_catalogue() -> None:
    built = integrations_catalogue.build_catalogue()
    assert _fields(built) == _fields(integrations_catalogue.CATALOGUE)


@pytest.mark.usefixtures("fake_parts")
def test_a_fake_backend_with_an_extra_gets_a_catalogue_row() -> None:
    row = _row("local-ocr-fake")

    assert (row.id, row.name, row.extra, row.caution) == (
        "local-ocr-fake",
        "Local OCR backend: Fake OCR",
        "local-ocr-fake",
        None,
    )
    assert row.purpose.endswith(".")
    assert row.probe(None) == integrations_catalogue.NOT_INSTALLED


@pytest.mark.usefixtures("fake_parts")
def test_a_fake_reader_with_an_extra_gets_a_reader_row_beside_the_others() -> None:
    row = _row("pdf-fake")

    assert row.name == "PDF reader: fake-reader"
    assert row.purpose == "Reads PDF files as Markdown with the fake-reader library."
    ids = [item.id for item in integrations_catalogue.build_catalogue()]
    assert ids.index("pdf-fake") < ids.index("community-leiden")


@pytest.mark.usefixtures("fake_parts")
def test_a_listed_fake_backend_keeps_its_extra_in_use() -> None:
    listed = EffectiveSettings.model_validate({"ocr_local_backends": ["pp-ocrv6-small"]})
    saved: dict[str, Any] = {"ocr_local_backends": ["fake-ocr", "pp-ocrv6-small"]}

    assert uninstall_plan.in_use_setting("local-ocr-fake", listed, saved) == "ocr_local_backends"
    assert uninstall_plan.in_use_setting("local-ocr-fake", listed, {}) is None


@pytest.mark.usefixtures("fake_parts")
def test_a_listed_fake_reader_keeps_its_extra_in_use() -> None:
    saved: dict[str, Any] = {"pdf_readers": ["pypdf", "fake_reader"]}

    assert uninstall_plan.in_use_setting("pdf-fake", None, saved) == "pdf_readers"
    assert uninstall_plan.part_in_use_rows()["pdf-fake"] == (("pdf_reader", "fake_reader"),)
    assert uninstall_plan.part_in_use_rows()["local-ocr-fake"] == ()


def test_each_reader_extra_has_its_in_use_row_from_the_descriptor() -> None:
    expected = {
        part.extra: (("pdf_reader", part.name),) for part in reading_parts.PDF_READERS if part.extra
    }
    assert expected, "a built-in reader should have an extra"
    assert {extra: uninstall_plan.IN_USE[extra] for extra in expected} == expected
