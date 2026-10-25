# Runner pattern: `run_eval.py`

One runner per experiment. It runs every cell on the same items, so the summariser can make paired comparisons. The pattern works for any project. Only three small functions touch the project's own code.

## What the runner does

1. Reads the ground truth. Stops if it is empty.
2. Appends one run record to `output/run-records.jsonl` through `experiments/_lib/run_record.py`. It does this on every start, including `--resume`. It never rewrites earlier lines.
3. Builds one configuration per cell. If the project has settings objects, it passes them in. It does not set env vars or patch module globals per cell unless the project offers no other way.
4. Runs each item under each cell and saves one raw row per item and cell.
5. Writes a checkpoint after each cell. `--resume` skips cells that are done.
6. Writes `output/raw.json`.

Keep flags to `--resume` and `--limit`. Add another flag only when a step in the plan uses it.

## The three project hooks

| Hook | Job | Find it by |
| --- | --- | --- |
| `setup()` | Start the project once: load config, open an experiment-local store | Repository `AGENTS.md`, existing experiments, the project's entry point |
| `build_cells()` | Return one configuration per cell, baseline first | The project's settings or config objects |
| `run_item(config, item, ctx)` | Run one item and return the raw result | The function the experiment tests (search, classify, generate) |

Everything else in the skeleton is project-neutral.

### Example: OMRS

| Hook | Uses |
| --- | --- |
| `setup()` | `omrs.compose.ensure_runtime_setup()`, a store from `experiments/_lib/storage.py` |
| `build_cells()` | `omrs.core.settings.EffectiveSettings(retrieval=RetrievalBlock(...))` |
| `run_item()` | `omrs.core.retrieval.pipeline.search(query, store=..., effective_settings=config)` |

For another project, replace these three rows. If the repository `AGENTS.md` names different entry points, follow it.

## Skeleton

```python
"""Experiment <N>: <title>. Runs every cell on the same items."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))  # adjust to the project layout
sys.path.insert(0, str(HERE.parent))  # for experiments/_lib

OUTPUT = HERE / "output"
GROUND_TRUTH = HERE / "ground-truth.json"
CHECKPOINT = OUTPUT / "checkpoint.json"
RAW = OUTPUT / "raw.json"


# --- project hooks: the only part that changes between projects ----------


def setup() -> Any:
    """Start the project once. Return anything run_item needs (store, client)."""
    raise NotImplementedError


def build_cells() -> dict[str, Any]:
    """Return one configuration per cell. Baseline first."""
    raise NotImplementedError


def run_item(config: Any, item: dict[str, Any], ctx: Any) -> Any:
    """Run one item under one configuration. Return the raw result."""
    raise NotImplementedError


# --- scoring: pure, tested in test_score.py ------------------------------


def score(item: dict[str, Any], result: Any) -> dict[str, Any]:
    """Turn one raw result into metric fields, for example hit_at_10 or flagged."""
    raise NotImplementedError


# --- project-neutral runner -----------------------------------------------


def run_cell(name: str, config: Any, items: list[dict[str, Any]], ctx: Any) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        started = time.perf_counter()
        result = run_item(config, item, ctx)
        rows.append(
            {
                "cell": name,
                "item_id": item["id"],
                "group": item.get("group"),  # document or topic, for grouped statistics
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                **score(item, result),
            }
        )
    return rows


def save_atomic(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    items = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))["items"][: args.limit]
    if not items:
        raise SystemExit(f"No items in {GROUND_TRUTH}")

    ctx = setup()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    done = json.loads(CHECKPOINT.read_text()) if args.resume and CHECKPOINT.exists() else {}
    for name, config in build_cells().items():
        if name in done:
            print(f"skip {name} (in checkpoint)", file=sys.stderr)
            continue
        print(f"run {name} on {len(items)} items", file=sys.stderr)
        done[name] = run_cell(name, config, items, ctx)
        save_atomic(CHECKPOINT, done)

    save_atomic(RAW, {"experiment": HERE.name, "n_items": len(items), "cells": done})
    print(f"wrote {RAW}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

## Notes

- Every cell has one row per item, with the same `item_id`. The summariser pairs rows by `item_id`.
- Put a `group` on each row when items share a document or a topic. Medium and expert statistics use it.
- Print progress to stderr. On an MCP server project, stdout is the protocol channel.
- Clear any query cache between cells if the project has one.
- The shape is the same for retrieval, classification and generation experiments. Only `run_item` and `score` change.
- For LLM calls with randomness (expert level), run each item 3 or more times and store the mean per item.
