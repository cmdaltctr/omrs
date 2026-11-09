"""The graph adapters build their models off the event loop (2026-11-09 review fix).

The first build of a role may read the OpenRouter endpoint list with a
blocking call (pre-exp35 D11). ``Engine.answer`` already builds its models
off the loop (``prepare_models``); these tests pin the same property for the
graph path that user-profile collections run, where one answer must not
stall every other request on the server.
"""

from __future__ import annotations

import threading
from typing import Any

from omrs.core.answer.graph_adapters import (
    ANSWER_LLM_RESOURCE,
    VERIFY_LLM_RESOURCE,
    PrepareEvidenceParams,
    SynthesiseParams,
    synthesise_adapter,
    verify_claims_adapter,
)
from omrs.core.pipelines.adapters import NodeContext


class _Completion:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeLLM:
    """An answer model whose seam call needs no network."""

    async def acomplete(self, _prompt: str) -> _Completion:
        return _Completion("The answer is yes.")


class _NoCancel:
    """A cancellation token that never fires."""

    cancelled = False


def _context(settings: Any, resources: dict[str, Any]) -> NodeContext:
    return NodeContext(
        run_id="run",
        node_id="node",
        settings=settings,
        resources=resources,
        cancellation=_NoCancel(),
    )


async def test_synthesise_builds_the_answer_model_off_the_loop(effective_settings: Any) -> None:
    settings = effective_settings()
    built: dict[str, int] = {}

    def factory() -> _FakeLLM:
        built["thread"] = threading.get_ident()
        return _FakeLLM()

    context = _context(settings, {ANSWER_LLM_RESOURCE: factory})
    output = await synthesise_adapter(
        context,
        {"query": "q", "context": [{"text": "alpha beta", "chunk_id": "c1"}]},
        SynthesiseParams(),
    )
    assert built, "the factory must run"
    assert built["thread"] != threading.get_ident()
    # Before the cite step the status is ``generation_unverified``; the text
    # proves the off-loop model was used.
    assert output.values["answer"]["answer"] == "The answer is yes."


async def test_verify_builds_the_judge_off_the_loop(effective_settings: Any) -> None:
    base = effective_settings()
    # The conftest factory takes no ``answer`` block override; copy the block.
    settings = base.model_copy(
        update={"answer": base.answer.model_copy(update={"verify_claims": True})}
    )
    built: dict[str, int] = {}

    def factory(_block: Any) -> None:
        built["thread"] = threading.get_ident()
        return None

    context = _context(settings, {VERIFY_LLM_RESOURCE: factory})
    answer = {
        "query": "q",
        "completion_source": "engine",
        "status": "ok",
        "answer": "Done.",
        "citations": [],
        "evidence": [],
    }
    output = await verify_claims_adapter(context, {"answer": answer}, PrepareEvidenceParams())
    assert built, "the factory must run"
    assert built["thread"] != threading.get_ident()
    assert output.values["answer"]["answer"] == "Done."
