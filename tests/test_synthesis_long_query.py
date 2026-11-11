"""Long questions and long drafts must fit every synthesis round.

Experiment 35 FreshStack question 77536364 failed in 5 of 12 arm-runs
with llama-index's "Calculated available context size ... was not
non-negative". The prompt helper's window held the evidence budget and
the template slack only. A refine round also carries the question and
the draft answer, so a long Stack Overflow question plus a long draft
left a negative room for evidence and the answer failed.
"""

from __future__ import annotations

import re

from llama_index.core.schema import NodeWithScore, TextNode

from omrs.core.answer import synthesis

_LONG_QUERY = "How do I fix this LangChain error? " + "q" * 6_000
_LONG_DRAFT = "Draft answer [1]. " + "d" * 5_000
_BUDGET = {"context_window": 8_192, "max_output_tokens": 2_048, "max_rounds": 4}


def _nodes() -> list[NodeWithScore]:
    """Ten labelled passages: more than one round at the default budget."""
    return [
        NodeWithScore(node=TextNode(text=f"[{i}] " + "¤" * 1_500), score=1.0) for i in range(1, 11)
    ]


class _Capture:
    """Seam that records every prompt and replies with a fixed draft."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


def _labels(prompt: str) -> list[str]:
    """Passage labels and passage text size in one prompt round."""
    return [*re.findall(r"\[\d+\] ¤", prompt), str(prompt.count("¤"))]


async def test_a_long_question_with_a_long_draft_still_answers() -> None:
    """Question 77536364's shape: no negative-room error, rounds stay bounded."""
    capture = _Capture(_LONG_DRAFT)

    answer, calls = await synthesis.run_synthesis(_LONG_QUERY, _nodes(), seam=capture, **_BUDGET)

    assert answer
    assert 1 <= calls <= _BUDGET["max_rounds"]
    joined = "\n".join(capture.prompts)
    # The packer may split one passage across two rounds, so count text.
    assert all(f"[{i}]" in joined for i in range(1, 11)), "no passage label may be dropped"
    assert joined.count("¤") == 10 * 1_500, "no passage text may be dropped"


async def test_the_question_length_does_not_change_the_evidence_per_round() -> None:
    """Passages are packed into rounds the same way for short and long questions."""
    short, long = _Capture(_LONG_DRAFT), _Capture(_LONG_DRAFT)

    await synthesis.run_synthesis("short question", _nodes(), seam=short, **_BUDGET)
    await synthesis.run_synthesis(_LONG_QUERY, _nodes(), seam=long, **_BUDGET)

    assert [_labels(p) for p in long.prompts] == [_labels(p) for p in short.prompts]


async def test_planning_agrees_with_the_pipeline_for_a_long_question() -> None:
    """MRTR replay (design D6) returns the prompt the pipeline sends next."""
    capture = _Capture(_LONG_DRAFT)
    await synthesis.run_synthesis(_LONG_QUERY, _nodes(), seam=capture, **_BUDGET)
    assert len(capture.prompts) >= 2, "the case must need a refine round"

    planned = await synthesis.plan_next_prompt(
        _LONG_QUERY, _nodes(), previous_replies=[_LONG_DRAFT], **_BUDGET
    )

    assert planned == capture.prompts[1]
