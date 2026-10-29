"""MCP tool routing through an in-memory client: discovery, profiles,
ingest, search, listing, validation and default-collection behaviour.

Split from ``test_mcp_tools.py`` so pytest-xdist can spread the slow
ingest-backed cases over more workers (``--dist loadfile``).
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from conftest import connected_client, extract_tool_result

# ── Tool discovery ─────────────────────────────────────────────────────────


async def test_list_tools_discovers_all_nine(mcp_server) -> None:
    """The server must expose all expected tools."""
    async with connected_client(mcp_server) as client:
        result = await client.list_tools()
        tool_names = {t.name for t in result.tools}
        assert tool_names == {
            "ingest_documents",
            "search_documents",
            "answer_documents",
            "list_indexed_documents",
            "list_collections",
            "delete_documents",
            "get_codebase_map",
            "change_collection_profile",
            "list_profiles",
        }


async def test_search_documents_annotations_remain_read_only(mcp_server) -> None:
    """Diagnostics do not change the search tool's safety annotations."""
    async with connected_client(mcp_server) as client:
        result = await client.list_tools()

    tool = next(item for item in result.tools if item.name == "search_documents")
    assert tool.annotations is not None
    annotations = tool.annotations.model_dump(by_alias=True)
    assert annotations["readOnlyHint"] is True
    assert annotations["destructiveHint"] is False


# ── list_profiles ──────────────────────────────────────────────────────────


async def test_list_profiles_carries_read_only_annotations(mcp_server) -> None:
    """The profile list changes nothing, so it is marked read-only."""
    async with connected_client(mcp_server) as client:
        result = await client.list_tools()

    tool = next(item for item in result.tools if item.name == "list_profiles")
    assert tool.annotations is not None
    annotations = tool.annotations.model_dump(by_alias=True)
    assert annotations["readOnlyHint"] is True
    assert annotations["destructiveHint"] is False


async def test_list_profiles_returns_the_built_ins_without_a_catalogue(mcp_server) -> None:
    """A process with no workspace catalogue lists the built-in profiles only."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool("list_profiles", {})

    items = extract_tool_result(result)
    assert [item["profile_id"] for item in items] == ["documents", "codebase"]
    for item in items:
        assert item["kind"] == "builtin" and item["ready"] is True
        assert item["not_ready_reasons"] == []
        assert item["slots"] == {"ingest": None, "search": None, "answer": None}
        assert item["used_by"] == []


async def test_list_profiles_adds_the_user_profiles_of_the_catalogue(
    tmp_path: Path, effective_settings: Any
) -> None:
    """With a catalogue the list holds the built-ins, then each user profile."""
    from tests.unit.test_mcp_stdio_profiles_support import PROFILE, engine_builder, make_env

    env = make_env(tmp_path / "seed", effective_settings)
    env.service.create_profile("Empty", source=None)
    engine = engine_builder(effective_settings(), [], "documents")(env.catalogue)
    from conftest import build_mcp_server

    async with connected_client(build_mcp_server(engine)) as client:
        items = extract_tool_result(await client.call_tool("list_profiles", {}))

    assert [item["profile_id"] for item in items] == ["documents", "codebase", PROFILE, "empty"]
    mine, empty = items[2], items[3]
    assert mine["kind"] == "user" and mine["base_profile"] == "documents"
    assert mine["ready"] is True and set(mine["slots"]) == {"ingest", "search", "answer"}
    assert empty["ready"] is False and len(empty["not_ready_reasons"]) == 3


# ── ingest_documents ───────────────────────────────────────────────────────


async def test_ingest_documents_with_fixtures_dir(mcp_server, fixtures_dir: Path) -> None:
    """Ingesting the test fixtures directory must succeed."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool("ingest_documents", {"path": str(fixtures_dir)})
        data = extract_tool_result(result)
        assert data["status"] == "ok"
        assert data["files_indexed"] > 0


async def test_ingest_documents_returns_lazy_setup_error(mcp_server) -> None:
    """Lazy profile-resolver construction errors return an MCP error result."""
    with patch.object(
        mcp_server.test_context.engine,
        "resolve_settings",
        side_effect=ImportError("missing optional dependency"),
    ):
        async with connected_client(mcp_server) as client:
            result = await client.call_tool("ingest_documents", {"path": "ignored.txt"})

    data = extract_tool_result(result)
    assert data == {"status": "error", "message": "ImportError: missing optional dependency"}


# ── search_documents ───────────────────────────────────────────────────────


async def test_search_after_ingest_returns_results(mcp_server, fixtures_dir: Path) -> None:
    """After ingesting fixtures, search must return results with correct shape."""
    async with connected_client(mcp_server) as client:
        # First, ingest
        await client.call_tool("ingest_documents", {"path": str(fixtures_dir)})
        # Then search
        result = await client.call_tool("search_documents", {"query": "capital of France"})
        data = extract_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        # Check shape of first result
        first = data[0]
        assert "score" in first
        assert "source" in first
        assert "text" in first
        assert "reranked" in first


async def test_search_documents_handler_is_async_and_preserves_shape(
    mcp_server,
) -> None:
    """MCP search handler is async and returns the same list-of-dicts shape."""
    import omrs.transports.mcp as server

    expected = [
        {
            "score": 0.9,
            "source": "fixture.txt",
            "page_label": None,
            "text": "fixture text",
            "reranked": False,
        }
    ]

    assert inspect.iscoroutinefunction(server.search_documents)

    with patch.object(
        mcp_server.test_context.engine, "search", return_value=expected
    ) as mock_search:
        async with connected_client(mcp_server) as client:
            result = await client.call_tool(
                "search_documents",
                {
                    "query": "fixture",
                    "top_k": 3,
                    "similarity_threshold": 0.25,
                    "rerank": True,
                    "collection": "mcp_shape_coll",
                },
            )

    data = extract_tool_result(result)
    assert data == expected
    mock_search.assert_called_once_with(
        "fixture",
        top_k=3,
        similarity_threshold=0.25,
        rerank=True,
        hybrid=None,
        expand_window=0,
        collection_name="mcp_shape_coll",
        metadata_filter=None,
        include_diagnostics=False,
    )


async def test_search_documents_defaults_follow_policy_resolver(mcp_server) -> None:
    """Omitted values reach the Engine as None, so it resolves them from the profile (D14)."""
    expected = [
        {
            "score": 0.9,
            "source": "fixture.txt",
            "page_label": None,
            "text": "fixture text",
            "reranked": False,
        }
    ]

    with patch.object(
        mcp_server.test_context.engine, "search", return_value=expected
    ) as mock_search:
        async with connected_client(mcp_server) as client:
            result = await client.call_tool(
                "search_documents",
                {"query": "fixture"},
            )

    data = extract_tool_result(result)
    assert data == expected
    mock_search.assert_called_once_with(
        "fixture",
        top_k=None,
        similarity_threshold=None,
        rerank=None,
        hybrid=None,
        expand_window=0,
        collection_name="documents",
        metadata_filter=None,
        include_diagnostics=False,
    )


@pytest.mark.parametrize(
    ("arguments", "expected_flag"),
    [
        ({"diagnostics": True}, True),
        ({"diagnostics": False}, False),
        ({}, False),
    ],
    ids=["enabled", "explicitly-disabled", "omitted"],
)
async def test_search_documents_diagnostics_passthrough(
    mcp_server,
    arguments: dict,
    expected_flag: bool,
) -> None:
    """MCP diagnostics map directly to core retrieval and preserve its output."""
    observed: list[bool] = []

    def _search(*args, **kwargs):
        observed.append(kwargs["include_diagnostics"])
        item = {
            "score": 0.9,
            "source": "fixture.txt",
            "text": "fixture text",
            "reranked": False,
        }
        if kwargs["include_diagnostics"]:
            item.update({"dense_rank": 1, "fused_rank": 1, "sparse_backend": "bm25"})
        return [item]

    with patch.object(mcp_server.test_context.engine, "search", side_effect=_search):
        async with connected_client(mcp_server) as client:
            result = await client.call_tool(
                "search_documents",
                {"query": "fixture", **arguments},
            )

    data = extract_tool_result(result)
    assert observed == [expected_flag]
    assert ("dense_rank" in data[0]) is expected_flag
    assert ("fused_rank" in data[0]) is expected_flag
    assert ("sparse_backend" in data[0]) is expected_flag


# ── list_indexed_documents ─────────────────────────────────────────────────


async def test_list_after_ingest_returns_nonempty(mcp_server, fixtures_dir: Path) -> None:
    """After ingesting, list_indexed_documents must return non-empty."""
    async with connected_client(mcp_server) as client:
        await client.call_tool("ingest_documents", {"path": str(fixtures_dir)})
        result = await client.call_tool("list_indexed_documents", {})
        data = extract_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        # Check shape
        first = data[0]
        assert "source" in first
        assert "chunks" in first


async def test_list_passes_through_orphaned_values(mcp_server) -> None:
    """MCP listing preserves orphaned values and every existing row key."""
    rows = [
        {"source": "gone.txt", "source_id": "gone", "chunks": 1, "orphaned": True},
        {"source": "present.txt", "source_id": "present", "chunks": 2, "orphaned": False},
        {"source": "legacy.txt", "source_id": None, "chunks": 3, "orphaned": None},
    ]

    with patch("omrs.transports.mcp.list._list_documents", return_value=rows):
        async with connected_client(mcp_server) as client:
            result = await client.call_tool("list_indexed_documents", {})

    assert extract_tool_result(result) == rows


# ── Parameter validation ───────────────────────────────────────────────────


async def test_search_without_query_returns_error(mcp_server) -> None:
    """Calling search_documents without query must return an error."""
    async with connected_client(mcp_server) as client:
        # MCPServer wraps pydantic validation errors as is_error=True
        result = await client.call_tool("search_documents", {})
        assert result.is_error is True
        # Verify the error mentions the missing field
        error_text = result.content[0].text
        assert "query" in error_text.lower()
        assert "required" in error_text.lower()


# ── 9.15 Backward compatibility tests ──────────────────────────────────────


async def test_ingest_without_collection_defaults_to_documents(
    mcp_server,
    fixtures_dir: Path,
) -> None:
    """ingest_documents without collection must use 'documents' collection."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir)},
        )
        data = extract_tool_result(result)
        # Should work without specifying collection
        assert "status" in data


async def test_search_without_collection_defaults_to_documents(
    mcp_server,
) -> None:
    """search_documents without collection must work with default."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "search_documents",
            {"query": "anything"},
        )
        data = extract_tool_result(result)
        assert isinstance(data, list)


async def test_list_without_collection_defaults_to_documents(
    mcp_server,
) -> None:
    """list_indexed_documents without collection must work with default."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool("list_indexed_documents", {})
        data = extract_tool_result(result)
        assert isinstance(data, list)
