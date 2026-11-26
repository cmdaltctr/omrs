"""Run the official FreshStack ``alpha_ndcg`` on one input file (RDY 16.3).

Usage (inside the scorer venv, never the project venv)::

    <scorer venv>/bin/python -I alpha_runner35.py INPUT.json OUTPUT.json

``alphandcg35.py`` writes INPUT and reads OUTPUT. The runner checks the
SHA-256 of the official ``metrics.py`` against the pin before it imports it,
and the pin's alpha against 0.5, the ``pyndeval`` default that ``alpha_ndcg``
uses (it passes no alpha). ``metrics.py`` imports ``pytrec_eval`` at the top
for its recall and nDCG functions; ``alpha_ndcg`` does not use it, so an empty
stand-in module takes its place and nothing else is installed. Standard
library only.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import sys
import types
from pathlib import Path

#: The ``pyndeval.RelevanceEvaluator`` default; ``alpha_ndcg`` passes no alpha.
OFFICIAL_ALPHA = 0.5


def _version() -> str | None:
    module = sys.modules.get("pyndeval")
    found = getattr(module, "__version__", None)
    if found:
        return str(found)
    try:
        return importlib.metadata.version("pyndeval")
    except importlib.metadata.PackageNotFoundError:
        return None


def main(argv: list[str]) -> int:
    """Score every setup of the input file; write values or the refusal; return 0 or 2."""
    source, target = Path(argv[1]), Path(argv[2])
    task = json.loads(source.read_text(encoding="utf-8"))
    metrics = Path(task["metrics"])
    digest = hashlib.sha256(metrics.read_bytes()).hexdigest()
    if digest != task["sha256"]:
        out = {"refused": f"metrics.py SHA-256 {digest} is not the pin {task['sha256']}"}
    elif task["alpha"] != OFFICIAL_ALPHA:
        out = {"refused": f"alpha {task['alpha']} is not the official {OFFICIAL_ALPHA}"}
    else:
        sys.modules.setdefault("pytrec_eval", types.ModuleType("pytrec_eval"))
        spec = importlib.util.spec_from_file_location("freshstack_metrics", metrics)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        name = f"alpha-nDCG@{task['k']}"
        values = {
            setup: module.alpha_ndcg(task["qrels"], run["nuggets"], run["results"], [task["k"]])[
                name
            ]
            for setup, run in task["runs"].items()
        }
        out = {"values": values, "pyndeval": _version(), "python": sys.version.split()[0]}
    target.write_text(json.dumps(out, sort_keys=True), encoding="utf-8")
    return 2 if "refused" in out else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
