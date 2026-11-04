"""Compose runs reading-part discovery before settings resolve (task 5.2, design D11).

Spec reading-parts: "Discovered backend can be listed" and "Nothing
discovered". Every test uses a fake distribution; no package is installed.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_part_discovery_support import (
    READER_DESCRIPTOR,
    backend_distribution,
    fake_parts_builder,
)

from omrs import compose
from omrs.config import rules
from omrs.core import reading_parts
from omrs.integrations import part_registry
from omrs.integrations.pdf.local_ocr import chain


@pytest.fixture
def fake_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Yield the fake-distribution builder of ``test_part_discovery_support``."""
    yield from fake_parts_builder(tmp_path, monkeypatch)


@pytest.fixture
def fresh_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the next ``get_settings()`` build ``Settings`` again."""
    import omrs.config as config

    monkeypatch.setattr(config, "_settings", None)


def test_compose_runs_discovery_before_settings_resolve(fake_parts, monkeypatch) -> None:
    import omrs.config as config

    order: list[str] = []
    real_discover = part_registry.discover_parts
    real_settings = config.get_settings

    def discover(**kwargs: Any) -> Any:
        order.append("discover")
        return real_discover(**kwargs)

    def settings() -> Any:
        order.append("settings")
        return real_settings()

    monkeypatch.setattr(part_registry, "discover_parts", discover)
    monkeypatch.setattr(compose, "_config_get_settings", settings)
    monkeypatch.setattr(config, "_settings", None)

    compose.get_settings()
    compose.get_settings()

    assert order[:2] == ["discover", "settings"]


def test_a_discovered_backend_can_be_listed_and_is_tried_first(
    fake_parts, fresh_settings, monkeypatch, tmp_path: Path
) -> None:
    dist = backend_distribution(fake_parts)
    monkeypatch.setenv("OCR_LOCAL_BACKENDS", "fake-ocr,pp-ocrv6-small")

    settings = compose.get_settings()
    effective = compose.settings_to_effective(settings)

    assert effective.ocr_local_backends == ("fake-ocr", "pp-ocrv6-small")
    pages = chain.read_local_pages(tmp_path / "doc.pdf", [1, 2], settings=effective, post_checks=())
    implementation = __import__(dist.module("impl"))
    assert implementation.CALLS == [[1, 2]]
    assert [page.producer for page in pages] == ["fake_ocr", "fake_ocr"]
    assert [page.escalates for page in pages] == [False, False]


def test_a_discovered_backend_enters_the_identity_without_error(
    fake_parts, fresh_settings, monkeypatch
) -> None:
    from types import SimpleNamespace

    from omrs.core.ingestion.source_state import build_index_identity

    backend_distribution(fake_parts)
    monkeypatch.setenv("OCR_LOCAL_BACKENDS", "fake-ocr,pp-ocrv6-small")
    effective = compose.settings_to_effective(compose.get_settings())

    digest = build_index_identity(
        effective,
        content_type="application/pdf",
        chunk_size=512,
        chunk_overlap=100,
        pdf_reader_revision=2,
        embed_model=SimpleNamespace(model_name="m"),
    )

    assert len(digest) == 64


def test_an_undiscovered_backend_is_still_refused(fake_parts, fresh_settings, monkeypatch) -> None:
    monkeypatch.setenv("OCR_LOCAL_BACKENDS", "fake-ocr")

    with pytest.raises(ValueError, match="OCR_LOCAL_BACKENDS='fake-ocr' is not valid"):
        compose.get_settings()


def test_a_discovered_reader_can_be_listed_in_the_environment(
    fake_parts, fresh_settings, monkeypatch
) -> None:
    fake_parts(
        "fakereader",
        {"omrs.pdf_readers": {"fake-reader": "{mod:desc}:READER"}},
        {"desc": READER_DESCRIPTOR.replace("{name}", "fake-reader").replace("{impl}", "x.y")},
    )
    monkeypatch.setenv("PDF_READERS", "fake-reader,pypdf")

    effective = compose.settings_to_effective(compose.get_settings())

    assert effective.pdf_readers == ("fake-reader", "pypdf")


def _startup(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[str], str]:
    """Start twice (a good and a bad backend list); return the messages and the refusal."""
    import omrs.config as config

    caplog.clear()
    refusal = ""
    with caplog.at_level(logging.DEBUG):
        for backends in ("pp-ocrv6-small", "bogus"):
            monkeypatch.setattr(config, "_settings", None)
            monkeypatch.setenv("OCR_LOCAL_BACKENDS", backends)
            try:
                compose.settings_to_effective(compose.get_settings())
            except ValueError as exc:
                refusal = str(exc)
    return [record.getMessage() for record in caplog.records], refusal


def test_nothing_discovered_keeps_names_and_messages(
    fake_parts, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    """With no part discovered, start-up says what it said before discovery existed."""
    monkeypatch.setattr(part_registry, "entry_points", lambda **_: ())
    names_before = (rules.KNOWN_READER_NAMES, reading_parts.names(reading_parts.PAGE_RULES))
    with monkeypatch.context() as before_change:
        before_change.setattr(compose, "discover_reading_parts", lambda: (), raising=False)
        before = _startup(caplog, monkeypatch)

    after = _startup(caplog, monkeypatch)

    assert part_registry.discovered_parts() == ()
    assert after == before
    assert "Accepted values: pp-ocrv6-small, indra." in after[1]
    assert (rules.KNOWN_READER_NAMES, reading_parts.names(reading_parts.PAGE_RULES)) == (
        names_before
    )
