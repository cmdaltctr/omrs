"""The reading-list rules accept discovered parts (change local-ocr-backends, design D11).

Bug fixed here (likelihood 6 x impact 4): a discovered local OCR backend or PDF
reader written in ``omrs.jsonc``, on the Settings page or in a Read document
step was refused, because the rules in ``config/rules.py`` knew only the
built-in names. With nothing discovered, every message is as before.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from omrs.config import rules
from omrs.config.settings_file import check_setting
from omrs.core import reading_parts

_BACKEND = reading_parts.LocalOcrBackendDescriptor(
    name="fake-ocr",
    import_path="omrs_fake_ocr:BACKEND",
    label="Fake OCR",
    help_key="local_ocr_backend.fake-ocr",
    min_confidence=0.8,
    calibrated_by="00-fake",
    producer="fake_ocr",
    source="omrs-fake",
)
_READER = reading_parts.PdfReaderDescriptor(
    name="fake_reader",
    import_path="omrs_fake_reader:Reader",
    label="fake-reader",
    help_key="pdf_reader.fake_reader",
    text_format="plain",
    page_provenance=True,
    source="omrs-fake",
)


@pytest.fixture
def installed() -> Iterator[None]:
    reading_parts.install_discovered((_BACKEND, _READER))
    yield
    reading_parts.reset_discovered()


@pytest.mark.usefixtures("installed")
def test_a_file_value_naming_a_discovered_backend_is_accepted() -> None:
    value, rule = check_setting("ocr_local_backends", ["fake-ocr", "pp-ocrv6-small"])

    assert rule is None
    assert value == ("fake-ocr", "pp-ocrv6-small")


@pytest.mark.usefixtures("installed")
def test_a_discovered_backend_passes_the_page_and_step_rule() -> None:
    assert rules.document_reading_problem("ocr_local_backends", ["fake-ocr"]) is None


@pytest.mark.usefixtures("installed")
def test_a_discovered_reader_passes_the_reader_list_rule() -> None:
    assert rules.reading_list_problem("pdf_readers", ["fake_reader", "pypdf"]) is None
    assert rules.document_reading_problem("pdf_readers", ["fake_reader"]) is None
    assert check_setting("pdf_readers", ["fake_reader"])[1] is None


@pytest.mark.usefixtures("installed")
def test_a_discovered_reader_rule_names_it_among_the_accepted_values() -> None:
    rule = rules.reading_list_problem("pdf_readers", ["nope"])

    assert rule is not None and "fake_reader" in rule and "nope" not in rule


def test_without_discovery_the_messages_are_as_before() -> None:
    assert rules.reading_list_problem("pdf_readers", ["fake_reader"]) == rules.READER_LIST_RULE
    assert rules.READER_LIST_RULE == (
        "The value must be one of: liteparse, pdf_inspector, pypdfium2, pypdf."
    )
    assert check_setting("ocr_local_backends", ["fake-ocr"])[1] == (
        "Each name must be a local OCR backend. Accepted values: pp-ocrv6-small."
    )
    assert rules.document_reading_problem("ocr_local_backends", ["fake-ocr"]) == (
        "Each name must be a local OCR backend. Accepted values: pp-ocrv6-small."
    )
