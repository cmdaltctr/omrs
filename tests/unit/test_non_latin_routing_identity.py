"""Non-Latin routing in the source index identity (change non-latin-script-routing, task 2.4).

With a mode other than ``off`` a PDF source's ``parser`` block holds
``non_latin_routing: {mode, detector_version}``. With ``off`` the block is
absent, so the digest equals the one pinned before this change. A source that
is not a PDF never changes. ``pages_non_latin`` is a diagnostic count: it is in
the central embedding exclusion set, and the identity's excluded-key list leaves
it out, because the block already records the setting that stamps it.
"""

from __future__ import annotations

from typing import Any

import pytest
from llama_index.core.schema import MetadataMode, TextNode
from tests.unit.test_index_identity_baseline import _MD_DIGEST_BEFORE_REVISION
from tests.unit.test_pdf_reader_identity import CODE_DEFAULT_PDF, digest

from omrs.core.ingestion import embed_exclusions, source_state
from omrs.core.ingestion.ocr_identity import non_latin_routing_payload
from omrs.core.ingestion.source_state import stamp_source_lineage
from omrs.core.settings import EffectiveSettings, EmbeddingBlock, MetadataBlock
from omrs.integrations.pdf import page_routing, script_routing

MODES = ("detect", "always")


@pytest.fixture(autouse=True)
def _unresolved_local_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hash with the local OCR model unresolved: the real probe depends on the host runtime."""
    page_routing.reset_local_model_resolution()
    monkeypatch.setattr(
        page_routing, "_probe_local_model_identity", lambda settings, backend="x": None
    )


def _settings(**overrides: Any) -> EffectiveSettings:
    return EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        embedding=EmbeddingBlock(tokenizer_model="", tokenizer_revision=""),
        **overrides,
    )


def test_off_adds_no_block() -> None:
    assert non_latin_routing_payload(_settings()) == {}
    assert non_latin_routing_payload(_settings(ocr_non_latin_routing="off")) == {}


@pytest.mark.parametrize("mode", MODES)
def test_a_mode_adds_the_mode_and_the_detector_version(mode: str) -> None:
    assert non_latin_routing_payload(_settings(ocr_non_latin_routing=mode)) == {
        "non_latin_routing": {
            "mode": mode,
            "detector_version": script_routing.SCRIPT_DETECTOR_VERSION,
        }
    }


def test_the_default_install_keeps_its_pinned_pdf_digest() -> None:
    assert digest() == CODE_DEFAULT_PDF
    assert digest(ocr_non_latin_routing="off") == CODE_DEFAULT_PDF


@pytest.mark.parametrize("mode", MODES)
def test_turning_the_setting_on_moves_the_pdf_digest(mode: str) -> None:
    assert digest(ocr_non_latin_routing=mode) != CODE_DEFAULT_PDF


def test_each_mode_has_its_own_digest() -> None:
    assert digest(ocr_non_latin_routing="detect") != digest(ocr_non_latin_routing="always")


def test_a_detector_version_bump_moves_the_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    before = digest(ocr_non_latin_routing="detect")
    monkeypatch.setattr(script_routing, "SCRIPT_DETECTOR_VERSION", 2)
    assert digest(ocr_non_latin_routing="detect") != before


def test_the_detector_version_does_not_move_an_off_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script_routing, "SCRIPT_DETECTOR_VERSION", 2)
    assert digest(ocr_non_latin_routing="off") == CODE_DEFAULT_PDF


@pytest.mark.parametrize("mode", MODES)
def test_a_source_that_is_not_a_pdf_keeps_its_digest(mode: str) -> None:
    assert digest("text/plain", ocr_non_latin_routing=mode) == digest("text/plain")


def test_a_markdown_source_keeps_its_pinned_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from omrs.core.ingestion.backends import orchestrator

    settings = _settings(ocr_non_latin_routing="always")
    from pathlib import Path

    path = Path("notes.md")
    identity = source_state.build_index_identity(
        settings,
        content_type="text/markdown",
        chunk_size=512,
        chunk_overlap=100,
        text_format=orchestrator.resolve_declared_text_format(path, settings=settings),
        pdf_reader_revision=orchestrator.resolve_pdf_reader_revision(path, settings=settings),
        embed_model=SimpleNamespace(model_name="pinned-embedder"),
    )
    assert identity == _MD_DIGEST_BEFORE_REVISION


def test_the_count_key_is_in_the_central_exclusion_set() -> None:
    assert script_routing.PAGES_NON_LATIN_KEY in embed_exclusions.EXCLUDED_EMBED_METADATA_KEYS


def test_the_count_key_never_reaches_the_embedding_text() -> None:
    node = TextNode(text="Page text.", metadata={script_routing.PAGES_NON_LATIN_KEY: 3, "page": 1})
    stamp_source_lineage(
        [node],
        file_path="/fixtures/a.pdf",
        source_id="src-a",
        content_hash="a" * 64,
        index_identity="b" * 64,
        source_version="c" * 64,
        source_attempt="attempt-1",
    )
    assert node.metadata[script_routing.PAGES_NON_LATIN_KEY] == 3
    for mode in (MetadataMode.EMBED, MetadataMode.LLM):
        assert f"{script_routing.PAGES_NON_LATIN_KEY}:" not in node.get_content(metadata_mode=mode)


def test_the_identity_excluded_list_leaves_the_count_key_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding the key to the exclusion set must not move a default install's digest."""
    assert script_routing.PAGES_NON_LATIN_KEY in embed_exclusions.IDENTITY_UNLISTED_KEYS
    with_key = digest()
    monkeypatch.setattr(
        source_state,
        "EXCLUDED_EMBED_METADATA_KEYS",
        tuple(
            key
            for key in source_state.EXCLUDED_EMBED_METADATA_KEYS
            if key != script_routing.PAGES_NON_LATIN_KEY
        ),
    )
    assert digest() == with_key
