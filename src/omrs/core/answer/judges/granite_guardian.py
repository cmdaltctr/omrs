"""The ``granite_guardian`` claim judge: IBM Granite Guardian 3.3, groundedness (design D10).

The prompt is the text the model's own chat template
(``ibm-granite/granite-guardian-3.3-8b``, ``chat_template.jinja``) renders
for ``guardian_config={"criteria_id": "groundedness"}``, the cited evidence
as ``documents``, the claim as the only message (role ``assistant``) and
thinking off. OMRS renders it here and the composition root sends it to the
router's ``/v1/completions``: llama-server prefills a chat request whose last
message is an assistant message, so its chat route never renders the judge
turn (design D10, card check 3).

The guardian answers ``yes`` when the risk is present: ``yes`` means
``unsupported`` and ``no`` means ``supported``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from ..verify import VERDICT_SUPPORTED, VERDICT_UNPARSEABLE, VERDICT_UNSUPPORTED
from .base import Judgement, JudgeRequestFailed, JudgeResources, JudgeUnavailable, make_call

#: Changes when the rendered prompt or the reply reading changes.
VERSION = "granite-guardian-3.3-groundedness/1"
NEEDS = ("generate",)
LOCAL_MODEL = True
NAME = "granite_guardian"
#: Thinking is off: the reply is the score tag alone.
THINK = False
#: Room for ``<score> yes </score>`` with spare tokens.
MAX_TOKENS = 32
#: The card's examples run at temperature 0.
DEFAULT_TEMPERATURE = 0.0

_SYSTEM = (
    "As a judge agent, your role is to help assess whether the provided text meets the given "
    "judging criteria, utilizing all available information, including conversations, "
    "documents, and tools."
)
_CRITERIA = (
    "A text is considered ungrounded or unfaithful if it includes information lacking support "
    "from, or directly contradicting, the provided document(s). This risk arises when the text "
    "fabricates details, misinterprets the content, or makes unsupported extrapolations beyond "
    "what is explicitly stated in the document(s)."
)
_SCORING = "If the last assistant's text meets the criteria, return 'yes'; otherwise, return 'no'."
_SCORE = re.compile(r"<score>(.*?)</score>", re.DOTALL)
_RISK = {"yes": VERDICT_UNSUPPORTED, "no": VERDICT_SUPPORTED}


def _turn(role: str, content: str) -> str:
    return f"<|start_of_role|>{role}<|end_of_role|>{content}<|end_of_text|>\n"


def _untrusted(text: str) -> str:
    """Break the role-token opener in untrusted text, so it cannot open a turn."""
    return text.replace("<|", "< |")


def guardian_prompt(claim: str, evidence_texts: Sequence[str]) -> str:
    """Return the guardian prompt for one claim, as the model's chat template renders it."""
    parts = [_turn("system", _SYSTEM)]
    for index, text in enumerate(evidence_texts):
        parts.append(
            f'<|start_of_role|>document {{"document_id" :"{index}"}}<|end_of_role|>\n'
            f"{_untrusted(text)}<|end_of_text|>\n"
        )
    parts.append(_turn("assistant", _untrusted(claim)))
    parts.append(
        _turn("judge_protocol", f"### Criteria: {_CRITERIA}\n\n### Scoring Schema: {_SCORING}")
    )
    parts.append(f"<|start_of_role|>judge{{{'think' if THINK else 'no_think'}}}<|end_of_role|>")
    return "".join(parts)


def read_score(reply: str) -> str:
    """Return the verdict of the last ``<score>`` tag; anything else is ``unparseable``."""
    scores = _SCORE.findall(reply or "")
    return (
        _RISK.get(scores[-1].strip().lower(), VERDICT_UNPARSEABLE)
        if scores
        else VERDICT_UNPARSEABLE
    )


class GraniteGuardianJudge:
    """Judge a claim's groundedness with Granite Guardian."""

    name = NAME
    version = VERSION

    def __init__(self, resources: JudgeResources) -> None:
        """Keep the injected completion call and the sampling values to send."""
        self._resources = resources
        temperature = resources.settings.get("temperature")
        self._options: dict[str, Any] = {
            "max_tokens": MAX_TOKENS,
            "temperature": DEFAULT_TEMPERATURE if temperature is None else temperature,
        }
        if resources.settings.get("seed") is not None:
            self._options["seed"] = resources.settings["seed"]
        self._settings = {
            "temperature": self._options["temperature"],
            "seed": self._options.get("seed"),
            "reasoning": None,
            "threshold": None,
            "think": THINK,
        }

    async def judge(self, claim: str, evidence_texts: Sequence[str]) -> Judgement:
        """Return the verdict read from the guardian's score.

        Raises:
            JudgeUnavailable: The judge cannot start. Nothing is sent.
        """
        resources = self._resources
        if resources.refusal is not None or resources.generate is None:
            raise JudgeUnavailable(f"claim judge {NAME} cannot run: {resources.refusal}")
        settings = self._settings
        try:
            reply = await resources.generate(guardian_prompt(claim, evidence_texts), self._options)
        except JudgeRequestFailed as failed:
            call = make_call(NAME, VERSION, resources, settings=settings, error=failed.reason)
            return Judgement(VERDICT_UNPARSEABLE, call)
        return Judgement(read_score(reply), make_call(NAME, VERSION, resources, settings=settings))


def build(resources: JudgeResources) -> GraniteGuardianJudge:
    """Return the Granite Guardian judge over ``resources.generate``."""
    return GraniteGuardianJudge(resources)
