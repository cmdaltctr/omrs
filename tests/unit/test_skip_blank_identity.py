"""The skip-blank switch in the source index identity (change page-routing-panel, task 2.1).

Switch on (the default), nothing enters the identity, so every pinned digest
stays the same. Switch off, the PDF ``parser`` block gains
``skip_blank_pages: false`` (design D4), so PDF sources re-index and every
other source keeps its digest.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_index_identity_baseline import (
    _MD_DIGEST_BEFORE_REVISION,
    _RecordingJSON,
    _source_identity,
)
from tests.unit.test_pdf_reader_identity import CODE_DEFAULT_PDF, digest

from omrs.core.ingestion import source_state
from omrs.core.ingestion.ocr_identity import ocr_routing_payload
from omrs.core.ingestion.pipeline import ingest_path_async
from omrs.core.ingestion.reader_identity import pdf_parser_payload
from omrs.core.settings import EffectiveSettings
from omrs.integrations.pdf import page_routing

MARKDOWN = "text/markdown"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "smoke_text.pdf"
#: The PDF digest with the switch off: ``CODE_DEFAULT_PDF`` plus
#: ``parser.skip_blank_pages: false``. Pinned on 7 November 2026 (page-routing-panel).
SWITCH_OFF_PDF = "94310ff8cf85eb7ca5138586b8a0c31b918bff9574a126d63a883db131c24ff4"


@pytest.fixture(autouse=True)
def _unresolved_local_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hash with the local OCR model unresolved: the real probe depends on the host runtime."""
    page_routing.reset_local_model_resolution()
    monkeypatch.setattr(
        page_routing, "_probe_local_model_identity", lambda settings, backend="x": None
    )


# ── Switch on: nothing moves ─────────────────────────────────────────────


def test_switch_on_adds_no_parser_entry() -> None:
    assert "skip_blank_pages" not in pdf_parser_payload(EffectiveSettings())
    on = EffectiveSettings(ocr_skip_blank_pages=True)
    assert "skip_blank_pages" not in pdf_parser_payload(on)


def test_switch_on_keeps_every_pinned_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    assert digest() == CODE_DEFAULT_PDF
    assert digest(ocr_skip_blank_pages=True) == CODE_DEFAULT_PDF
    _, markdown = _source_identity(monkeypatch, "notes.md")
    assert markdown == _MD_DIGEST_BEFORE_REVISION


# ── Switch off: the PDF parser block only ────────────────────────────────


def test_switch_off_adds_the_parser_entry() -> None:
    off = EffectiveSettings(ocr_skip_blank_pages=False)
    assert pdf_parser_payload(off)["skip_blank_pages"] is False


def test_switch_off_leaves_the_routing_block_alone() -> None:
    off = EffectiveSettings(ocr_skip_blank_pages=False)
    assert ocr_routing_payload(off) == ocr_routing_payload(EffectiveSettings())


def test_switch_off_moves_the_pdf_digest_to_its_pin() -> None:
    off = digest(ocr_skip_blank_pages=False)
    assert off != CODE_DEFAULT_PDF
    assert off == SWITCH_OFF_PDF


def test_switch_off_keeps_the_markdown_digest() -> None:
    assert digest(MARKDOWN, ocr_skip_blank_pages=False) == digest(MARKDOWN)


def test_the_recorded_pdf_payload_holds_the_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """The entry reaches the hashed payload, not only the builder."""
    recorder = _RecordingJSON()
    monkeypatch.setattr(source_state, "json", recorder)
    digest(ocr_skip_blank_pages=False)
    assert recorder.payloads[-1]["parser"]["skip_blank_pages"] is False


# ── Explicit ingest: the PDF source only ─────────────────────────────────


@pytest.fixture
def mixed(tmp_path: Path) -> Path:
    folder = tmp_path / "mixed"
    folder.mkdir()
    (folder / "smoke_text.pdf").write_bytes(FIXTURE.read_bytes())
    (folder / "notes.md").write_text("# Notes\n\nA short note about blank pages.\n")
    return folder


async def _ingest(folder: Path, settings: Any, collection: str) -> dict[str, str]:
    result = await ingest_path_async(
        str(folder), effective_settings=settings, collection_name=collection
    )
    return {Path(d["file"]).name: d["status"] for d in result["file_details"]}


@pytest.mark.asyncio
async def test_turning_the_switch_off_reindexes_the_pdf_source_only(
    mixed: Path, effective_settings: Any
) -> None:
    on = effective_settings(pdf_reader="pypdf")
    off = effective_settings(pdf_reader="pypdf", ocr_skip_blank_pages=False)

    first = await _ingest(mixed, on, "skip_blank_mixed")
    second = await _ingest(mixed, off, "skip_blank_mixed")
    third = await _ingest(mixed, off, "skip_blank_mixed")

    assert first == {"smoke_text.pdf": "indexed", "notes.md": "indexed"}
    assert second == {"smoke_text.pdf": "indexed", "notes.md": "skipped_unchanged"}
    assert set(third.values()) == {"skipped_unchanged"}
