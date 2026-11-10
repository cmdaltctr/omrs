"""Live wiring of the Experiment 35 arm runner: router, runtime guard, Engine and judges.

``run_arms.py`` takes these through one object, so the tests pass a stub and
nothing here runs under test except :func:`guard_stage`.

* Router: Experiment 48's ``router_config.start_router`` joins OMRS's managed
  router (``llamacpp_router_server: managed`` in the scratch ``omrs.jsonc``)
  and loads the named files. The router stops when the process exits.
* Guard: before any stage, the live server is checked against the plan
  (build and GGUF SHA-256). A full run calls ``run_guard.guard_run``, which
  appends the experiment's run record. A smoke run (``--limit``) checks the
  same way but writes the found runtime into its output folder: it is not a
  measured run, and the Confirmatory rule needs the freeze commit before the
  first line of ``output/run-records.jsonl`` (task 4.2).
* Judges: one claim judge per strategy, from a copy of the answer block
  (archived change D10), built by ``compose_judges``. ``chat`` wraps the
  GLM-5.3 LLM in OMRS's production chat strategy, as the pre-freeze runner did.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import arms
import datasets35
from experiments._lib import run_guard
from experiments._lib.llamacpp_runtime import verify_llamacpp_runtime

EXP_DIR = Path(__file__).resolve().parent
EXP48_DIR = EXP_DIR.parent / "48-pipeline-sweep-llamacpp-2026-11-01"


def guard_stage(
    block: Any,
    *,
    base_url: str,
    smoke: bool,
    runtime_path: Path,
    verify: Callable[..., Any] = verify_llamacpp_runtime,
    guard_run: Callable[..., Any] = run_guard.guard_run,
) -> Any:
    """Check the live server against the plan; record the found runtime.

    Raises:
        PreflightError: The build or a GGUF hash differs. Nothing is written.
    """
    if smoke:
        found = verify(block, base_url=base_url)
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = runtime_path.with_name(runtime_path.name + ".tmp")
        tmp.write_text(json.dumps(found.as_run_record(), indent=2) + "\n", encoding="utf-8")
        tmp.replace(runtime_path)
        return found
    return guard_run(EXP_DIR, block, base_url=base_url, command=None)


class LiveDeps:
    """The real outside world of one runner process."""

    def plan(self) -> dict[str, Any]:
        """Return the parsed ``plan.json``."""
        return json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))

    def verify_inputs(self, root: Path, dataset: str, files: Sequence[Path]) -> None:
        """Check the recorded input hashes, and each FinanceBench PDF against its manifest."""
        datasets35.verify_inputs(root, datasets35.EXPECTED_SHA256[dataset])
        if dataset == "financebench":
            datasets35.verify_inputs(root, datasets35.pdf_hashes(root, files))

    def chunking_token_aware(self, settings: Any) -> bool:
        """Return whether OMRS resolves the model-token-aware Markdown path."""
        from omrs.core.chunking.model_token import resolve_markdown_chunking

        return bool(resolve_markdown_chunking(settings).model_token_aware)

    def start_router(self, files: Sequence[str], plan: Any) -> Any:
        """Join OMRS's managed router and load *files* (Experiment 48's helper)."""
        if str(EXP48_DIR) not in sys.path:
            sys.path.insert(0, str(EXP48_DIR))
        import router_config

        return router_config.start_router(list(files), plan)

    def guard(self, block: Any, *, base_url: str, smoke: bool, runtime_path: Path) -> Any:
        """Validate the runtime block, then run :func:`guard_stage`."""
        from omrs.core.experiment_records.runtime_block import RuntimeBlock

        model = RuntimeBlock.model_validate(block)
        return guard_stage(model, base_url=base_url, smoke=smoke, runtime_path=runtime_path)

    def engine(self) -> Any:
        """Build an Engine from the scratch settings."""
        from omrs.compose import build_engine

        return build_engine()

    def judge(self, name: str, settings: Any, plan: Any) -> Any:
        """Build OMRS's claim judge *name* from a copy of the answer block.

        Raises:
            ArmConfigError: OMRS says the strategy cannot run, or builds no judge.
        """
        from omrs.compose_judges import build_judge_target, chat_judge, strategy_ready

        block = arms.judge_block(settings.answer, name, plan)
        reason = strategy_ready(settings, name, block)
        if reason:
            raise arms.ArmConfigError(f"OMRS says {name} cannot run: {reason}")
        target = build_judge_target(settings, block)
        if name == "chat":
            from omrs.engine_answer import server_seam

            if target is None or not hasattr(target, "acomplete"):
                raise arms.ArmConfigError("OMRS built no chat judge LLM from the scratch settings")
            provider = str(block.verify_provider)
            target = chat_judge(target, block, provider, lambda inner: server_seam(inner))
        if target is None or getattr(target, "name", None) != name:
            raise arms.ArmConfigError(f"OMRS built no {name} claim judge from the scratch settings")
        return target

    def spawn(self, argv: Sequence[str]) -> int:
        """Run this script again in a new process; return its exit code."""
        script = EXP_DIR / "run_arms.py"
        return subprocess.run([sys.executable, str(script), *argv], check=False).returncode  # noqa: S603
