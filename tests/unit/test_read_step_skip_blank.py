"""The Read document step sets ``ocr_skip_blank_pages`` (change page-routing-panel, task 4.1).

``ReadParams.ocr_skip_blank_pages`` is a nullable boolean: ``None`` inherits
the host value, and a set value passes the Settings rule. The key never enters
the graph fingerprint or the ``graph_shape`` block (``_UNHASHED_OPTIONS``,
design D5). It reaches the identify step through ``IngestionShape.step_options``
and enters the PDF ``parser`` block as the host value does (design D4), so a
step value ``false`` re-indexes PDF sources only.
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

from omrs.config.rules import BOOL_RULE
from omrs.core.ingestion.graph_adapters_catalogue import READ, ReadParams
from omrs.core.ingestion.graph_fingerprint import graph_shape, standard_shape
from omrs.core.pipelines import IssueCode, PipelineValidationError, parse_definition

KEY = "ocr_skip_blank_pages"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "smoke_text.pdf"


def _issues(effective_settings: Any, data: dict[str, Any], tmp_path: Path) -> list[Any]:
    engine = build_engine(offline_settings(effective_settings))
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(data, inputs={"path": str(tmp_path)})
    return list(caught.value.issues)


# ── Parameter ────────────────────────────────────────────────────────────


def test_the_step_inherits_by_default_and_takes_a_boolean() -> None:
    assert ReadParams().ocr_skip_blank_pages is None
    assert ReadParams.model_validate({KEY: False}).ocr_skip_blank_pages is False
    assert READ.option_params[KEY] == KEY


def test_text_is_refused_as_an_invalid_parameter(effective_settings: Any, tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match=KEY) as caught:
        ReadParams.model_validate({KEY: "no"})
    assert BOOL_RULE in str(caught.value)

    data = canonical_graph("documents", read={KEY: "no"})
    bad = [
        issue
        for issue in _issues(effective_settings, data, tmp_path)
        if issue.code == IssueCode.INVALID_PARAMETER
    ]
    assert bad and bad[0].node_id == "read"
    assert KEY in bad[0].message and BOOL_RULE in bad[0].message


def test_a_graph_wide_override_is_host_owned(effective_settings: Any) -> None:
    engine = build_engine(effective_settings())
    data = retrieval_graph()
    data["overrides"] = {KEY: False}

    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(data)

    owned = [i for i in caught.value.issues if i.code == IssueCode.HOST_OWNED_SETTING]
    assert owned and owned[0].lever == KEY


# ── Fingerprint ──────────────────────────────────────────────────────────


def test_a_saved_graph_without_the_key_keeps_the_standard_fingerprint() -> None:
    data = canonical_graph("documents", read={})
    shape = graph_shape(parse_definition(data).graph, build_catalogue())
    assert shape.fingerprint == standard_shape().fingerprint


def test_a_step_that_sets_it_keeps_the_fingerprint_and_the_shape_block() -> None:
    data = canonical_graph("documents", read={KEY: False})
    shape = graph_shape(parse_definition(data).graph, build_catalogue())

    assert shape.fingerprint == standard_shape().fingerprint
    assert shape.standard and shape.identity_block() is None
    assert shape.step_options() == {KEY: False}


# ── Identity: PDF sources only ───────────────────────────────────────────


@pytest.fixture
def mixed_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A folder with one PDF source and one Markdown source."""
    pin_detection(monkeypatch)
    root = tmp_path / "mixed"
    root.mkdir()
    shutil.copy(FIXTURE, root / "smoke_text.pdf")
    (root / "notes.md").write_text("# Notes\n\nA short note about blank pages.\n")
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
async def test_a_step_value_false_reindexes_the_pdf_source_only(
    mixed_root: Path, effective_settings: Any
) -> None:
    run, identities = await _runner(
        offline_settings(effective_settings), mixed_root, "skip_blank_step"
    )

    assert await run() == ["indexed", "indexed"]
    before = identities()

    assert await run(**{KEY: False}) == ["indexed", "skipped_unchanged"]
    after = identities()
    assert after["smoke_text.pdf"] != before["smoke_text.pdf"]
    assert after["notes.md"] == before["notes.md"]
    assert await run(**{KEY: False}) == ["skipped_unchanged", "skipped_unchanged"]


@pytest.mark.asyncio
async def test_a_step_that_repeats_the_host_value_keeps_the_standard_identity(
    mixed_root: Path, effective_settings: Any
) -> None:
    host = offline_settings(effective_settings)
    assert host.ocr_skip_blank_pages is True
    run, identities = await _runner(host, mixed_root, "skip_blank_host_value")

    assert await run() == ["indexed", "indexed"]
    before = identities()

    assert await run(**{KEY: True}) == ["skipped_unchanged"] * 2
    assert identities() == before


# ── The catalogue ────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", [True, False])
def test_the_catalogue_reports_the_host_value_as_inherited(
    effective_settings: Any, value: bool
) -> None:
    engine = build_engine(offline_settings(effective_settings, ocr_skip_blank_pages=value))
    read = next(op for op in engine.describe_operations() if op["operation_id"] == "read.document")

    assert read["inherited_values"][KEY] is value
