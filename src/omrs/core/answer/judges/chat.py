"""The ``chat`` claim judge: today's judge behind the strategy protocol (design D10).

It sends :func:`~omrs.core.answer.verify.build_judge_prompt` through the
injected chat seam and reads the reply with
:func:`~omrs.core.answer.verify.parse_verdict`, byte for byte as before
the registry. The judge receives no answer context.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..verify import build_judge_prompt, parse_verdict
from .base import Judgement, JudgeResources, JudgeUnavailable, make_call

#: Changes when the prompt or the reply reading changes.
VERSION = "chat-oneword/1"
NEEDS = ("complete",)
LOCAL_MODEL = False
NAME = "chat"


class ChatJudge:
    """Judge a claim with a chat model and a one-word reply (last word wins)."""

    name = NAME
    version = VERSION

    def __init__(self, resources: JudgeResources) -> None:
        """Keep the injected seam and the call facts."""
        if resources.complete is None:
            raise JudgeUnavailable("claim judge chat cannot run: no judge model")
        self._complete = resources.complete
        self._resources = resources

    async def __call__(self, prompt: str) -> str:
        """Send *prompt* through the plain judge seam (kept for seam callers)."""
        return await self._complete(prompt)

    async def judge(self, claim: str, evidence_texts: Sequence[str]) -> Judgement:
        """Return the parsed verdict and the call record. Seam errors propagate."""
        reply = await self._complete(build_judge_prompt(claim, evidence_texts))
        return Judgement(parse_verdict(reply), make_call(NAME, VERSION, self._resources))


def build(resources: JudgeResources) -> ChatJudge:
    """Return the chat judge over ``resources.complete``."""
    return ChatJudge(resources)
