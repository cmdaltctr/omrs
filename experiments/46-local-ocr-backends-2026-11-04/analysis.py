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
# # Experiment 46: Local OCR backends for non-Latin scripts
# Tables for `report.md`. Reads `output/summary.json` only and writes `output/report_tables.md`.
# Sections (a) to (e) repeat the planned gates. Sections (f) and (g) are exploratory and enter
# no gate: they show what the chosen cut does on pages the gates do not cover.

# %%
import json
import statistics
from collections import defaultdict
from pathlib import Path

try:
    _ROOT = Path(__file__).parent
except NameError:
    _ROOT = Path.cwd()

OUT = _ROOT / "output"
summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
th = summary["thresholds"]
arms = summary["arms"]
control = summary["control_A"]
lines: list[str] = []


def table(header: list[str], rows: list[list]) -> None:
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    lines.append("")


def ok(flag: bool) -> str:
    return "pass" if flag else "FAIL"


def med(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


# %% [markdown]
# ## (a) G1: median recall by script (threshold in `thresholds.G1`)

# %%
lines.append("### (a) Median token recall by script (G1: 0.70 or more)\n")
scripts = ["arabic", "bengali", "devanagari"]
rows = []
for s in scripts:
    row = [s, control["median_recall_by_script"][s]]
    for a in ("B", "D"):
        got = arms[a]["median_recall_by_script"].get(s)
        row.append("not run" if got is None else f"{got} ({ok(arms[a]['gates']['G1'][s])})")
    row += [arms[a]["median_recall_vs_dots_by_script"].get(s, "n/a") for a in ("B", "D")]
    rows.append(row)
table(
    ["Script", "A PP-OCRv6", "B Indra", "D Apple Vision", "B vs dots.mocr", "D vs dots.mocr"], rows
)

# %% [markdown]
# ## (b) G2: cut applied with leave-one-document-out, scripts that pass G1

# %%
lines.append("### (b) G2 over the pages of the scripts that pass G1\n")
rows = []
for a, res in arms.items():
    passing = [s for s, v in res["gates"]["G1"].items() if v]
    pool = [r for r in res["rows"] if r["script"] in passing]
    good = [r for r in pool if r["recall"] >= 0.8]
    kept = [r for r in pool if r["kept"]]
    bad_kept = [r for r in kept if r["recall"] < 0.5]
    rows.append(
        [
            a,
            "+".join(passing),
            f"{sum(r['kept'] for r in good)} of {len(good)} ({ok(res['gates']['G2a'])})",
            f"{len(bad_kept)} of {len(kept)} ({ok(res['gates']['G2b'])})",
            f"{len(kept)} of {len(pool)} ({ok(res['gates']['G2c'])})",
        ]
    )
table(
    [
        "Arm",
        "Scripts",
        "Good pages kept (0.60+)",
        "Kept pages bad (0.05 or less)",
        "Pages kept (0.30+)",
    ],
    rows,
)

# %% [markdown]
# ## (c) G3: Latin non-regression, G4: speed

# %%
lines.append("### (c) G3 Latin paired difference (arm minus PP-OCRv6) and G4 seconds per page\n")
rows = []
for a, res in arms.items():
    v = res["g3_values"]
    rows.append(
        [
            a,
            f"{v['overall_median_diff']} ({ok(res['gates']['G3a'])})",
            ", ".join(f"{k} {x}" for k, x in v["stratum_median_diff"].items()),
            ok(res["gates"]["G3b"]),
            f"{res['median_seconds_timed']} ({ok(res['gates']['G4'])})",
        ]
    )
table(
    ["Arm", "Overall median diff (-0.02)", "Stratum medians (-0.05)", "G3b", "Median s/page (5.0)"],
    rows,
)

lines.append("Median Latin recall by stratum:\n")
rows = [
    [
        "A PP-OCRv6",
        *[control["median_recall_by_stratum"][s] for s in ("print", "old_print", "handwriting")],
    ]
]
for a, res in arms.items():
    by = defaultdict(list)
    for r in res["rows"]:
        if r["script"] == "latin":
            by[r["stratum"]].append(r["recall"])
    rows.append([a, *[med(by[s]) for s in ("print", "old_print", "handwriting")]])
table(["Arm", "Print (30)", "Old print (35)", "Handwriting (35)"], rows)

# %% [markdown]
# ## (d) Outcome

# %%
lines.append(f"### (d) Outcome: {summary['outcome']}\n")
table(
    ["Arm", "Script", "G1", "G2", "G3", "G4"],
    [
        [a, s, *[ok(v[g]) for g in ("G1", "G2", "G3", "G4")]]
        for a, res in arms.items()
        for s, v in res["verdict_by_script"].items()
    ],
)

# %% [markdown]
# ## (e) Cuts, confidence AUC (H2) and per-document values

# %%
lines.append("### (e) Leave-one-document-out cuts, registered cut and confidence AUC\n")
table(
    [
        "Arm",
        "Cut for each held-out document",
        "Registered cut",
        "AUC conf",
        "AUC min long line",
        "AUC share",
    ],
    [
        [
            a,
            ", ".join(f"{d} {c}" for d, c in res["loo_cuts"].items()),
            res["registered_cut"],
            *[
                round(res["auc_recall_ge_0_8"][k], 3)
                for k in ("conf", "conf_min_long", "conf_share")
            ],
        ]
        for a, res in arms.items()
    ],
)
lines.append(
    "Per document (pages, median recall, kept by the cut, kept pages with recall below 0.5):\n"
)
rows = []
for a, res in arms.items():
    by = defaultdict(list)
    for r in res["rows"]:
        by[r["doc"]].append(r)
    for doc, rs in sorted(by.items()):
        rows.append(
            [
                a,
                doc,
                rs[0]["script"],
                len(rs),
                med([r["recall"] for r in rs]),
                sum(r["kept"] for r in rs),
                sum(1 for r in rs if r["kept"] and r["recall"] < 0.5),
            ]
        )
table(["Arm", "Document", "Script", "Pages", "Median recall", "Kept", "Kept and bad"], rows)

# %% [markdown]
# ## (f) Exploratory: the cut on every page, including scripts that fail G1

# %%
lines.append("### (f) Exploratory: kept pages by script under the leave-one-document-out cut\n")
rows = []
for a, res in arms.items():
    by = defaultdict(list)
    for r in res["rows"]:
        by[r["script"]].append(r)
    for s, rs in sorted(by.items()):
        kept = [r for r in rs if r["kept"]]
        rows.append(
            [
                a,
                s,
                len(rs),
                len(kept),
                sum(1 for r in kept if r["recall"] < 0.5),
                med([r["recall"] for r in kept]),
            ]
        )
table(
    ["Arm", "Script", "Pages", "Kept", "Kept and bad (below 0.5)", "Median recall of kept pages"],
    rows,
)

# %% [markdown]
# ## (g) Exploratory: spot-check candidates and time saved

# %%
lines.append(
    "### (g) Exploratory: pages where the reference is suspect "
    "(recall below 0.5, dots.mocr 0.8 or more)\n"
)
rows = []
for a, res in arms.items():
    for s in ("arabic", "devanagari", "bengali"):
        picks = [
            f"{r['doc']} p{r['page']}"
            for r in res["rows"]
            if r["script"] == s and r["recall"] < 0.5 and (r["recall_dots"] or 0) >= 0.8
        ]
        rows.append([a, s, len(picks), ", ".join(picks[:10])])
table(["Arm", "Script", "Candidate pages", "First 10"], rows)
engine_seconds = 37.0  # Experiment 37, dots.mocr seconds per page
for a, res in arms.items():
    passing = [s for s, v in res["gates"]["G1"].items() if v]
    kept = sum(1 for r in res["rows"] if r["script"] in passing and r["kept"])
    lines.append(
        f"- Arm {a}: {kept} pages of {'+'.join(passing)} stay local; at {engine_seconds} s "
        f"per engine page that avoids about {round(kept * engine_seconds / 60)} minutes."
    )
lines.append("")

# %%
(OUT / "report_tables.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
