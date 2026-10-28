"""The index identity records the step OCR settings (task 4.4, design D4).

Change integrations-show-runtime-components. The identify step builds each
source identity with the OCR options of the Read document node, as it does
for the step reader. An engine change on the node reprocesses the source on
the next explicit ingest. A node that inherits every OCR option keeps the
identity of the standard ingest path.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from llama_index.core import Settings as LlamaIndexSettings
from tests.fixtures.pipeline_parity.ingestion.snapshot import (
    collect_rows,
    copy_sources,
    pin_detection,
)
from tests.unit.test_ingestion_graph_adapters_support import (
    admit,
    build_catalogue,
    canonical_graph,
    offline_settings,
    resources,
    run_by_hand,
)

from omrs.core.ingestion.graph_adapters_catalogue import READ_OCR_KEYS
from omrs.core.ingestion.graph_fingerprint import ingestion_shape
from omrs.core.ingestion.source_state import build_index_identity
from omrs.core.ingestion.sources import build_ingestion_context

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "smoke_text.pdf"


@pytest.fixture
def pdf_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    pin_detection(monkeypatch)
    root = tmp_path / "pdfs"
    root.mkdir()
    shutil.copy(FIXTURE, root / "smoke_text.pdf")
    return root


def _identity_with(settings: Any, block: dict | None) -> str:
    """Return the identity a pypdf read of the fixture gets under *settings*."""
    from omrs.integrations.pdf.factory import declared_output_revision

    ctx = build_ingestion_context(
        settings, embed_model=LlamaIndexSettings.embed_model, graph_shape=block
    )
    return build_index_identity(
        settings,
        content_type=None,
        chunk_size=ctx.chunk_size,
        chunk_overlap=ctx.chunk_overlap,
        text_format="plain",
        pdf_reader_revision=declared_output_revision(settings.pdf_reader),
        embed_model=ctx.embed_model,
        ocr_routing=ctx.ocr_routing,
        ocr_worker_fingerprint=ctx.ocr_worker_fingerprint,
        ocr_fallback_fingerprint=ctx.ocr_fallback_fingerprint,
        tokenizer=ctx.markdown_chunking.tokenizer_identity,
        resolved_splitter=ctx.markdown_chunking.resolved_splitter,
        graph_shape=ctx.graph_shape,
    )


def _host(effective_settings: Any) -> Any:
    return offline_settings(effective_settings, ocr_engine_primary="dots-mocr")


async def _runner(host: Any, root: Path, collection: str) -> Any:
    from omrs.core.vectordb import get_default_store

    store, catalogue = get_default_store(), build_catalogue()

    async def run(**read: Any) -> list[str]:
        snapshot = admit(canonical_graph(collection, read=read), host, root, catalogue)
        outputs = await run_by_hand(snapshot, catalogue, resources(snapshot, catalogue, store))
        return [o.values["summary"]["status"] for o in outputs]

    return run, store


@pytest.mark.asyncio
async def test_engine_change_reprocesses_the_source(
    pdf_root: Path, effective_settings: Any
) -> None:
    """Inherited ``dots-mocr``, then ``paddleocr-vl`` on the node: indexed again."""
    host = _host(effective_settings)
    run, store = await _runner(host, pdf_root, "ocr_engine_reuse")

    assert await run() == ["indexed"]
    assert await run() == ["skipped_unchanged"]
    assert await run(ocr_engine_primary="paddleocr-vl") == ["indexed"]
    assert await run(ocr_engine_primary="paddleocr-vl") == ["skipped_unchanged"]

    shape = ingestion_shape(
        admit(canonical_graph("x", read={"ocr_engine_primary": "paddleocr-vl"}), host, pdf_root),
        build_catalogue(),
    )
    step = host.model_copy(update={"ocr_engine_primary": "paddleocr-vl"})
    rows = collect_rows(store, "ocr_engine_reuse", pdf_root)
    assert rows
    expected = _identity_with(step, shape.identity_block())
    assert {r["metadata"]["source_index_identity"] for r in rows} == {expected}


def test_identity_block_names_only_the_set_ocr_options(
    pdf_root: Path, effective_settings: Any
) -> None:
    """The ``graph_shape`` block carries the set OCR options and no others."""
    host = _host(effective_settings)
    read = {"ocr_engine_primary": "paddleocr-vl", "ocr_fallback_page_fraction": 0.5}
    shape = ingestion_shape(
        admit(canonical_graph("x", read=read), host, pdf_root), build_catalogue()
    )
    assert dict(shape.read_options) == read
    block = shape.identity_block()
    assert block is not None and block["read_options"] == read
    reader_only = ingestion_shape(
        admit(canonical_graph("x", read={"pdf_reader": "pypdf"}), host, pdf_root),
        build_catalogue(),
    )
    assert dict(reader_only.read_options) == {}
    assert "read_options" not in (reader_only.identity_block() or {})


@pytest.mark.asyncio
async def test_identify_builds_the_identity_with_the_step_ocr_settings(
    pdf_root: Path, effective_settings: Any
) -> None:
    """A step ``ocr_fallback_page_fraction`` reaches the stored OCR routing payload."""
    host = _host(effective_settings)
    run, store = await _runner(host, pdf_root, "ocr_fraction")
    assert await run(ocr_fallback_page_fraction=0.5) == ["indexed"]

    shape = ingestion_shape(
        admit(canonical_graph("x", read={"ocr_fallback_page_fraction": 0.5}), host, pdf_root),
        build_catalogue(),
    )
    step = host.model_copy(update={"ocr_fallback_page_fraction": 0.5})
    rows = collect_rows(store, "ocr_fraction", pdf_root)
    identities = {r["metadata"]["source_index_identity"] for r in rows}
    assert identities == {_identity_with(step, shape.identity_block())}
    assert identities != {_identity_with(host, shape.identity_block())}


@pytest.mark.asyncio
async def test_all_inherit_template_keeps_the_standard_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """Every OCR option set to ``null``: the stored identity equals ``ingest_path_async``."""
    from omrs.core.ingestion.pipeline import ingest_path_async
    from omrs.core.vectordb import get_default_store

    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    host = offline_settings(effective_settings)
    store, catalogue = get_default_store(), build_catalogue()
    await ingest_path_async(
        str(root), collection_name="standard", effective_settings=host, store=store
    )
    read = dict.fromkeys(READ_OCR_KEYS)
    snapshot = admit(canonical_graph("graph", read=read), host, root, catalogue)
    assert ingestion_shape(snapshot, catalogue).standard
    await run_by_hand(snapshot, catalogue, resources(snapshot, catalogue, store))

    def identities(collection: str) -> dict[str, str]:
        rows = collect_rows(store, collection, root)
        return {r["rel_path"]: r["metadata"]["source_index_identity"] for r in rows}

    assert identities("graph") and identities("graph") == identities("standard")
