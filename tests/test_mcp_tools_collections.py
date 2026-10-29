"""MCP tool routing through an in-memory client: the ``collection``
parameter of ingest, search and list, and the list_collections tool.

Split from ``test_mcp_tools.py`` so pytest-xdist can spread the slow
ingest-backed cases over more workers (``--dist loadfile``).
"""

from __future__ import annotations

from pathlib import Path

from conftest import connected_client, extract_tool_result

# ── 9.14 Collection parameter tests ─────────────────────────────────────────


async def test_ingest_with_collection_parameter(
    mcp_server,
    fixtures_dir: Path,
) -> None:
    """ingest_documents with collection param must store in named collection."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir), "collection": "mcp_test_coll"},
        )
        data = extract_tool_result(result)
        # Should succeed and use the named collection
        assert "files_indexed" in data
        assert data.get("collection") == "mcp_test_coll"


async def test_search_with_collection_parameter(
    mcp_server,
    fixtures_dir: Path,
) -> None:
    """search_documents with collection param must search named collection."""
    async with connected_client(mcp_server) as client:
        # First ingest into a named collection
        await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir), "collection": "mcp_search_coll"},
        )
        # Then search that collection
        result = await client.call_tool(
            "search_documents",
            {"query": "sample", "collection": "mcp_search_coll"},
        )
        data = extract_tool_result(result)
        assert isinstance(data, list)


async def test_list_with_collection_parameter(
    mcp_server,
    fixtures_dir: Path,
) -> None:
    """list_indexed_documents with collection param must list named collection."""
    async with connected_client(mcp_server) as client:
        await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir), "collection": "mcp_list_coll"},
        )
        result = await client.call_tool(
            "list_indexed_documents",
            {"collection": "mcp_list_coll"},
        )
        data = extract_tool_result(result)
        assert isinstance(data, list)
        assert len(data) >= 1


async def test_list_collections_tool(
    mcp_server,
    fixtures_dir: Path,
) -> None:
    """list_collections tool must return available collections."""
    async with connected_client(mcp_server) as client:
        # Ingest into two different collections
        await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir), "collection": "coll_a"},
        )
        await client.call_tool(
            "ingest_documents",
            {"path": str(fixtures_dir), "collection": "coll_b"},
        )

        result = await client.call_tool("list_collections", {})
        data = extract_tool_result(result)
        assert isinstance(data, list)

        # Must include both collections
        names = {c.get("name") for c in data}
        assert "coll_a" in names
        assert "coll_b" in names
