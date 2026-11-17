"""Stand-ins for the Experiment 35 Ragas stage tests (``test_experiment35_ragas*.py``).

No Ragas, no router, no network: a scripted chat seam, stub metrics, a router
that counts sessions and a runtime check that returns fixed values.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tests._exp35_fixtures import load

ragas35 = load("ragas35")
ragas_stage = ragas35.ragas_stage_lib

EMBED_FILE = "Qwen3-Embedding-4B-Q8_0.gguf"
JUDGE = {
    "role": "ragas-judge",
    "provider": "openrouter",
    "model": "openai/gpt-oss-120b",
    "host": "hostj",
    "reasoning": "low",
    "temperature": 0.0,
    "seed": 20261109,
}


def plan(**judge: Any) -> dict[str, Any]:
    """A plan with the Ragas judge reference and the 4B and 8B embedding files."""
    models = [
        {
            "role": "embedding-baseline-4b",
            "repository": "Qwen/Qwen3-Embedding-4B-GGUF",
            "file": EMBED_FILE,
            "sha256": "a" * 64,
            "build": 11941,
        },
        {
            "role": "embedding-8b",
            "repository": "Qwen/Qwen3-Embedding-8B-GGUF",
            "file": "Qwen3-Embedding-8B-Q8_0.gguf",
            "sha256": "b" * 64,
        },
    ]
    return {"runtime": {"models": models, "references": [{**JUDGE, **judge}]}}


class Status429(Exception):
    """A rate-limit error as the openai client raises it."""

    status_code = 429


class APIConnectionError(Exception):
    """A connection error with no status code."""


class Script:
    """The chat seam. ``fail`` maps ``(metric, qid)`` to an exception class raised on every call."""

    def __init__(self, fail: dict[tuple[str, str], type[Exception]] | None = None) -> None:
        self.fail = dict(fail or {})
        self.prompts: list[str] = []
        self.events: list[str] | None = None

    async def __call__(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        if self.events is not None:
            self.events.append("chat")
        await asyncio.sleep(0)
        metric, qid = prompt.split("|")
        exc = self.fail.get((metric, qid))
        if exc is not None:
            raise exc("lost")
        return ragas_stage.ChatReply(
            text="x",
            input_tokens=100,
            output_tokens=10,
            reasoning_tokens=2,
            cost_usd=None,
            host="hostj",
            host_in_list=True,
            temperature=0.0,
            seed=20261109,
            model_returned="openai/gpt-oss-120b",
            provider_returned="hostj",
        )


class Embeddings:
    """Stub embeddings; checks a router session is open at every call."""

    def __init__(self, router: Router) -> None:
        self.router = router
        self.calls = 0

    async def embed(self) -> None:
        assert self.router.open == 1, "embedding call outside the router session"
        self.router.events.append("embed")
        self.calls += 1


def stub_metrics(seam: Any, embeddings: Embeddings) -> tuple[dict[str, Any], dict[str, Any]]:
    """Five metrics; each makes ``1 + index`` seam calls for its answer, with yields between."""

    def metric(name: str, uses_embeddings: bool) -> Any:
        async def score(sample: dict[str, Any]) -> float:
            for _ in range(1 + int(sample["qid"][1:]) % 3):
                await seam(f"{name}|{sample['qid']}")
                await asyncio.sleep(0)
            if uses_embeddings:
                await embeddings.embed()
            return 0.25 + 0.5 * (len(sample["answer"]) % 2)

        return score

    names = ragas35.METRICS
    fns = {n: metric(n, n in ("ragas_answer_relevancy", "ragas_answer_correctness")) for n in names}
    return fns, {"answer_correctness": [0.75, 0.25]}


class Router:
    """Counts router sessions and the files asked for."""

    def __init__(self) -> None:
        self.open = 0
        self.opened = 0
        self.closed = 0
        self.files: list[str] = []
        self.events: list[str] = []

    @contextmanager
    def __call__(self, entry: dict[str, Any]):
        self.files.append(entry["file"])
        self.open += 1
        self.opened += 1
        self.events.append("open")
        try:
            yield "http://127.0.0.1:18080/v1"
        finally:
            self.open -= 1
            self.closed += 1
            self.events.append("close")


def runtime_ok(entry: dict[str, Any], base_url: str) -> dict[str, Any]:
    """A runtime check that finds the planned build and hash."""
    return {"build": 11941, "sha256": "a" * 64}


def built(**change: Any) -> dict[str, Any]:
    """The judge values a built judge reports (the plan values unless changed)."""
    values = {k: JUDGE[k] for k in ("model", "host", "reasoning", "temperature", "seed")}
    return {**values, **change}


def parts(script: Script, router: Router, **change: Any) -> Any:
    """Ragas parts over the stubs, with a fixed clock."""
    values = {
        "require": lambda venv: "0.4.3",
        "judge": lambda settings: (script, built()),
        "embeddings": lambda url, model: Embeddings(router),
        "metrics": stub_metrics,
        "clock": lambda: 0.0,
    }
    return ragas35.RagasParts(**{**values, **change})


QIDS = [f"q{i}" for i in range(6)]


def answer_row(qid: str, text: str = "", error: str | None = None) -> dict[str, Any]:
    """One answer row as the answer stage writes it."""
    return {
        "qid": qid,
        "answer": text if text or error else f"Answer to {qid} [1].",
        "evidence": [{"ordinal": 1, "text": f"Passage for {qid}", "chunk_id": "c1"}],
        "error": error,
    }


def write_answers(run_dir: Path, rows: list[dict[str, Any]], *, done: bool = True) -> None:
    """Write ``answer.jsonl`` and, when *done*, its done-marker."""
    run_dir.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r) + "\n" for r in rows)
    (run_dir / "answer.jsonl").write_text(text, encoding="utf-8")
    if done:
        (run_dir / ".done-answer.json").write_text("{}", encoding="utf-8")


def ctx(run_dir: Path, qids: list[str], router: Router, **args: Any) -> Any:
    """The stand-in stage context (the fields ``ragas_stage`` reads)."""
    values = {
        "ragas_host": "hostj",
        "ragas_venv": None,
        "ragas_concurrency": 1,
        "rate_limit_attempts": 2,
        "dry_run": False,
    }
    questions = [
        SimpleNamespace(qid=q, text=f"Question {q}?", reference=f"Reference {q}.") for q in qids
    ]
    return SimpleNamespace(
        run_dir=run_dir,
        setup="e4b-c512-roff-hoff",
        questions=questions,
        key={"seed": 20261101, "qids": qids},
        resume=False,
        args=SimpleNamespace(**{**values, **args}),
        router=router,
        runtime_check=runtime_ok,
    )


async def no_sleep(seconds: float) -> None:
    """The gate's sleep, without waiting."""


def run(c: Any, p: Any, plan_: dict[str, Any] | None = None) -> int:
    """Run the stage once; the gate never waits."""
    return asyncio.run(ragas35.ragas_stage(c, plan_ or plan(), parts=p, sleep=no_sleep))


def rows(run_dir: Path) -> list[dict[str, Any]]:
    """The saved rows of ``ragas.jsonl``."""
    path = run_dir / "ragas.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
