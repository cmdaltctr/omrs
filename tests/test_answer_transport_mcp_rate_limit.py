"""MCP ``answer_documents`` returns a rate-limited answer as a typed result (Exp 35 task 0.4).

Design D25 and gotcha 1: the tool returns the error result with its
``rate_limited`` record and never raises. The server model is a fake whose
provider replies HTTP 429; no network is used.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from conftest import build_mcp_server, direct_ctx
from omrs.core.ingestion import ingest_path_async
from omrs.transports.mcp import answer_documents

_COLLECTION = "answer_mcp_rate_limit"
_QUERY = "quantum lantern calibration"


class _RateLimitedLLM:
    """Server model whose provider replies HTTP 429 with ``Retry-After: 7``."""

    async def acomplete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
        error = RuntimeError("HTTP 429")
        error.status_code = 429  # type: ignore[attr-defined]
        error.response = SimpleNamespace(headers={"Retry-After": "7"})  # type: ignore[attr-defined]
        raise error


async def test_a_rate_limited_answer_returns_the_record(tmp_path: Path) -> None:
    source = tmp_path / "mcp-answer-doc.txt"
    source.write_text("The quantum lantern array is calibrated every Tuesday. " * 40)
    ingested = await ingest_path_async(str(source), collection_name=_COLLECTION)
    assert ingested["status"] == "ok", ingested
    server = build_mcp_server(answer_llm_factory=lambda: _RateLimitedLLM())

    result = await answer_documents(
        query=_QUERY,
        collection=_COLLECTION,
        similarity_threshold=0.0,
        ctx=direct_ctx(server),
    )

    assert (result["status"], result["failure_stage"]) == ("error", "generation")
    assert result["evidence"], "the evidence is kept"
    assert result["rate_limited"] == {
        "kind": "rate_limit",
        "http_status": 429,
        "retry_after_seconds": 7.0,
    }
