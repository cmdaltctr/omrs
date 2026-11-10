"""Ragas judging stage and its one chat seam (Experiment 35 pre-freeze, master task 6.3).

Every judge call goes through one seam: ``await send(prompt) -> ChatReply``.
:class:`RecordingSeam` records the host, tokens and seconds of each call,
and the Ragas adapter only sees the seam. So tests and the cost accounting
do not depend on Ragas internals.

Ragas is imported lazily, inside the functions that need it. It lives in a
separate pod venv, never in the repository environment.

What was checked against the Ragas docs (Context7, ``/vibrantlabsai/ragas``,
2026-11-09): ``ragas.llms.base.InstructorBaseRagasLLM`` with abstract
``generate(prompt, response_model)`` and ``agenerate(prompt, response_model)``;
``ragas.metrics.collections`` ``Faithfulness``, ``AnswerRelevancy(llm,
embeddings)``, ``ContextPrecision``, ``ContextRecall`` and their ``ascore``
keywords; ``result.value``; ``ragas.embeddings.OpenAIEmbeddings(client, model)``.
Inferred, not checked: that the collections metrics accept any subclass of
``InstructorBaseRagasLLM`` and only call ``agenerate`` from ``ascore``.
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from measure_lib import METRICS, REFERENCE_METRICS

RAGAS_VERSION = "0.4.3"
_PY = f"{sys.version_info.major}.{sys.version_info.minor}"
RAGAS_INSTALL = (
    f"Ragas {RAGAS_VERSION} is not installed for this Python. It must not go into the "
    "repository environment. On the pod, run:\n"
    f"  uv venv /workspace/ragas-venv --python {_PY}\n"
    "  uv pip install --python /workspace/ragas-venv/bin/python "
    f"ragas=={RAGAS_VERSION}\n"
    "then run this script again with --ragas-venv /workspace/ragas-venv."
)

#: A metric scorer: takes one sample (question, answer, contexts, reference), returns a score.
MetricFn = Callable[[Mapping[str, Any]], Awaitable[float]]


class RagasMissingError(RuntimeError):
    """Ragas cannot be imported, or its version is not :data:`RAGAS_VERSION`."""


class StructuredReplyError(RuntimeError):
    """The judge reply did not match the response model after every attempt."""


@dataclass(frozen=True)
class ChatReply:
    """One judge reply: text plus what the call cost and which host served it."""

    text: str
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    cost_usd: float | None
    host: str | None
    host_in_list: bool | None
    temperature: float | None
    seed: int | None


ChatSeam = Callable[[str], Awaitable[ChatReply]]


@dataclass
class RecordingSeam:
    """The one seam every judge call goes through. Records ids and numbers, never text.

    Attributes:
        send: Sends one chat request.
        metric: The metric the next calls belong to.
        calls: One record per call.
    """

    send: ChatSeam
    metric: str = ""
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, prompt: str) -> str:
        """Send *prompt*, record the call and return the reply text."""
        started = time.perf_counter()
        try:
            reply = await self.send(prompt)
        except Exception as exc:
            # Only the type: a message can carry prompt text.
            self.calls.append(
                {
                    "metric": self.metric,
                    "error": type(exc).__name__,
                    "seconds": round(time.perf_counter() - started, 3),
                }
            )
            raise
        self.calls.append(
            {
                "metric": self.metric,
                "error": "",
                "seconds": round(time.perf_counter() - started, 3),
                "input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens,
                "reasoning_tokens": reply.reasoning_tokens,
                "reported_cost_usd": reply.cost_usd,
                "host": reply.host,
                "host_in_list": reply.host_in_list,
                "temperature": reply.temperature,
                "seed": reply.seed,
            }
        )
        return reply.text


def omrs_chat_seam(llm: Any, provider: str = "openrouter") -> ChatSeam:
    """Return a seam over an OMRS-built LLM; usage and host come from OMRS's own readers."""
    from omrs.engine_answer import reply_reader, sampling_record

    read = reply_reader(provider)

    async def send(prompt: str) -> ChatReply:
        completion = await llm.acomplete(prompt)
        raw = getattr(completion, "raw", None)
        try:
            facts = read(raw)
        except Exception:  # noqa: BLE001 - a reader failure counts the call with no figures
            facts = None
        record = sampling_record(llm, provider, raw)
        return ChatReply(
            text=str(getattr(completion, "text", "") or ""),
            input_tokens=getattr(facts, "input_tokens", None),
            output_tokens=getattr(facts, "output_tokens", None),
            reasoning_tokens=getattr(facts, "reasoning_tokens", None),
            cost_usd=getattr(facts, "cost_usd", None),
            host=record.get("host"),
            host_in_list=record.get("host_in_list"),
            temperature=record.get("temperature"),
            seed=record.get("seed"),
        )

    return send


# --- structured replies ---------------------------------------------------------


def _json_part(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


async def structured(seam: RecordingSeam, prompt: str, response_model: Any, attempts: int = 2):
    """Ask for JSON matching *response_model* through *seam*; retry a bad reply once.

    The prompt names the JSON schema, so no ``response_format`` field is sent
    (a pinned host with ``require_parameters`` might not take it).

    Raises:
        StructuredReplyError: No attempt gave a reply the model accepts.
    """
    schema = json.dumps(response_model.model_json_schema())
    ask = (
        f"{prompt}\n\nReturn only one JSON object that matches this JSON schema, "
        f"with no other text:\n{schema}"
    )
    for attempt in range(attempts):
        text = await seam(
            ask
            if attempt == 0
            else f"{ask}\n\nYour last reply did not match the schema. Try again."
        )
        try:
            return response_model.model_validate_json(_json_part(text))
        except ValueError:
            continue
    raise StructuredReplyError(f"no reply matched {response_model.__name__}")


# --- Ragas (lazy) ---------------------------------------------------------------


def ragas_site(venv: Path) -> Path:
    """Return the ``site-packages`` folder of *venv* for this Python.

    Raises:
        RagasMissingError: *venv* has no folder for this Python version.
    """
    site = Path(venv) / "lib" / f"python{_PY}" / "site-packages"
    if not site.is_dir():
        raise RagasMissingError(f"{site} does not exist.\n{RAGAS_INSTALL}")
    return site


def require_ragas(venv: Path | None = None) -> str:
    """Return the Ragas version, after adding *venv* to the end of ``sys.path``.

    Appending (not prepending) keeps the repository's own packages first.

    Raises:
        RagasMissingError: Ragas does not import, or it is not :data:`RAGAS_VERSION`.
    """
    if venv is not None:
        site = str(ragas_site(venv))
        if site not in sys.path:
            sys.path.append(site)
    try:
        import ragas
    except ImportError as exc:
        raise RagasMissingError(RAGAS_INSTALL) from exc
    except Exception as exc:  # noqa: BLE001 - a broken dependency must give a plain message
        raise RagasMissingError(
            f"Ragas did not import: {type(exc).__name__}: {exc}\n{RAGAS_INSTALL}"
        ) from exc
    version = str(getattr(ragas, "__version__", ""))
    if version != RAGAS_VERSION:
        raise RagasMissingError(
            f"Ragas {version} is installed; the protocol fixes {RAGAS_VERSION}.\n{RAGAS_INSTALL}"
        )
    return version


def ragas_llm(seam: RecordingSeam) -> Any:
    """Return a Ragas LLM whose every call goes through *seam*."""
    from ragas.llms.base import InstructorBaseRagasLLM

    class SeamLLM(InstructorBaseRagasLLM):
        """Ragas LLM over the recording seam (structured replies by JSON schema prompt)."""

        def generate(self, prompt: str, response_model: Any) -> Any:
            raise RuntimeError("this measurement scores with ascore only")

        async def agenerate(self, prompt: str, response_model: Any) -> Any:
            return await structured(seam, prompt, response_model)

    return SeamLLM()


def ragas_embeddings(base_url: str, model: str) -> Any:
    """Return Ragas embeddings over the OMRS router (local Qwen3-Embedding-4B; no cost)."""
    from openai import AsyncOpenAI
    from ragas.embeddings import OpenAIEmbeddings

    return OpenAIEmbeddings(
        client=AsyncOpenAI(base_url=base_url, api_key="local-router"), model=model
    )


def ragas_metrics(llm: Any, embeddings: Any) -> dict[str, MetricFn]:
    """Return the four Ragas 0.4.3 collections metrics as sample scorers."""
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
    )

    faith, relevancy = Faithfulness(llm=llm), AnswerRelevancy(llm=llm, embeddings=embeddings)
    precision, recall = ContextPrecision(llm=llm), ContextRecall(llm=llm)

    async def _value(pending: Awaitable[Any]) -> float:
        return float((await pending).value)

    return {
        "faithfulness": lambda s: _value(
            faith.ascore(
                user_input=s["question"], response=s["answer"], retrieved_contexts=s["contexts"]
            )
        ),
        "answer_relevancy": lambda s: _value(
            relevancy.ascore(user_input=s["question"], response=s["answer"])
        ),
        "context_precision": lambda s: _value(
            precision.ascore(
                user_input=s["question"], reference=s["reference"], retrieved_contexts=s["contexts"]
            )
        ),
        "context_recall": lambda s: _value(
            recall.ascore(
                user_input=s["question"], retrieved_contexts=s["contexts"], reference=s["reference"]
            )
        ),
    }


# --- one answer -----------------------------------------------------------------


def _metric_record(score: float | None, calls: list[dict], seconds: float, error: str) -> dict:
    def total(name: str) -> int:
        return sum(int(c.get(name) or 0) for c in calls)

    return {
        "score": score,
        "calls": len(calls),
        "seconds": round(seconds, 3),
        "error": error,
        "input_tokens": total("input_tokens"),
        "output_tokens": total("output_tokens"),
        "reasoning_tokens": total("reasoning_tokens"),
        "unreported_calls": sum(
            1 for c in calls if c.get("input_tokens") is None or c.get("output_tokens") is None
        ),
    }


async def judge_answer(
    sample: Mapping[str, Any],
    seam: RecordingSeam,
    metrics: Mapping[str, MetricFn],
    *,
    header: Mapping[str, Any],
) -> dict[str, Any]:
    """Score one answer with each metric in turn; return its ids-and-numbers row.

    Metrics run one after another, so each call belongs to the metric that
    was running. A failed metric keeps its calls and records the error type
    only (a message can carry judge text).
    """
    seam.calls = []
    rows: dict[str, Any] = {}
    for name in [m for m in METRICS if m in metrics]:
        seam.metric, first, started = name, len(seam.calls), time.perf_counter()
        score, error = None, ""
        if name in REFERENCE_METRICS and not sample.get("reference"):
            error = "no reference answer"
        else:
            try:
                score = await metrics[name](sample)
            except Exception as exc:  # noqa: BLE001 - record and continue
                error = type(exc).__name__
            if score is not None and math.isnan(score):
                score, error = None, "score is NaN"
        rows[name] = _metric_record(score, seam.calls[first:], time.perf_counter() - started, error)
    return {**header, "qid": sample["qid"], "error": "", "metrics": rows, "calls": list(seam.calls)}
