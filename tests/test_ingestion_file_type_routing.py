"""File-type routing can be turned off for prepared Markdown passages.

Experiment 35 found that Magika routing on its prepared FreshStack passage
files sent fenced ``.md`` files to the code splitter, skipped files it called
binary, and made chunk counts depend on the folder path (the generic fallback
splitter subtracts the file path's token length). ``ingestion.file_type_routing``
off sends every file through the reader and the token-aware Markdown path.
The default stays on, so codebase collections keep code routing.

Magika is replaced by a fake detector so the tests never depend on its model.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omrs.core.ingestion import ingest_path_async, pipeline
from omrs.core.settings import (
    ChunkingBlock,
    EffectiveSettings,
    EmbeddingBlock,
    IngestionBlock,
    MetadataBlock,
)
from omrs.core.vectordb.lancedb.store import LanceVectorStore

#: Prose long enough for several 512-unit chunks on the word-level stub tokenizer.
_PROSE = "The loader reads each record and stores the parsed fields for later answers. " * 90
#: Starts with a heading, so tree-sitter Python parses it and CodeSplitter runs.
_FENCED = f"# Parse a JSON file\n\n{_PROSE}\n\n```python\nimport json\nrows = json.load(f)\n```\n"
#: Starts with a fence, so tree-sitter Python fails and the generic splitter runs.
_FENCE_FIRST = f"```python\nx = 1\n```\n\n{_PROSE}"


def _stub_tokenizer():
    """Return a word-level tokenizer whose units are whitespace-ish words."""
    from tokenizers import Tokenizer, models, pre_tokenizers

    marker = "[UNK]"
    tokenizer = Tokenizer(models.WordLevel({marker: 0}, unk_token=marker))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    return tokenizer


@pytest.fixture
def stub_tokenizer(monkeypatch: pytest.MonkeyPatch) -> None:
    from omrs.core.chunking import model_token

    tokenizer = _stub_tokenizer()
    monkeypatch.setattr(model_token, "load_tokenizer", lambda *_args: tokenizer)


def _settings(*, routing: bool) -> EffectiveSettings:
    return EffectiveSettings(
        chunking=ChunkingBlock(chunk_size=512, markdown_chunk_size=512, chunk_overlap=77),
        embedding=EmbeddingBlock(tokenizer_model="test/word", tokenizer_revision="rev-1"),
        metadata=MetadataBlock(extraction_mode="disabled"),
        ingestion=IngestionBlock(file_type_routing=routing),
    )


def _detect_as(monkeypatch: pytest.MonkeyPatch, content_type: str | None) -> None:
    """Make detection call every file *content_type*, as Magika did on the pod."""

    def fake(root: Path, *, settings: object) -> dict[str, str]:
        if content_type is None:
            return {}
        files = [root] if root.is_file() else sorted(root.rglob("*.md"))
        return {str(f.relative_to(root)) if f != root else ".": content_type for f in files}

    monkeypatch.setattr(pipeline, "detect_content_types", fake)


async def _ingest(folder: Path, store: LanceVectorStore, collection: str, settings) -> dict:
    return await ingest_path_async(
        str(folder), collection_name=collection, effective_settings=settings, store=store
    )


def _rows(store: LanceVectorStore, collection: str) -> list[tuple[str, dict]]:
    return [(text, meta) for _, text, meta in store.iter_documents(collection)]


def _folder(root: Path, text: str) -> Path:
    root.mkdir(parents=True)
    (root / "passage.md").write_text(text, encoding="utf-8")
    return root


@pytest.mark.asyncio
async def test_a_fenced_md_file_called_code_python_chunks_through_the_markdown_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_tokenizer: None
) -> None:
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    folder = _folder(tmp_path / "passages", _FENCED)
    _detect_as(monkeypatch, None)
    reference = await _ingest(folder, store, "reference", _settings(routing=True))
    _detect_as(monkeypatch, "code/python")
    result = await _ingest(folder, store, "routed_off", _settings(routing=False))

    assert result["status"] == "ok"
    assert result["chunks_created"] == reference["chunks_created"]
    rows = _rows(store, "routed_off")
    assert sorted(t for t, _ in rows) == sorted(t for t, _ in _rows(store, "reference"))
    assert all(meta.get("content_type") != "code/python" for _, meta in rows)
    # CodeSplitter caps a chunk at 1,500 characters; the 512-unit Markdown path does not.
    assert max(len(text) for text, _ in rows) > 1500


@pytest.mark.asyncio
async def test_a_file_called_binary_is_indexed_and_not_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_tokenizer: None
) -> None:
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    folder = _folder(tmp_path / "passages", _FENCED)
    _detect_as(monkeypatch, "binary/snap")
    result = await _ingest(folder, store, "binary_off", _settings(routing=False))

    assert result["status"] == "ok"
    assert result["files_skipped_binary"] == 0
    assert result["files_indexed"] == 1
    assert result["chunks_created"] > 0


@pytest.mark.asyncio
async def test_the_chunk_count_is_the_same_when_the_passages_folder_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_tokenizer: None
) -> None:
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    near = _folder(tmp_path / "p", _FENCE_FIRST)
    deep = tmp_path.joinpath(*[f"a-much-longer-folder-name-{i:02d}" for i in range(8)], "p")
    shutil.copytree(near, deep)
    _detect_as(monkeypatch, "code/python")
    first = await _ingest(near, store, "near", _settings(routing=False))
    second = await _ingest(deep, store, "deep", _settings(routing=False))

    assert first["chunks_created"] > 1
    assert second["chunks_created"] == first["chunks_created"]
    assert sorted(t for t, _ in _rows(store, "deep")) == sorted(t for t, _ in _rows(store, "near"))


def test_file_type_routing_stays_on_by_default() -> None:
    from omrs.config import Settings
    from omrs.core.ingestion.settings import IngestionSettings

    assert IngestionBlock().file_type_routing is True
    assert IngestionSettings().file_type_routing is True
    assert Settings(_env_file=None).ingestion.file_type_routing is True


def test_the_environment_variable_turns_file_type_routing_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omrs.compose_settings import settings_to_effective
    from omrs.config import Settings

    monkeypatch.setenv("INGESTION__FILE_TYPE_ROUTING", "false")
    settings = Settings(_env_file=None)
    assert settings.ingestion.file_type_routing is False
    assert settings_to_effective(settings).ingestion.file_type_routing is False


@pytest.mark.asyncio
async def test_the_saved_pipeline_discover_step_honours_the_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from omrs.core.ingestion import graph_adapters

    folder = _folder(tmp_path / "passages", _FENCED)
    monkeypatch.setattr(
        graph_adapters, "detect_content_types", lambda root, *, settings: {"passage.md": "x/y"}
    )

    async def units(routing: bool) -> list:
        context = SimpleNamespace(settings=_settings(routing=routing))
        out = await graph_adapters.discover_adapter(context, {"sources": str(folder)}, None)
        return [unit.content_type for unit in out.values["sources"]]

    assert await units(True) == ["x/y"]
    assert await units(False) == [None]
