"""Live wiring of the Experiment 35 stage runner: router, run guard, machine, Engine and judges.

``run_arms.py`` reaches the outside world only through one ``LiveDeps``
object; tests pass a stub with the same methods.

* Router: Experiment 48's ``router_config.start_router`` joins OMRS's managed
  router (``llamacpp_router_server: managed`` in the scratch ``omrs.jsonc``)
  and loads the named files. The router stops when the process exits.
* Guard: every stage calls ``run_guard.guard_run`` with ``check_args=True``
  (task 5.8), the pre-freeze and smoke flags, and the command with every
  resolved concurrency value (design D7). The guard checks the live server
  against the plan (build, GGUF SHA-256, server arguments) and appends one
  line to ``output/run-records.jsonl``. A main stage refuses an empty
  ``frozen`` or a dirty tree.
* Machine: the host name, ``RUNPOD_POD_ID``, the GPU model from ``nvidia-smi``
  and the image from ``EXP35_POD_IMAGE`` (design D19). A field that cannot be
  read is ``None``, and the stage then refuses.
* Judges: one claim judge per strategy, on a copy of the answer block, built
  by ``compose_judges``. ``chat`` wraps GLM-5.3 in OMRS's production chat
  strategy.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import arms
import datasets35
from experiments._lib import run_guard
from experiments._lib.manifest import git_commit

EXP_DIR = Path(__file__).resolve().parent
EXP48_DIR = EXP_DIR.parent / "48-pipeline-sweep-llamacpp-2026-11-01"


def _gpu() -> str | None:
    try:
        found = subprocess.run(  # noqa: S603 - fixed command, no shell
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    names = sorted({line.strip() for line in found.stdout.splitlines() if line.strip()})
    return ", ".join(names) or None


class LiveDeps:
    """The outside world of one runner process."""

    def plan(self) -> dict[str, Any]:
        """Return the parsed ``plan.json``."""
        return json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))

    def commit(self) -> str:
        """Return the harness commit (``git rev-parse HEAD``)."""
        found = git_commit(EXP_DIR)
        if found is None:
            raise arms.ArmConfigError("git cannot report the harness commit; run inside the repo")
        return found

    def verify_inputs(
        self, root: Path, dataset: str, files: Sequence[Path], plan: Mapping[str, Any]
    ) -> None:
        """Check the recorded input hashes, and the FinanceBench PDFs against their manifest."""
        datasets35.verify_inputs(root, datasets35.input_hashes(dataset, plan))
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

    def guard(
        self, block: Any, *, base_url: str, command: str, prefreeze: bool, smoke: bool
    ) -> Any:
        """Validate the runtime block and run ``guard_run`` with ``check_args=True``."""
        from omrs.core.experiment_records.runtime_block import RuntimeBlock

        return run_guard.guard_run(
            EXP_DIR,
            RuntimeBlock.model_validate(block),
            base_url=base_url,
            command=command,
            check_args=True,
            prefreeze=prefreeze,
            smoke=smoke,
        )

    def machine(self) -> dict[str, Any]:
        """Return the host name, pod ID, GPU model and pinned image of this machine."""
        return {
            "host": socket.gethostname(),
            "pod_id": os.environ.get("RUNPOD_POD_ID") or None,
            "gpu": _gpu(),
            "image": os.environ.get("EXP35_POD_IMAGE") or None,
        }

    def engine(self) -> Any:
        """Build an Engine on the scratch settings."""
        from omrs.compose import build_engine

        return build_engine()

    def judge(self, name: str, settings: Any, plan: Any) -> Any:
        """Build OMRS's claim judge *name* on a copy of the answer block.

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
        """Run the runner again in a new process; return its exit code."""
        script = EXP_DIR / "run_arms.py"
        return subprocess.run([sys.executable, str(script), *argv], check=False).returncode  # noqa: S603
