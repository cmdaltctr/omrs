"""The router in the source index identity and the embedding exclusions (tasks 3.4 and 3.5).

With a router selected, a PDF source's ``parser`` block holds ``document_router``
with the recipe that decides the text: question, threshold, image flag,
character limit, the decision model's kind and model identity, and the rule
version. The router name, address, key and opt-in stay out, so a rename or a
key change does not reindex. With no router, or for a source that is not a
PDF, nothing changes and every pinned digest holds.

The settings maps arrive through ``model_copy(update=...)``, so the tests run
whether or not ``EffectiveSettings`` declares the router fields yet.
"""

from __future__ import annotations

from typing import Any

import pytest
from llama_index.core.schema import MetadataMode, TextNode
from tests.unit.test_pdf_reader_identity import CODE_DEFAULT_PDF

from omrs.core import reading_parts
from omrs.core.ingestion import embed_exclusions, source_state
from omrs.core.ingestion.ocr_identity import document_router_payload
from omrs.core.ingestion.reader_identity import pdf_parser_payload
from omrs.core.ingestion.source_state import stamp_source_lineage
from omrs.core.settings import EffectiveSettings, EmbeddingBlock, MetadataBlock

STAMP_KEYS = (
    "router_pages_judged",
    "router_pages_accepted",
    "router_pages_rejected",
    "router_pages_unjudged",
    "router_status",
)

LOCAL = {
    "kind": "llamacpp",
    "address": "http://127.0.0.1:8090",
    "model": "clef-flash-q8_0",
    "images": True,
    "key": None,
    "server": "external",
}
MANAGED = {
    **LOCAL,
    "server": "managed",
    "model_file": "~/models/clef-flash-q8_0.gguf",
    "projector_file": "~/models/mmproj.gguf",
    "model_sha256": "a" * 64,
    "projector_sha256": "b" * 64,
}
RECIPE = {
    "model": "clef",
    "question": "Does the text match the text written or printed on the page image?",
    "threshold": 0.172,
    "images": True,
    "max_chars": 2000,
    "send_off_machine": False,
}


def _base(**overrides: Any) -> EffectiveSettings:
    return EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        embedding=EmbeddingBlock(tokenizer_model="", tokenizer_revision=""),
        **overrides,
    )


def _with_router(
    name: str = "junk",
    recipe: dict[str, Any] | None = None,
    model: dict[str, Any] | None = None,
    *,
    model_name: str = "clef",
) -> EffectiveSettings:
    return _base().model_copy(
        update={
            "document_router": name,
            "document_routers": {name: {**(recipe or RECIPE), "model": model_name}},
            "decision_models": {model_name: dict(model or LOCAL)},
        }
    )


def _digest(settings: Any, content_type: str = "application/pdf") -> str:
    return source_state.build_index_identity(
        settings,
        content_type=content_type,
        chunk_size=512,
        chunk_overlap=100,
        pdf_reader_revision=2 if content_type == "application/pdf" else None,
    )


# ── The parser entry ─────────────────────────────────────────────────────


def test_no_router_adds_no_entry() -> None:
    assert document_router_payload(_base()) == {}
    for off in ("", "none"):
        assert (
            document_router_payload(_with_router().model_copy(update={"document_router": off}))
            == {}
        )


def test_an_unknown_router_name_adds_no_entry() -> None:
    settings = _with_router().model_copy(update={"document_router": "missing"})

    assert document_router_payload(settings) == {}


def test_a_selected_router_adds_its_recipe_and_model_identity() -> None:
    version = reading_parts.by_name(reading_parts.PAGE_RULES, "document_router").version

    assert document_router_payload(_with_router()) == {
        "document_router": {
            "question": RECIPE["question"],
            "threshold": 0.172,
            "images": True,
            "max_chars": 2000,
            "model": {"kind": "llamacpp", "model": "clef-flash-q8_0"},
            "version": version,
            "runnable": False,  # no judge hook here; see test_document_router_runnable
        }
    }


def test_a_managed_model_adds_its_file_hashes() -> None:
    entry = document_router_payload(_with_router(model=MANAGED))["document_router"]

    assert entry["model"] == {
        "kind": "llamacpp",
        "model": "clef-flash-q8_0",
        "model_sha256": "a" * 64,
        "projector_sha256": "b" * 64,
    }


def test_entries_given_as_objects_read_the_same_as_mappings() -> None:
    from types import SimpleNamespace

    settings = _base().model_copy(
        update={
            "document_router": "junk",
            "document_routers": {"junk": SimpleNamespace(**RECIPE)},
            "decision_models": {"clef": SimpleNamespace(**LOCAL)},
        }
    )

    assert document_router_payload(settings) == document_router_payload(_with_router())


def test_the_entry_reaches_the_pdf_parser_block() -> None:
    assert "document_router" in pdf_parser_payload(_with_router())
    assert "document_router" not in pdf_parser_payload(_base())


# ── Digests ──────────────────────────────────────────────────────────────


def test_the_default_digest_equals_the_pinned_value() -> None:
    assert _digest(_base()) == CODE_DEFAULT_PDF
    assert _digest(_base().model_copy(update={"document_router": ""})) == CODE_DEFAULT_PDF


def test_selecting_a_router_moves_the_pdf_digest() -> None:
    assert _digest(_with_router()) != CODE_DEFAULT_PDF


def test_renaming_a_router_leaves_the_digest() -> None:
    """Scenario "Renaming does not reindex"."""
    assert _digest(_with_router("junk")) == _digest(_with_router("handwriting"))
    assert _digest(_with_router(model_name="clef")) == _digest(_with_router(model_name="local"))


@pytest.mark.parametrize(
    "change",
    [
        {"send_off_machine": True},
    ],
)
def test_the_opt_in_does_not_enter_the_digest(change: dict[str, Any]) -> None:
    assert _digest(_with_router(recipe={**RECIPE, **change})) == _digest(_with_router())


@pytest.mark.parametrize(
    "change",
    [
        {"address": "https://api.example.invalid"},
        {"key": "env://ROUTER_KEY"},
        {"model_file": "~/elsewhere/clef.gguf"},
    ],
)
def test_where_the_model_lives_does_not_enter_the_digest(change: dict[str, Any]) -> None:
    assert _digest(_with_router(model={**LOCAL, **change})) == _digest(_with_router())


@pytest.mark.parametrize(
    "change",
    [
        {"threshold": 0.21},
        {"question": "Is this page readable?"},
        {"images": False},
        {"max_chars": 1000},
    ],
)
def test_a_recipe_change_moves_pdf_digests_only(change: dict[str, Any]) -> None:
    """Scenario "Threshold change reindexes PDF sources"."""
    changed = _with_router(recipe={**RECIPE, **change})

    assert _digest(changed) != _digest(_with_router())
    assert _digest(changed, "text/plain") == _digest(_with_router(), "text/plain")
    assert _digest(changed, "text/plain") == _digest(_base(), "text/plain")


@pytest.mark.parametrize(
    "change",
    [{"kind": "typesafe"}, {"model": "jev"}, {"server": "managed", "model_sha256": "c" * 64}],
)
def test_a_model_identity_change_moves_the_pdf_digest(change: dict[str, Any]) -> None:
    assert _digest(_with_router(model={**LOCAL, **change})) != _digest(_with_router())


def test_a_rule_version_bump_moves_the_pdf_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    before = _digest(_with_router())
    bumped = tuple(
        dataclasses.replace(rule, version=rule.version + 1)
        if rule.name == "document_router"
        else rule
        for rule in reading_parts.PAGE_RULES
    )
    monkeypatch.setattr(reading_parts, "PAGE_RULES", bumped)

    assert _digest(_with_router()) != before


# ── Stamp keys (task 3.4) ────────────────────────────────────────────────


def test_the_stamp_keys_are_excluded_from_embedding_and_unlisted_in_identity() -> None:
    assert [k for k in STAMP_KEYS if k not in embed_exclusions.EXCLUDED_EMBED_METADATA_KEYS] == []
    assert [k for k in STAMP_KEYS if k not in embed_exclusions.IDENTITY_UNLISTED_KEYS] == []


def test_the_stamp_keys_never_reach_the_embedding_text() -> None:
    stamped = dict(zip(STAMP_KEYS, (3, 2, 1, 0, "ok"), strict=True))
    node = TextNode(text="Page text.", metadata={**stamped, "page": 1})
    stamp_source_lineage(
        [node],
        file_path="/fixtures/a.pdf",
        source_id="src-a",
        content_hash="a" * 64,
        index_identity="b" * 64,
        source_version="c" * 64,
        source_attempt="attempt-1",
    )

    for mode in (MetadataMode.EMBED, MetadataMode.LLM):
        content = node.get_content(metadata_mode=mode)
        assert [key for key in STAMP_KEYS if f"{key}:" in content] == []


def test_listing_the_stamp_keys_does_not_move_a_default_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with_keys = _digest(_base())
    monkeypatch.setattr(
        source_state,
        "EXCLUDED_EMBED_METADATA_KEYS",
        tuple(k for k in source_state.EXCLUDED_EMBED_METADATA_KEYS if k not in STAMP_KEYS),
    )

    assert _digest(_base()) == with_keys == CODE_DEFAULT_PDF
