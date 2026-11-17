"""One answer round for the largest evidence of every answer setup (tasks 14.1, 15.15).

The largest evidence set of each chunk size (10 passages at the level), the
largest ``-t20k`` cut (20,480 tokens of stored chunks) and the largest oracle
context (20,480 tokens) must synthesise through OMRS in exactly one
completion call with the frozen answer settings: ``context_window`` 131,072
and ``max_rounds`` 1. A recording stub seam stands in for the answer model.
At about 4.5 characters per Qwen3 token, 2,048 tokens are about 9,200
characters; the test uses 5 characters per token to stay on the safe side.
"""

from __future__ import annotations

import asyncio

import pytest
from tests._exp35_fixtures import load

from omrs.core.answer.settings import AnswerSettings
from omrs.core.answer.stages import prepare_evidence, synthesise_answer

arms = load("arms")
CHARS_PER_TOKEN = 5
MAX_OUTPUT_TOKENS = 2048


def _calls(passages: list[int], *, window: int, rounds: int) -> tuple[int, bool]:
    """Return the completion calls and whether any evidence was truncated."""
    calls: list[str] = []

    async def seam(prompt: str) -> str:
        calls.append(prompt)
        return "The answer [1]."

    rows = [
        {"chunk_id": f"c{i}", "text": ("word " * (size // 5))[:size], "source": f"s{i}"}
        for i, size in enumerate(passages)
    ]
    block = AnswerSettings(
        context_window=window, max_rounds=rounds, max_output_tokens=MAX_OUTPUT_TOKENS
    )
    outcome = asyncio.run(
        synthesise_answer(
            "q?", prepare_evidence(rows), complete=seam, answer_block=block, error_detail=str
        )
    )
    assert outcome.text is not None, outcome.error
    return len(calls), "[evidence truncated]" in "".join(calls)


SETS = {
    **{f"c{c} x 10": [c * CHARS_PER_TOKEN] * 10 for c in arms.CHUNKS},
    **{f"c{c}-t20k": [c * CHARS_PER_TOKEN] * (20_480 // c) for c in arms.CHUNKS},
    "oracle 20,480 tokens": [20_480 * CHARS_PER_TOKEN],
}


@pytest.mark.parametrize("name", sorted(SETS))
def test_the_largest_evidence_synthesises_in_one_completion_call(name: str) -> None:
    calls, cut = _calls(
        SETS[name], window=arms.ANSWER_CONTEXT_WINDOW, rounds=arms.ANSWER_MAX_ROUNDS
    )
    assert (calls, cut) == (1, False), f"{name}: {calls} completion calls, truncated {cut}"


def test_the_old_round_settings_need_more_than_one_call() -> None:
    calls, cut = _calls(SETS["c2048 x 10"], window=8192, rounds=4)
    assert calls > 1 or cut
