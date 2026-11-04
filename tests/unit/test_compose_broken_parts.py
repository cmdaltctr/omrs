"""A discovered part that fails to load never stops start-up (review of PR #168, finding 4).

Spec reading-parts: "A discovered part that fails to load SHALL be skipped with
one warning and shown broken with the reason". A setting that names such a part
is accepted with one warning, and the part is off: the local tier, the page-rule
pipeline and the reader chain skip it. A name that nothing declares is still
refused. Every test uses a fake distribution; no package is installed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_part_discovery_support import fake_parts_builder

from omrs import compose
from omrs.core import reading_parts
from omrs.integrations import part_registry
from omrs.integrations.pdf import registry as reader_registry
from omrs.integrations.pdf.local_ocr import chain
from omrs.integrations.pdf.local_ocr import registry as backend_registry
from omrs.integrations.pdf.local_ocr.base import BackendPage
from omrs.integrations.pdf.page_rules import registry as rule_registry
from omrs.integrations.pdf.page_rules.pipeline import run_rules

#: A descriptor module that broke, for example after a dependency upgrade.
BROKEN = "import a_module_that_is_gone\n"
PROBLEM = "ModuleNotFoundError: No module named 'a_module_that_is_gone'"


@pytest.fixture
def fake_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    yield from fake_parts_builder(tmp_path, monkeypatch)


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the next ``get_settings()`` build ``Settings`` again."""
    import omrs.config as config

    monkeypatch.setattr(config, "_settings", None)
    chain.reset_skip_warnings()


def _broken(build: Any, group: str, entry: str) -> None:
    build("acmebroken", {group: {entry: "{mod:desc}:PART"}}, {"desc": BROKEN})


def _start(caplog: pytest.LogCaptureFixture) -> Any:
    with caplog.at_level(logging.WARNING):
        return compose.settings_to_effective(compose.get_settings())


def _setting_warnings(caplog: pytest.LogCaptureFixture, name: str) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "omrs.compose_settings" and repr(name) in record.getMessage()
    ]


def test_a_broken_rule_named_in_the_options_is_accepted_and_off(
    fake_parts, monkeypatch, caplog
) -> None:
    _broken(fake_parts, "omrs.page_rules", "acme")
    monkeypatch.setenv("READING_PART_OPTIONS", json.dumps({"acme": {"enabled": True}}))

    effective = _start(caplog)

    assert effective.reading_part_options == {"acme": {"enabled": True}}
    (warning,) = _setting_warnings(caplog, "acme")
    assert PROBLEM in warning
    assert "acme" not in [name for name, _ in rule_registry.ordered()]
    plan = run_rules(Path("doc.pdf"), [], {1}, effective, None)
    assert [run.name for run in plan.runs] == ["blank", "maths", "non_latin"]
    assert [row.name for row in part_registry.discovered_parts()] == ["acme"]


def test_a_broken_backend_in_the_list_is_accepted_and_skipped(
    fake_parts, monkeypatch, caplog, tmp_path: Path
) -> None:
    _broken(fake_parts, "omrs.local_ocr_backends", "acme-ocr")
    monkeypatch.setenv("OCR_LOCAL_BACKENDS", "acme-ocr,pp-ocrv6-small")

    effective = _start(caplog)

    assert effective.ocr_local_backends == ("acme-ocr", "pp-ocrv6-small")
    (warning,) = _setting_warnings(caplog, "acme-ocr")
    assert PROBLEM in warning
    assert PROBLEM in (backend_registry.off_reason("acme-ocr") or "")

    class Good:
        def read_pages(self, file, pages, *, settings):
            return [BackendPage(p, "Good Latin text here", 0.99, "m@1") for p in pages]

    backend_registry.BACKENDS.cache["pp-ocrv6-small"] = Good()
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        pages = chain.read_local_pages(
            tmp_path / "doc.pdf", [1], settings=effective, post_checks=()
        )
    assert [(page.producer, page.escalates) for page in pages] == [("pdf_inspector_ocr", False)]
    assert caplog.records == []


def test_a_broken_reader_in_the_list_is_accepted_and_dropped(
    fake_parts, monkeypatch, caplog
) -> None:
    _broken(fake_parts, "omrs.pdf_readers", "acme-reader")
    monkeypatch.setenv("PDF_READERS", "acme-reader,pypdf")

    effective = _start(caplog)

    assert effective.pdf_readers == ("pypdf",)
    assert len(_setting_warnings(caplog, "acme-reader")) == 1
    assert PROBLEM in (reader_registry.READERS.off_reason("acme-reader") or "")


def test_a_name_that_nothing_declares_is_still_refused(fake_parts, monkeypatch) -> None:
    _broken(fake_parts, "omrs.page_rules", "acme")
    monkeypatch.setenv("READING_PART_OPTIONS", json.dumps({"other": {"enabled": True}}))

    with pytest.raises(ValueError, match="'other' is not a reading part"):
        compose.settings_to_effective(compose.get_settings())


def test_a_broken_entry_point_with_a_built_in_name_leaves_the_built_in_on(
    fake_parts, monkeypatch
) -> None:
    _broken(fake_parts, "omrs.pdf_readers", "pypdf")

    compose.settings_to_effective(compose.get_settings())

    assert reader_registry.READERS.off_reason("pypdf") is None
    assert reading_parts.broken() == {}
    assert [row.name for row in part_registry.discovered_parts()] == ["pypdf"]


def test_a_broken_backend_in_the_list_adds_nothing_to_the_identity(
    fake_parts, monkeypatch, caplog
) -> None:
    from omrs.core.ingestion.ocr_identity import local_backends_payload

    _broken(fake_parts, "omrs.local_ocr_backends", "acme-ocr")
    monkeypatch.setenv("OCR_LOCAL_BACKENDS", "acme-ocr,indra")

    payload = local_backends_payload(_start(caplog))

    assert [entry["name"] for entry in payload["local_ocr_backends"]["backends"]] == ["indra"]
