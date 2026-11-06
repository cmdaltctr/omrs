"""The Read document step sets local OCR cuts (change local-ocr-per-backend-cuts, group 7).

``ReadParams.ocr_local_cuts`` is a map from a local OCR backend name to a cut.
``None`` inherits the host map. A set value passes the Settings rule. The step
map merges over the host map: a step entry replaces the host cut of its own
backend, and every other backend keeps the host's effective cut. The map never
enters the graph fingerprint (``_UNHASHED_OPTIONS``). It enters the PDF
``parser`` block through the effective settings, so a step cut change
re-indexes PDF sources only.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tests.fixtures.pipeline_parity.ingestion.snapshot import collect_rows, pin_detection
from tests.unit.test_engine_pipelines_support import build_engine, retrieval_graph
from tests.unit.test_ingestion_graph_adapters_support import (
    admit,
    build_catalogue,
    canonical_graph,
    offline_settings,
    resources,
    run_by_hand,
)

from omrs.config.rules import document_reading_problem
from omrs.core.ingestion.graph_adapters_catalogue import (
    READ,
    READ_OCR_KEYS,
    READ_OPTION_KEYS,
    ReadParams,
)
from omrs.core.ingestion.graph_adapters_values import with_read_options
from omrs.core.ingestion.graph_fingerprint import graph_shape, ingestion_shape, standard_shape
from omrs.core.pipelines import IssueCode, PipelineValidationError, levers, parse_definition
from omrs.core.reading_parts import effective_cut

KEY = "ocr_local_cuts"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "smoke_text.pdf"


def _graph(**read: Any) -> dict[str, Any]:
    return canonical_graph("documents", read=read)


def _issues(effective_settings: Any, data: dict[str, Any], tmp_path: Path) -> list[Any]:
    engine = build_engine(offline_settings(effective_settings))
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(data, inputs={"path": str(tmp_path)})
    return list(caught.value.issues)


# ── The key lists ────────────────────────────────────────────────────────


def test_the_key_is_a_read_option_and_a_read_step_key() -> None:
    assert KEY in READ_OCR_KEYS
    assert KEY in READ_OPTION_KEYS
    assert KEY in levers._READ_STEP_OCR_KEYS
    assert READ.option_params[KEY] == KEY


# ── Parameter ────────────────────────────────────────────────────────────


def test_the_step_inherits_by_default_and_takes_a_valid_map() -> None:
    assert ReadParams().ocr_local_cuts is None
    assert ReadParams(ocr_local_cuts=None).ocr_local_cuts is None
    params = ReadParams.model_validate({KEY: {"pp-ocrv6-small": 0.88}})
    assert params.ocr_local_cuts == {"pp-ocrv6-small": 0.88}


@pytest.mark.parametrize(
    "value",
    [{"pp-ocrv6-small": 1.4}, {"nope": 0.9}, {"pp-ocrv6-small": True}, ["pp-ocrv6-small"]],
)
def test_a_bad_map_is_refused_naming_the_option_and_never_the_value(
    value: Any, effective_settings: Any, tmp_path: Path
) -> None:
    rule = document_reading_problem(KEY, value)
    assert rule is not None
    with pytest.raises(ValidationError, match=KEY) as caught:
        ReadParams.model_validate({KEY: value})
    assert rule in str(caught.value)

    bad = [
        issue
        for issue in _issues(effective_settings, _graph(**{KEY: value}), tmp_path)
        if issue.code == IssueCode.INVALID_PARAMETER
    ]
    assert bad and bad[0].node_id == "read"
    assert KEY in bad[0].message and rule in bad[0].message
    for leaked in ("1.4", "nope", "True"):
        assert leaked not in bad[0].message


# ── Graph-wide override stays host-owned ─────────────────────────────────


def test_a_graph_wide_override_is_host_owned_and_points_at_the_step(
    effective_settings: Any,
) -> None:
    engine = build_engine(effective_settings())
    data = retrieval_graph()
    data["overrides"] = {KEY: {"pp-ocrv6-small": 0.88}}

    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(data)

    owned = [i for i in caught.value.issues if i.code == IssueCode.HOST_OWNED_SETTING]
    assert owned and owned[0].lever == KEY
    assert "Read document step" in owned[0].message


# ── Merge, not replace ───────────────────────────────────────────────────


def test_a_step_entry_replaces_the_host_cut_of_its_own_backend_only(
    effective_settings: Any,
) -> None:
    host = effective_settings(ocr_local_cuts={"indra": 0.96})

    merged = with_read_options(host, {KEY: {"pp-ocrv6-small": 0.88}})

    assert merged.ocr_local_cuts == {"indra": 0.96, "pp-ocrv6-small": 0.88}
    assert effective_cut(merged, "pp-ocrv6-small") == 0.88
    assert effective_cut(merged, "indra") == 0.96
    assert host.ocr_local_cuts == {"indra": 0.96}


def test_a_step_entry_wins_over_a_host_entry_of_the_same_backend(effective_settings: Any) -> None:
    host = effective_settings(ocr_local_cuts={"indra": 0.96, "pp-ocrv6-small": 0.9})

    merged = with_read_options(host, ReadParams(ocr_local_cuts={"pp-ocrv6-small": 0.88}))

    assert merged.ocr_local_cuts == {"indra": 0.96, "pp-ocrv6-small": 0.88}


def test_null_inherits_the_host_map(effective_settings: Any) -> None:
    host = effective_settings(ocr_local_cuts={"indra": 0.96})
    assert with_read_options(host, ReadParams(ocr_local_cuts=None)) is host


# ── Fingerprint ──────────────────────────────────────────────────────────


def _fingerprint(**read: Any) -> str:
    data = canonical_graph("documents", read=read)
    return graph_shape(parse_definition(data).graph, build_catalogue()).fingerprint


def test_a_saved_graph_without_the_key_keeps_the_standard_fingerprint() -> None:
    assert _fingerprint() == standard_shape().fingerprint
    assert _fingerprint(**{KEY: None}) == standard_shape().fingerprint


def test_a_step_that_sets_cuts_keeps_the_graph_fingerprint_and_the_shape_block() -> None:
    data = canonical_graph("documents", read={KEY: {"pp-ocrv6-small": 0.95}})
    shape = graph_shape(parse_definition(data).graph, build_catalogue())

    assert shape.fingerprint == standard_shape().fingerprint
    assert shape.standard and shape.identity_block() is None
    assert shape.step_options() == {KEY: {"pp-ocrv6-small": 0.95}}


def test_a_cut_beside_another_option_stays_out_of_the_shape_block() -> None:
    read = {KEY: {"pp-ocrv6-small": 0.95}, "ocr_non_latin_routing": "detect"}
    shape = graph_shape(parse_definition(canonical_graph("d", read=read)).graph, build_catalogue())

    block = shape.identity_block()
    assert block is not None
    assert block["read_options"] == {"ocr_non_latin_routing": "detect"}


# ── Identity: PDF sources only ───────────────────────────────────────────


@pytest.fixture
def mixed_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A folder with one PDF source and one Markdown source."""
    pin_detection(monkeypatch)
    root = tmp_path / "mixed"
    root.mkdir()
    shutil.copy(FIXTURE, root / "smoke_text.pdf")
    (root / "notes.md").write_text("# Notes\n\nA short note about cuts.\n", encoding="utf-8")
    return root


async def _runner(host: Any, root: Path, collection: str) -> Any:
    from omrs.core.vectordb import get_default_store

    store, catalogue = get_default_store(), build_catalogue()

    async def run(**read: Any) -> list[str]:
        snapshot = admit(canonical_graph(collection, read=read), host, root, catalogue)
        outputs = await run_by_hand(snapshot, catalogue, resources(snapshot, catalogue, store))
        return sorted(o.values["summary"]["status"] for o in outputs)

    def identities() -> dict[str, str]:
        rows = collect_rows(store, collection, root)
        return {r["rel_path"]: r["metadata"]["source_index_identity"] for r in rows}

    return run, identities


@pytest.mark.asyncio
async def test_a_step_cut_change_reindexes_the_pdf_source_only(
    mixed_root: Path, effective_settings: Any
) -> None:
    host = offline_settings(effective_settings)
    run, identities = await _runner(host, mixed_root, "cuts_pdf_only")

    assert await run() == ["indexed", "indexed"]
    before = identities()
    assert set(before) == {"smoke_text.pdf", "notes.md"}
    assert await run() == ["skipped_unchanged", "skipped_unchanged"]

    assert await run(**{KEY: {"pp-ocrv6-small": 0.95}}) == ["indexed", "skipped_unchanged"]
    after = identities()
    assert after["smoke_text.pdf"] != before["smoke_text.pdf"]
    assert after["notes.md"] == before["notes.md"]

    assert await run(**{KEY: {"pp-ocrv6-small": 0.95}}) == [
        "skipped_unchanged",
        "skipped_unchanged",
    ]


@pytest.mark.asyncio
async def test_a_step_that_sets_the_host_value_keeps_the_standard_identity(
    mixed_root: Path, effective_settings: Any
) -> None:
    host = offline_settings(effective_settings)
    assert host.ocr_local_cuts == {}
    run, identities = await _runner(host, mixed_root, "cuts_host_value")

    assert await run() == ["indexed", "indexed"]
    before = identities()

    assert await run(**{KEY: {"pp-ocrv6-small": 0.92}}) == ["skipped_unchanged"] * 2
    assert identities() == before


@pytest.mark.asyncio
async def test_the_identity_follows_the_merged_map(
    mixed_root: Path, effective_settings: Any
) -> None:
    """The step map reaches the identify step through ``IngestionShape.step_options``."""
    host = offline_settings(effective_settings, ocr_local_cuts={"indra": 0.96})
    catalogue = build_catalogue()
    read = {KEY: {"pp-ocrv6-small": 0.88}}
    shape = ingestion_shape(admit(canonical_graph("x", read=read), host, mixed_root), catalogue)

    merged = with_read_options(host, shape.step_options())

    assert merged.ocr_local_cuts == {"indra": 0.96, "pp-ocrv6-small": 0.88}


# ── The catalogue ────────────────────────────────────────────────────────


def test_the_catalogue_reports_the_host_map_as_inherited(effective_settings: Any) -> None:
    engine = build_engine(offline_settings(effective_settings, ocr_local_cuts={"indra": 0.96}))
    read = next(op for op in engine.describe_operations() if op["operation_id"] == "read.document")

    assert read["inherited_values"][KEY] == {"indra": 0.96}


def test_the_catalogue_reports_an_empty_host_map(effective_settings: Any) -> None:
    engine = build_engine(offline_settings(effective_settings))
    read = next(op for op in engine.describe_operations() if op["operation_id"] == "read.document")

    assert read["inherited_values"][KEY] == {}
