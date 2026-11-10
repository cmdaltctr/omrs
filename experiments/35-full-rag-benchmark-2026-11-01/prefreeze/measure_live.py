"""Live wiring of the 20-answer measurement: Experiment 48 Part A code, OMRS and the router.

Only ``measure_answers.main`` imports this module. It reuses Experiment 48's
own code by importing it from its folder (``run_part_a``, ``router_config``),
as Experiment 48's scripts do, and edits nothing there:

* inputs come from Experiment 48's pod layout (``corpus/``, ``ground-truth.json``,
  ``output/financebench/``), read only and hash-checked against its ``plan.json``;
* scratch settings, router state and LanceDB go under ``--out-dir``: the
  module constants ``router_config.CONFIG_DIR`` and ``STATE_DIR`` are re-pointed
  before OMRS reads any setting, the same way Experiment 48's tests re-point
  ``OUTPUT``;
* Experiment 48's ``preflight`` is not called, because it writes Experiment 48's
  run record. Its parts are called here and the runtime record goes to
  ``<out-dir>/runtime.json``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import measure_lib as lib
import ragas_stage

HERE = Path(__file__).resolve().parent
EXP48_DIR = HERE.parent.parent / "48-pipeline-sweep-llamacpp-2026-11-01"


def _import_exp48(out: Path) -> tuple[Any, Any]:
    """Import Experiment 48's runner and router module; point the scratch folders at *out*."""
    if str(EXP48_DIR) not in sys.path:
        sys.path.insert(0, str(EXP48_DIR))
    # Importing run_part_a sets Experiment 48's environment: LanceDB store, the
    # Qwen3-Embedding-4B tokenizer and revision, metadata extraction and claim check off.
    import router_config
    import run_part_a

    router_config.OUTPUT = out
    router_config.CONFIG_DIR = out / "config"
    router_config.STATE_DIR = out / "state"
    router_config.prepare_environment({"LANCEDB_URI": str(out / "lancedb")})
    return run_part_a, router_config


class Wiring:
    """Builds the scratch settings and the real stage functions for one run."""

    def __init__(
        self, *, out_dir: Path, answer_host: str, judge_host: str, collection: str
    ) -> None:
        self.out = out_dir
        self.answer_host = answer_host
        self.judge_host = judge_host
        self.collection = collection
        self.part_a, self.rc = _import_exp48(out_dir)
        self.plan = json.loads((EXP48_DIR / "plan.json").read_text(encoding="utf-8"))
        self.embed = self.rc.plan_model(self.plan, self.part_a.BASELINE_MODEL)

    def question_pool(self) -> list[dict]:
        """Return Part A's questions: 17 from Experiment 2, then the frozen FinanceBench ones."""
        try:
            return lib.question_pool(self.part_a.load_questions(), self.part_a.load_financebench())
        except FileNotFoundError as exc:
            raise SystemExit(
                f"Part A input missing: {exc.filename}. Run Experiment 48's "
                "pod_setup.sh and prepare_financebench.py first."
            ) from exc

    def values(self) -> dict[str, Any]:
        """Return the scratch ``omrs.jsonc`` values (Experiment 48 D2, answers on OpenRouter)."""
        from omrs.core.answer.settings import normalise_hosts

        # The plan's chat model stays listed (as in Part A) so OMRS's classification role
        # has its entry; a blank llamacpp_chat_model falls back to the default, which has
        # none. The router never loads it: answers go to OpenRouter, extraction is off.
        chat = self.rc.chat_model(self.plan)
        return {
            "embed_provider": "llamacpp",
            "local_backend": "llamacpp",
            "llamacpp_router_server": "managed",
            "llamacpp_router_url": self.rc.ROUTER_URL,
            "llamacpp_embed_model": self.rc.model_name(self.embed),
            "llamacpp_chat_model": self.rc.model_name(chat),
            "llamacpp_models": self.rc.model_entries(
                {"runtime": {"models": [self.embed, chat]}}, self.rc.gguf_dir()
            ),
            "answer": {
                "provider": "openrouter",
                "model": lib.ANSWER_MODEL,
                "temperature": lib.TEMPERATURE,
                "seed": lib.SEED,
                "allowed_hosts": normalise_hosts(self.answer_host),
                "verify_claims": False,
            },
        }

    def configure(self) -> Path:
        """Write and check the scratch settings file; return its path."""
        values = self.values()
        path = self.rc.write_settings(values, self.rc.CONFIG_DIR)
        self.rc.check_settings_file(self.rc.CONFIG_DIR)
        self.rc.check_resolved(self.rc.load_settings(), values)
        return path

    def print_plan(self, settings_path: Path, stages: Sequence[str], qids: list[str]) -> int:
        """Print what a live run would do; return 1 when OMRS lists role problems."""
        settings = self.rc.load_settings()
        summary = self.rc.dry_run_summary(settings)
        summary.update(
            {
                "settings_file": str(settings_path),
                "out_dir": str(self.out),
                "collection": self.collection,
                "stages": list(stages),
                "answer_temperature": settings.answer.temperature,
                "answer_seed": settings.answer.seed,
                "answer_allowed_hosts": settings.answer.allowed_hosts,
                "judge": {
                    "model": lib.JUDGE_MODEL,
                    "reasoning": lib.JUDGE_REASONING,
                    "temperature": lib.TEMPERATURE,
                    "seed": lib.SEED,
                    "allowed_hosts": self.judge_host,
                },
                "documents": [p.name for p in self.part_a.fixed_set_documents(self.plan)],
                "question_ids": qids,
            }
        )
        print("[dry-run] nothing started, nothing sent", flush=True)
        print(json.dumps(summary, indent=2), flush=True)
        return 1 if summary["role_problems"] else 0

    def preflight(self) -> None:
        """Hash-check the inputs, check chunking, start the router, record the runtime."""
        from omrs.compose import get_settings
        from omrs.core.experiment_records.runtime_block import RuntimeBlock

        maps = self.part_a.frozen_paths(self.plan)
        self.part_a.verify_input_hashes(self.part_a.EXP_DIR, maps["gt"])
        self.part_a.verify_input_hashes(self.part_a.EXP_DIR / "corpus", maps["corpus"])
        self.part_a.verify_input_hashes(self.part_a.OUTPUT / "financebench/pdfs", maps["pdfs"])
        settings = get_settings()
        self.part_a.chunking_guard(settings)
        self.rc.start_router([self.part_a.BASELINE_MODEL], self.plan)
        block = json.loads(json.dumps(self.plan["runtime"]))
        block["models"] = [m for m in block["models"] if m["file"] == self.embed["file"]]
        found = self.part_a.verify_llamacpp_runtime(
            RuntimeBlock.model_validate(block), base_url=self.rc.verify_url(settings)
        )
        lib.write_json_atomic(self.out / "runtime.json", found.as_run_record())

    def judge(self, ragas_version: str) -> tuple[Any, Any, dict[str, Any]]:
        """Build the judge through OMRS's judge builder (host check runs here) and the metrics."""
        from omrs.compose import get_settings
        from omrs.compose_answer import build_verify_llm
        from omrs.core.answer.settings import normalise_hosts

        settings = get_settings()
        hosts = normalise_hosts(self.judge_host)
        block = settings.answer.model_copy(
            update={
                "verify_claims": True,
                "verify_provider": "openrouter",
                "verify_model": lib.JUDGE_MODEL,
                "verify_reasoning": lib.JUDGE_REASONING,
                "verify_temperature": lib.TEMPERATURE,
                "verify_seed": lib.SEED,
                "verify_allowed_hosts": hosts,
            }
        )
        llm = build_verify_llm(settings, answer_block=block)
        if llm is None:
            raise RuntimeError("OMRS built no judge: llama-index-llms-openai-like is missing")
        seam = ragas_stage.RecordingSeam(ragas_stage.omrs_chat_seam(llm, "openrouter"))
        embeddings = ragas_stage.ragas_embeddings(
            self.rc.ROUTER_URL, self.rc.model_name(self.embed)
        )
        metrics = ragas_stage.ragas_metrics(ragas_stage.ragas_llm(seam), embeddings)
        header = {
            "judge_model": lib.JUDGE_MODEL,
            "temperature": lib.TEMPERATURE,
            "seed": lib.SEED,
            "reasoning": lib.JUDGE_REASONING,
            "judge_allowed_hosts": hosts,
            "ragas_version": ragas_version,
        }
        return seam, metrics, header

    def run(
        self,
        opts: Any,
        questions: list[dict],
        ragas_venv: Path | None,
        run_stages: Callable[..., Any],
        deps_type: Callable[..., Any],
    ) -> int:
        """Check Ragas first, start the router, run the stages, close the engine."""
        version = ""
        if "ragas" in opts.stages:
            try:
                version = ragas_stage.require_ragas(ragas_venv)
            except ragas_stage.RagasMissingError as exc:
                print(f"[ragas] {exc}", file=sys.stderr, flush=True)
                return 2
        if set(opts.stages) - {"summary"}:
            self.preflight()
        holder: dict[str, Any] = {}

        def engine() -> Any:
            if "engine" not in holder:
                holder["engine"] = self.part_a.engine_factory(self.collection)()
            return holder["engine"]

        async def answer(text: str) -> dict:
            return await engine().answer(text, top_k=10, collection_name=self.collection)

        def ingest() -> list[dict]:
            return run_ingest_off_loop(
                lambda: self.part_a.ingest_documents(
                    self.part_a.engine_factory(self.collection),
                    None,
                    self.collection,
                    plan=self.plan,
                )
            )

        deps = deps_type(
            answer=answer,
            ingest=ingest,
            judge=lambda: self.judge(version),
            require_ragas=lambda: version,
        )
        try:
            return asyncio.run(run_stages(opts, deps, questions))
        finally:
            if "engine" in holder:
                holder["engine"].close()


def run_ingest_off_loop(fn: Callable[[], list[dict]]) -> list[dict]:
    """Run *fn* in its own thread and wait for it.

    Experiment 48's ``ingest_documents`` calls ``asyncio.run()``, which refuses to start
    inside the event loop the measure stages already run in (pod run 2026-11-10).
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(fn).result()
