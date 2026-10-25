# Analysis Script Pattern

Use this as the canonical structure for `experiments/<id>/analysis.py`.

## Requirements

- Jupytext percent format (paired with gitignored `analysis.ipynb`)
- Load saved JSON results only — never run experiment logic or modify env vars
- Produce pandas DataFrame summaries and matplotlib plots
- Work both as a script (`python analysis.py`) and in Jupyter (`__file__` undefined)

## Skeleton

```python
# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: -all
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.16.0
#   kernelspec:
#     display_name: .venv
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Experiment <N> — <Title>
# <One-line description>

# %%
import json
from pathlib import Path

try:
    _ROOT = Path(__file__).parent
except NameError:
    _ROOT = Path.cwd()

import matplotlib.pyplot as plt
import pandas as pd

DATA = _ROOT / "eval_results.json"

with open(DATA) as f:
    raw = json.load(f)

# %% [markdown]
# ## Summary Table

# %%
df = pd.DataFrame(raw["summaries"])
df

# %% [markdown]
# ## Key Metric Comparison

# %%
fig, ax = plt.subplots(figsize=(8, 5))
ax.bar(df["label"], df["hit_rate_at_1"], color=["steelblue", "coral", "seagreen"][: len(df)])
ax.set_ylabel("Hit@1")
ax.set_title("Hit@1 by Configuration")
ax.tick_params(axis="x", rotation=30)
plt.tight_layout()
plt.show()
```

## Patterns

### Loading data

```python
# Single JSON file
DATA = _ROOT / "eval_results.json"
with open(DATA) as f:
    raw = json.load(f)

# Multiple JSON files (e.g., quickwins experiments)
configs = {}
for p in sorted(_ROOT.glob("eval_results.*.json")):
    with open(p) as f:
        configs[p.stem.split(".")[1]] = json.load(f)
```

### Building rows from nested JSON

```python
rows = []
for cell in raw["cells"]:
    queries = cell["queries"]
    latencies = [q["latency_ms"] for q in queries]
    rows.append(
        {
            "mode": cell["mode"],
            "rerank": cell["rerank"],
            "n_queries": len(queries),
            "hit_at_1": sum(1 for q in queries if q["hit_at_1"]) / len(queries),
            "mean_latency_ms": sum(latencies) / len(latencies),
        }
    )
df = pd.DataFrame(rows)
df
```

### Annotating scatter plots

```python
for _, row in df.iterrows():
    ax.annotate(
        str(row["label"]),
        (row["avg_latency_ms"], row["source_accuracy"]),
        fontsize=8,
        xytext=(5, 5),
        textcoords="offset points",
    )
```

### Boxplot with dict data

```python
data_by_label = {}
for cell in raw["cells"]:
    label = f"cache={'on' if cell['cache_enabled'] else 'off'}"
    data_by_label.setdefault(label, []).extend([c["latency_ms"] for c in cell["calls"]])
ax.boxplot(list(data_by_label.values()), tick_labels=list(data_by_label.keys()))
```

### Displaying pass criteria

```python
pc = raw.get("pass_criteria", {})
print(f"All gates pass: {pc.get('all_gates_pass', False)}")
print(f"Recommendation: {pc.get('recommendation', 'N/A')}")
```

## Type safety notes

- Cast `Series` values to `str` for `ax.annotate()` — `Series` is not `str`
- Cast `Series` values to `bool` in f-string conditionals — `Series` in boolean context raises `ValueError`
- Use `tick_labels=` not `labels=` for `ax.boxplot()` (deprecated in newer matplotlib)
- Convert `dict_values`/`dict_keys` to `list()` before passing to matplotlib functions

## Generating the paired notebook

```bash
# Generate notebook from analysis.py
jupytext --to notebook analysis.py

# Or sync both directions after edits
jupytext --sync analysis.py
```

The notebook (`analysis.ipynb`) is gitignored. Only `analysis.py` is committed.
