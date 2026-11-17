"""Judge settings and Ragas parts of the Experiment 35 Ragas stage (tasks 7.3, 14.5; H-11).

The judge model, provider, host, reasoning, temperature and seed come from
``plan.json`` (``runtime.references``, role ``ragas-judge``), never from the
pre-freeze ``measure_lib.py``. A built judge whose values differ refuses. Ragas
lives in a separate environment and is imported only inside :func:`main_metrics`.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PREFREEZE = Path(__file__).resolve().parent / "prefreeze"
if str(_PREFREEZE) not in sys.path:
    sys.path.insert(0, str(_PREFREEZE))

import ragas_stage as ragas_stage_lib  # noqa: E402

JUDGE_ROLE = "ragas-judge"
JUDGE_FIELDS = ("model", "provider", "host", "reasoning", "temperature", "seed")
BUILT_FIELDS = ("model", "host", "reasoning", "temperature", "seed")


class RagasRefused(RuntimeError):
    """The stage refuses to start; nothing was sent."""


def judge_settings(plan: Mapping[str, Any], host: str) -> dict[str, Any]:
    """Return the Ragas judge settings of *plan* (``runtime.references``, role ``ragas-judge``).

    Raises:
        RagasRefused: *host* is empty, a setting is missing from the plan, or the
            plan's host differs from *host*.
    """
    if not host:
        raise RagasRefused("--ragas-host is required for the ragas stage")
    found = [r for r in plan["runtime"]["references"] if r.get("role") == JUDGE_ROLE]
    reference = found[0] if found else {}
    missing = [name for name in JUDGE_FIELDS if name not in reference]
    if missing:
        raise RagasRefused(f"plan.json {JUDGE_ROLE} lacks {', '.join(missing)}")
    if reference["host"] != host:
        raise RagasRefused(f"--ragas-host {host} differs from plan.json host {reference['host']}")
    return {name: reference[name] for name in JUDGE_FIELDS}


def built_judge_values(llm: Any) -> dict[str, Any]:
    """Return the model, host, reasoning, temperature and seed a built OMRS judge sends."""
    from omrs.core.providers.llm.sampling import sent_values

    temperature, seed = sent_values(llm)
    body = (getattr(llm, "additional_kwargs", None) or {}).get("extra_body") or {}
    only = (body.get("provider") or {}).get("only") or []
    return {
        "model": getattr(llm, "model", None),
        "host": only[0] if len(only) == 1 else only,
        "reasoning": (body.get("reasoning") or {}).get("effort"),
        "temperature": temperature,
        "seed": seed,
    }


def check_built(settings: Mapping[str, Any], built: Mapping[str, Any]) -> None:
    """Refuse a built judge whose values differ from the plan settings.

    Raises:
        RagasRefused: The message names each differing value, planned and built.
    """
    differ = [
        f"{name} (plan {settings[name]!r}, built {built.get(name)!r})"
        for name in BUILT_FIELDS
        if built.get(name) != settings[name]
    ]
    if differ:
        raise RagasRefused(f"the built Ragas judge differs from plan.json: {'; '.join(differ)}")


def build_judge(settings: Mapping[str, Any]) -> tuple[Callable[[str], Awaitable[Any]], dict]:
    """Build the judge through OMRS (host check included); return its seam and built values."""
    from omrs.compose import get_settings
    from omrs.compose_answer import build_verify_llm
    from omrs.core.answer.settings import normalise_hosts

    base = get_settings()
    block = base.answer.model_copy(
        update={
            "verify_claims": True,
            "verify_provider": settings["provider"],
            "verify_model": settings["model"],
            "verify_reasoning": settings["reasoning"],
            "verify_temperature": settings["temperature"],
            "verify_seed": settings["seed"],
            "verify_allowed_hosts": normalise_hosts(settings["host"]),
        }
    )
    llm = build_verify_llm(base, answer_block=block)
    if llm is None:
        raise RagasRefused("OMRS built no judge: llama-index-llms-openai-like is missing")
    return ragas_stage_lib.omrs_chat_seam(llm, settings["provider"]), built_judge_values(llm)


def main_metrics(seam: Any, embeddings: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the five metric scorers over *seam*, and the correctness weights.

    Four come from the pre-freeze builder; ``AnswerCorrectness`` gets the
    question, the answer and the reference answer, never the contexts (D33).
    """
    from ragas.metrics.collections import AnswerCorrectness

    llm = ragas_stage_lib.ragas_llm(seam)
    four = ragas_stage_lib.ragas_metrics(llm, embeddings)
    correctness = AnswerCorrectness(llm=llm, embeddings=embeddings)

    async def correct(s: Mapping[str, Any]) -> float:
        result = await correctness.ascore(
            user_input=s["question"], response=s["answer"], reference=s["reference"]
        )
        return float(result.value)

    metrics = {f"ragas_{name}": fn for name, fn in four.items()}
    metrics["ragas_answer_correctness"] = correct
    return metrics, {"answer_correctness": list(getattr(correctness, "weights", []))}


@dataclass
class RagasParts:
    """The Ragas pieces the stage uses; tests pass stubs.

    Attributes:
        require: Returns the Ragas version, given the ``--ragas-venv`` folder.
        judge: Builds the judge from the plan settings: ``(send, built values)``.
        embeddings: Builds the embeddings from the endpoint and router model name.
        metrics: Builds one worker's metric scorers over its seam: ``(scorers, weights)``.
        clock: Gives seconds for the call records.
    """

    require: Callable[[Path | None], str] = ragas_stage_lib.require_ragas
    judge: Callable[[Mapping[str, Any]], tuple[Any, dict]] = build_judge
    embeddings: Callable[[str, str], Any] = ragas_stage_lib.ragas_embeddings
    metrics: Callable[[Any, Any], tuple[dict[str, Any], dict]] = main_metrics
    clock: Callable[[], float] = time.perf_counter
