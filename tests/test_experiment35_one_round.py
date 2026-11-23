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
closedbook35 = load("closedbook35")
oracle35 = load("oracle35")
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


# --- task 15.15: the largest oracle context per dataset and every closed-book prompt ---


class CharTokens:
    """Token counter at CHARS_PER_TOKEN characters per token (the safe side of Qwen3)."""

    @staticmethod
    def count(text: str) -> int:
        return -(-len(text) // CHARS_PER_TOKEN)

    @staticmethod
    def truncate(text: str, n: int) -> str:
        return text[: n * CHARS_PER_TOKEN]


#: Gold units per question at the large end of each dataset, each far above the cap
#: together: Legal has one gold passage; the others take many units.
GOLD_UNITS = {"legal": 1, "financebench": 12, "bioasq": 40, "freshstack": 40}
UNIT_TOKENS = {"legal": 30_000, "financebench": 6_000, "bioasq": 1_500, "freshstack": 4_000}


def _gold(dataset: str) -> list[dict[str, str]]:
    size = UNIT_TOKENS[dataset] * CHARS_PER_TOKEN
    return [
        {"chunk_id": f"{dataset}-u{i}", "text": ("word " * (size // 5))[:size], "source": f"u{i}"}
        for i in range(GOLD_UNITS[dataset])
    ]


def _oracle_calls(rows: list[dict], *, window: int, rounds: int) -> tuple[int, bool]:
    calls: list[str] = []

    async def seam(prompt: str) -> str:
        calls.append(prompt)
        return "The answer [1]."

    block = AnswerSettings(
        context_window=window, max_rounds=rounds, max_output_tokens=MAX_OUTPUT_TOKENS
    )
    outcome = asyncio.run(
        synthesise_answer(
            "q?", prepare_evidence(rows), complete=seam, answer_block=block, error_detail=str
        )
    )
    assert outcome.text is not None, outcome.error
    return len(calls), "[evidence truncated" in "".join(calls)


@pytest.mark.parametrize("dataset", sorted(GOLD_UNITS))
def test_the_largest_oracle_context_of_each_dataset_synthesises_in_one_call(dataset: str) -> None:
    kept, record = oracle35.oracle_context(_gold(dataset), CharTokens())
    assert record["tokens"] <= 20_480 and record["tokens_dropped"] > 0
    calls, cut = _oracle_calls(
        kept, window=arms.ANSWER_CONTEXT_WINDOW, rounds=arms.ANSWER_MAX_ROUNDS
    )
    assert (calls, cut) == (1, False), f"{dataset}: {calls} completion calls, truncated {cut}"


def test_an_uncapped_gold_set_would_not_fit_one_call() -> None:
    """The 20,480-token cap of task 15.12 is what keeps the oracle to one round."""
    calls, cut = _oracle_calls(
        _gold("freshstack"), window=arms.ANSWER_CONTEXT_WINDOW, rounds=arms.ANSWER_MAX_ROUNDS
    )
    assert calls > 1 or cut


#: A long question (a FreshStack title and body), well above the real longest one.
LONG_QUESTION = ("word " * 4096 * CHARS_PER_TOKEN)[: 4096 * CHARS_PER_TOKEN // 5 * 5]


@pytest.mark.parametrize("kind", ["own", "rag"])
def test_every_closed_book_prompt_is_one_completion_call(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import omrs.engine_answer as engine_answer

    calls: list[str] = []

    async def complete(prompt: str) -> str:
        calls.append(prompt)
        return "Paris"

    async def prepare(engine, settings, client, ledger):  # noqa: ANN001, ARG001
        return complete, settings, None, None

    class Engine:
        def resolve_settings(self, collection: str) -> str:
            return collection

    monkeypatch.setattr(engine_answer, "prepare_models", prepare)
    prompt = closedbook35.prompt_text(kind, LONG_QUESTION)
    result = asyncio.run(closedbook35.ask(Engine(), "c", prompt))
    assert result["answer"] == "Paris"
    assert calls == [prompt]
    tokens = CharTokens.count(prompt)
    assert tokens + MAX_OUTPUT_TOKENS <= arms.ANSWER_CONTEXT_WINDOW
