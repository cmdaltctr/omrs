"""The ``clef_flash`` claim judge: one decision question per claim (design D10).

Clef-Flash answers a System One ``noul`` question with P(yes) and writes no
text. The claim and the evidence it cites go in the state; the composition
root sends the question through the decision adapter (``/v1/systemone``,
router lease) and refuses a build below 8-bit before any request (root
gotcha 16).
"""

from __future__ import annotations

from collections.abc import Sequence

from ..verify import VERDICT_SUPPORTED, VERDICT_UNPARSEABLE, VERDICT_UNSUPPORTED
from .base import Judgement, JudgeRequestFailed, JudgeResources, JudgeUnavailable, make_call

#: Changes when the question, the state layout or the threshold changes.
VERSION = "clef-flash-claim/1"
NEEDS = ("decide",)
LOCAL_MODEL = True
#: The composition root runs the 8-bit check of ``core/providers/decision/checks.py``.
EIGHT_BIT_CHECK = True
NAME = "clef_flash"
#: P(yes) at or above this gives ``supported`` (design D10; not a setting).
THRESHOLD = 0.5
QUESTION = "Does the evidence fully support the claim, with nothing in the claim missing from it?"
SETTINGS = {"temperature": None, "seed": None, "reasoning": None, "threshold": THRESHOLD}
#: The decision request carries no sampling values; the judge settings read
#: reports these so the panel does not show a saved value as effective.
IGNORED_SAMPLING = ("temperature", "seed")


def state_text(claim: str, evidence_texts: Sequence[str]) -> str:
    """Return the state: the claim, then each cited evidence text in order."""
    parts = [f"Claim:\n{claim}"]
    parts += [f"Evidence {index}:\n{text}" for index, text in enumerate(evidence_texts, start=1)]
    return "\n\n".join(parts)


class ClefFlashJudge:
    """Judge a claim with P(yes) from a decision model."""

    name = NAME
    version = VERSION

    def __init__(self, resources: JudgeResources) -> None:
        """Keep the injected decision call and the refusal, if any."""
        self._resources = resources

    async def judge(self, claim: str, evidence_texts: Sequence[str]) -> Judgement:
        """Return ``supported`` at P(yes) >= 0.5, ``unsupported`` below, else ``unparseable``.

        Raises:
            JudgeUnavailable: The judge cannot start (no model, no router or a
                build below 8-bit). Nothing is sent.
        """
        resources = self._resources
        if resources.refusal is not None or resources.decide is None:
            raise JudgeUnavailable(f"claim judge {NAME} cannot run: {resources.refusal}")
        try:
            p_yes = await resources.decide(QUESTION, state_text(claim, evidence_texts))
        except JudgeRequestFailed as failed:
            call = make_call(NAME, VERSION, resources, settings=SETTINGS, error=failed.reason)
            return Judgement(VERDICT_UNPARSEABLE, call)
        call = make_call(NAME, VERSION, resources, settings=SETTINGS, p_yes=p_yes)
        if p_yes is None:
            return Judgement(VERDICT_UNPARSEABLE, call)
        return Judgement(VERDICT_SUPPORTED if p_yes >= THRESHOLD else VERDICT_UNSUPPORTED, call)


def build(resources: JudgeResources) -> ClefFlashJudge:
    """Return the Clef-Flash judge over ``resources.decide``."""
    return ClefFlashJudge(resources)
