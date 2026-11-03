"""Identity-driven re-ingestion tests for the OCR capability (task 2.14).

Spec: openspec/changes/improve-rag-input-quality-5/specs/async-ingestion/
spec.md — "New input-quality inputs SHALL participate in the complete index
identity". Every scenario below drives the REAL ``ingest_path_async`` plus
the ``source_state`` skip/replace path with stub-worker-backed fingerprints:
no Paddle, no network, no worker subprocess dispatch (the clean calibration
PDF stays on the ``pdf_inspector`` fast path, so the identity change is the
ONLY difference between ingestion legs).

The conservative inclusion rule (design D8) is exercised directly: the
fingerprint and routing settings are hashed for a file that never routes to
the worker, because unnecessary reprocessing is safer than stale chunks.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from omrs.capabilities import probe_ocr_worker, reset_ocr_fingerprint_cache
from omrs.core.ingestion.ocr_identity import (
    ocr_fingerprint_payload,
    ocr_routing_payload,
)
from omrs.core.ingestion.pipeline import ingest_path_async
from omrs.core.ingestion.source_state import SOURCE_INDEX_IDENTITY_KEY
from omrs.core.vectordb import get_default_store
from omrs.integrations.ocr_worker.fingerprint import (
    UNAVAILABLE_OCR_WORKER_FINGERPRINT,
)
from omrs.integrations.ocr_worker.managed import ManagedOcrClient

pytest.importorskip("pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)")

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB_WORKER = REPO_ROOT / "tests" / "fixtures" / "ocr_worker" / "stub_worker.py"
CAL_CLEAN = REPO_ROOT / "tests" / "fixtures" / "pdf_baseline" / "calibration" / "cal_clean_text.pdf"


def _stub_command(mode: str) -> list[str]:
    """Build the stub worker launch command."""
    return [sys.executable, str(STUB_WORKER), "--mode", mode]


@pytest.fixture(autouse=True)
def _fresh_fingerprint_cache() -> Iterator[None]:
    """Isolate probe memoisation between tests."""
    reset_ocr_fingerprint_cache()
    yield
    reset_ocr_fingerprint_cache()


def _echo_fingerprint() -> Any:
    """The real available fingerprint probed from the stub worker."""
    fingerprint = probe_ocr_worker(_stub_command("echo"))
    assert fingerprint.available, "the echo stub capabilities probe must be healthy"
    return fingerprint


def _client(fingerprint: Any) -> ManagedOcrClient:
    """A managed client carrying the given resolved fingerprint.

    Construction starts nothing; the clean calibration PDF never dispatches
    a parse request, so the chosen fingerprint reaches the index identity
    without any subprocess work.
    """
    return ManagedOcrClient(
        fingerprint=fingerprint,
        command=_stub_command("echo"),
    )


async def _ingest(source: Path, settings: Any, client: ManagedOcrClient, collection: str) -> dict:
    """Run one ingestion leg with an injected client on a fresh collection."""
    return await ingest_path_async(
        str(source),
        effective_settings=settings,
        ocr_client=client,
        collection_name=collection,
    )


def _ocr_settings(effective_settings, **extra) -> Any:
    """Effective settings with the routing seam active and extraction off."""
    return effective_settings(
        pdf_reader="pdf_inspector",
        ocr_fallback_enabled=True,
        **{"metadata.extraction_mode": "disabled"},
        **extra,
    )


def _stored_identities(collection: str) -> set[str]:
    """Read the real stored ``source_index_identity`` values for a collection."""
    store = get_default_store()
    identities = {
        meta[SOURCE_INDEX_IDENTITY_KEY] for meta in store.iter_metadatas(collection) if meta
    }
    assert identities, f"no stored rows carry {SOURCE_INDEX_IDENTITY_KEY!r} in {collection}"
    return identities


# ── Canonical payload helpers ──────────────────────────────────────────────


def test_unavailable_fingerprint_payload_has_one_stable_shape() -> None:
    """The None default and the real constant produce the same payload.

    Pins the no-drift contract between ``ocr_identity``'s built-in
    unavailable shape and ``asdict(UNAVAILABLE_OCR_WORKER_FINGERPRINT)``
    (task 2.13: one stable unavailable fingerprint, never an omitted
    field, never a second shape).
    """
    assert ocr_fingerprint_payload(None) == asdict(UNAVAILABLE_OCR_WORKER_FINGERPRINT)
    assert ocr_fingerprint_payload(UNAVAILABLE_OCR_WORKER_FINGERPRINT) == asdict(
        UNAVAILABLE_OCR_WORKER_FINGERPRINT
    )


def test_routing_payload_carries_the_switch_unit_blank_test_and_local_tier(
    effective_settings,
) -> None:
    """The routing payload carries the switch, the unit, the blank test and the local cut."""
    from omrs.integrations.pdf.blank_pages import BLANK_PAGE_TEST_VERSION

    settings = effective_settings(ocr_fallback_enabled=True, ocr_local_min_confidence=0.7)
    assert ocr_routing_payload(settings) == {
        "enabled": True,
        "routing_unit": "page",
        "blank_page_test": BLANK_PAGE_TEST_VERSION,
        "local_tier": {"min_confidence": 0.7},
    }
    assert ocr_routing_payload(settings, local_model_identity="model@1")["local_tier"] == {
        "min_confidence": 0.7,
        "model": "model@1",
    }


# ── Routing unit in the index identity (change page-level-ocr-routing) ───

_IDENTITY_KWARGS = {
    "content_type": "application/pdf",
    "chunk_size": 512,
    "chunk_overlap": 100,
}

#: The page-source counts every install now emits (change page-routing-default).
_PAGE_SOURCE_COUNT_KEYS = (
    "ocr_pages_native",
    "ocr_pages_local",
    "ocr_pages_worker",
    "ocr_pages_blank",
    "ocr_pages_unresolved",
)


def test_routing_payload_has_no_gate_values(effective_settings) -> None:
    """The default payload names the unit and the local tier, and no document gate."""
    payload = ocr_routing_payload(effective_settings())

    assert set(payload) == {"enabled", "routing_unit", "blank_page_test", "local_tier"}


def test_every_install_identity_includes_the_page_source_counts(
    monkeypatch, effective_settings
) -> None:
    """On default settings the page-source counts move the identity.

    Page is the only unit, so every install can emit these keys. Leaving
    them out of the exclusion set would hide a real change in embedded text,
    which is the failure the exclusion set is hashed to prevent.
    """
    from omrs.core.ingestion import source_state
    from omrs.core.ingestion.source_state import build_index_identity

    settings = effective_settings()
    with_keys = build_index_identity(settings, **_IDENTITY_KWARGS)

    without = tuple(
        key
        for key in source_state.EXCLUDED_EMBED_METADATA_KEYS
        if key not in _PAGE_SOURCE_COUNT_KEYS
    )
    monkeypatch.setattr(source_state, "EXCLUDED_EMBED_METADATA_KEYS", without)
    without_keys = build_index_identity(settings, **_IDENTITY_KWARGS)

    assert with_keys != without_keys


def test_page_source_count_keys_are_excluded_from_the_embedding_text() -> None:
    """A page-source count outside the exclusion set would reach the embedding model."""
    from omrs.core.ingestion.embed_exclusions import EXCLUDED_EMBED_METADATA_KEYS

    assert set(_PAGE_SOURCE_COUNT_KEYS) <= set(EXCLUDED_EMBED_METADATA_KEYS)


def test_page_unit_identity_ignores_the_model_directory(effective_settings) -> None:
    """Where the model lives is not what the pages say.

    Moving a model cache must not reindex a corpus. Only inputs that change
    the emitted text belong in the identity.
    """
    from omrs.core.ingestion.source_state import build_index_identity

    here = build_index_identity(
        effective_settings(ocr_local_model_directory="/models/a"),
        **_IDENTITY_KWARGS,
    )
    there = build_index_identity(
        effective_settings(ocr_local_model_directory="/models/b"),
        **_IDENTITY_KWARGS,
    )

    assert here == there


def test_page_unit_identity_follows_the_escalation_threshold(effective_settings) -> None:
    """The threshold decides which pages the worker rereads, so it must count."""
    from omrs.core.ingestion.source_state import build_index_identity

    default_cut = build_index_identity(effective_settings(), **_IDENTITY_KWARGS)
    raised_cut = build_index_identity(
        effective_settings(ocr_local_min_confidence=0.95), **_IDENTITY_KWARGS
    )

    assert raised_cut != default_cut


# ── The blank-page test version (change skip-blank-pages-before-worker) ───


def test_payload_carries_the_blank_page_test_version(effective_settings) -> None:
    """The routing payload names the blank-test version for every install."""
    payload = ocr_routing_payload(effective_settings())

    assert payload["blank_page_test"] == 1


def test_blank_page_test_version_moves_the_identity(monkeypatch, effective_settings) -> None:
    """A threshold change reindexes every source, through the version."""
    from omrs.core.ingestion.source_state import build_index_identity
    from omrs.integrations.pdf import blank_pages

    settings = effective_settings()
    before = build_index_identity(settings, **_IDENTITY_KWARGS)
    monkeypatch.setattr(blank_pages, "BLANK_PAGE_TEST_VERSION", 2)
    after = build_index_identity(settings, **_IDENTITY_KWARGS)

    assert after != before


def test_blank_count_key_is_excluded() -> None:
    """``ocr_pages_blank`` never reaches the embedding model."""
    from omrs.core.ingestion.embed_exclusions import EXCLUDED_EMBED_METADATA_KEYS

    assert "ocr_pages_blank" in EXCLUDED_EMBED_METADATA_KEYS


def test_local_cut_default_change_moves_the_identity(effective_settings) -> None:
    """The previous 0.8 cut differs from the default, so a source on default settings reindexes."""
    from omrs.core.ingestion.source_state import build_index_identity

    previous = build_index_identity(
        effective_settings(ocr_local_min_confidence=0.8), **_IDENTITY_KWARGS
    )
    current = build_index_identity(effective_settings(), **_IDENTITY_KWARGS)

    assert previous != current


# ── Scenario: degraded extraction recovers when OCR becomes available ─────


async def test_unavailable_to_available_fingerprint_forces_reingestion(
    tmp_path: Path, effective_settings
) -> None:
    """A byte-identical source indexed while UNAVAILABLE is re-ingested.

    Spec scenario "Degraded extraction recovers when the OCR capability
    becomes available": the resolved OCR capability SHALL differ from the
    stored index identity, and the source SHALL NOT be reported as
    ``skipped_unchanged``.
    """
    source = tmp_path / "clean.pdf"
    source.write_bytes(CAL_CLEAN.read_bytes())
    settings = _ocr_settings(effective_settings)

    unavailable = _client(UNAVAILABLE_OCR_WORKER_FINGERPRINT)
    try:
        first = await _ingest(source, settings, unavailable, "ocr_id_unavail")
    finally:
        unavailable.close()
    assert first["file_details"][0]["status"] == "indexed"
    first_identities = _stored_identities("ocr_id_unavail")

    available = _client(_echo_fingerprint())
    try:
        second = await _ingest(source, settings, available, "ocr_id_unavail")
    finally:
        available.close()
    assert second["file_details"][0]["status"] != "skipped_unchanged", (
        "the capability transition must be an identity change (design D8)"
    )
    assert second["file_details"][0]["status"] == "indexed"
    second_identities = _stored_identities("ocr_id_unavail")
    assert len(first_identities) == len(second_identities) == 1, (
        "each leg must leave exactly one complete current version"
    )
    assert second_identities.isdisjoint(first_identities), (
        "the stored identity must change when the fingerprint changes"
    )


# ── Scenario: each fingerprint field independently forces reprocessing ────


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("protocol_version", "1.1"),
        ("packages", (("stub-worker", "1.1"),)),
        ("pipeline_identity", "other-pipeline"),
        ("pipeline_revision", "2"),
        ("model_identity", "other-model"),
        ("model_revision", "2"),
        ("output_schema_id", "other.ocr.parse_output"),
        ("output_schema_version", "2"),
    ],
)
async def test_each_fingerprint_field_change_prevents_skip(
    field: str, changed: Any, tmp_path: Path, effective_settings
) -> None:
    """Changing any one fingerprint field invalidates the stored identity."""
    source = tmp_path / "clean.pdf"
    source.write_bytes(CAL_CLEAN.read_bytes())
    settings = _ocr_settings(effective_settings)
    base = _echo_fingerprint()

    first_client = _client(base)
    try:
        first = await _ingest(source, settings, first_client, f"ocr_id_{field}")
    finally:
        first_client.close()
    assert first["file_details"][0]["status"] == "indexed"

    variant = replace(base, **{field: changed})
    second_client = _client(variant)
    try:
        second = await _ingest(source, settings, second_client, f"ocr_id_{field}")
    finally:
        second_client.close()
    assert second["file_details"][0]["status"] == "indexed", (
        f"changing fingerprint field {field!r} must prevent skipped_unchanged"
    )


# ── Scenario: unchanged input-quality inputs still skip ───────────────────


async def test_unchanged_fingerprint_preserves_skip(tmp_path: Path, effective_settings) -> None:
    """An unchanged canonical fingerprint keeps ``skipped_unchanged``.

    The second leg uses a FRESH client instance carrying an EQUAL
    fingerprint value, proving identity comparison is canonical (value)
    comparison, not object identity.
    """
    source = tmp_path / "clean.pdf"
    source.write_bytes(CAL_CLEAN.read_bytes())
    settings = _ocr_settings(effective_settings)
    base = _echo_fingerprint()

    first_client = _client(base)
    try:
        first = await _ingest(source, settings, first_client, "ocr_id_same")
    finally:
        first_client.close()
    assert first["file_details"][0]["status"] == "indexed"
    first_identities = _stored_identities("ocr_id_same")

    equal_client = _client(replace(base))
    try:
        second = await _ingest(source, settings, equal_client, "ocr_id_same")
    finally:
        equal_client.close()
    assert second["file_details"][0]["status"] == "skipped_unchanged"
    assert (
        first["file_details"][0]["source_version"] == second["file_details"][0]["source_version"]
    ), "equal content plus equal fingerprint must reproduce the source version"
    # The skip means nothing new landed: the stored identity set is
    # unchanged and still exactly one complete current version.
    assert _stored_identities("ocr_id_same") == first_identities
    assert len(first_identities) == 1


# ── Scenario: OCR routing configuration change forces reprocessing ────────


async def test_routing_configuration_change_alone_prevents_skip(
    tmp_path: Path, effective_settings
) -> None:
    """A routing-setting change alone invalidates the stored identity.

    Spec scenario "OCR routing configuration change forces reprocessing":
    only ``OCR_LOCAL_MIN_CONFIDENCE`` changes (0.8 → 0.95) between legs
    — same fingerprint, same bytes, same chunking.
    """
    source = tmp_path / "clean.pdf"
    source.write_bytes(CAL_CLEAN.read_bytes())
    base = _echo_fingerprint()
    low = _ocr_settings(effective_settings, ocr_local_min_confidence=0.8)
    high = _ocr_settings(effective_settings, ocr_local_min_confidence=0.95)

    client = _client(base)
    try:
        first = await _ingest(source, low, client, "ocr_id_routing")
        first_identities = _stored_identities("ocr_id_routing")
        second = await _ingest(source, high, client, "ocr_id_routing")
    finally:
        client.close()
    assert first["file_details"][0]["status"] == "indexed"
    assert second["file_details"][0]["status"] == "indexed", (
        "a routing-configuration change alone must prevent skipped_unchanged"
    )
    second_identities = _stored_identities("ocr_id_routing")
    assert len(first_identities) == len(second_identities) == 1, (
        "each leg must leave exactly one complete current version"
    )
    assert second_identities.isdisjoint(first_identities), (
        "the stored identity must change when the routing setting changes"
    )


# ── Scenario: query instruction change alone does not force reprocessing ──


async def test_query_instruction_change_alone_still_skips(
    tmp_path: Path, effective_settings
) -> None:
    """Only ``EMBEDDING__QUERY_INSTRUCTION`` changes: identity is unchanged.

    Spec scenario "Query instruction change alone does not force
    reprocessing", asserted here against the schema-5 payload too: the
    instruction changes query vectors only and stays OUT of the document
    identity (design D8, proposal §6).
    """
    source = tmp_path / "clean.pdf"
    source.write_bytes(CAL_CLEAN.read_bytes())
    base = _echo_fingerprint()
    plain = _ocr_settings(effective_settings)
    instructed = _ocr_settings(
        effective_settings, **{"embedding.query_instruction": "retrieve evidence"}
    )

    client = _client(base)
    try:
        first = await _ingest(source, plain, client, "ocr_id_query")
        first_identities = _stored_identities("ocr_id_query")
        second = await _ingest(source, instructed, client, "ocr_id_query")
    finally:
        client.close()
    assert first["file_details"][0]["status"] == "indexed"
    assert second["file_details"][0]["status"] == "skipped_unchanged", (
        "the query instruction must stay out of the document index identity"
    )
    assert (
        first["file_details"][0]["source_version"] == second["file_details"][0]["source_version"]
    ), "equal content plus an instruction-only change must reproduce the version"
    assert _stored_identities("ocr_id_query") == first_identities
    assert len(first_identities) == 1
