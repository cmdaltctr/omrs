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
# # Experiment 45: Non-Latin script routing on stored OCR evidence
# Tables for `report.md`. Reads `output/summary.json` and `output/verdicts.json` only.
# The one exception is the last section: it counts letters per Unicode script in the frozen
# Experiment 37 engine text of the 129 pages. That count is descriptive. It does not enter
# a gate. It also writes `output/script_letters_engine_text.json` and `output/report_tables.md`.

# %%
import json
import os
import unicodedata
from collections import Counter
from pathlib import Path

try:
    _ROOT = Path(__file__).parent
except NameError:
    _ROOT = Path.cwd()

OUT = _ROOT / "output"
summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
verdicts = json.loads((OUT / "verdicts.json").read_text(encoding="utf-8"))
lines: list[str] = []


def table(header: list[str], rows: list[list]) -> None:
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    lines.append("")


def counts(entry: dict, *keys: str) -> list[int]:
    return [entry.get(k, 0) for k in keys]


# %% [markdown]
# ## (a) Flagged pages before OCR (design D3 point 1)

# %%
lines.append("### (a) Flagged pages, verdict on the text items before OCR\n")
rows = []
for doc, by_class in summary["a"]["per_document"].items():
    for cls, entry in by_class.items():
        non_latin, latin, none = counts(entry, "non_latin", "latin_verdict", "no_verdict")
        rows.append([doc, cls, non_latin + latin + none, non_latin, latin, none])
table(["Document", "Page class", "Flagged pages", "Non-Latin", "Latin", "No verdict"], rows)

# %% [markdown]
# ## (b) Stored local OCR text (design D3 point 2)

# %%
lines.append("### (b) Stored local OCR text, verdict per document\n")
rows = []
for doc, by_class in summary["b"]["per_document"].items():
    for cls, entry in by_class.items():
        non_latin, latin, none = counts(entry, "non_latin", "latin_verdict", "no_verdict")
        rows.append([doc, cls, non_latin + latin + none, non_latin, latin, none])
table(["Document", "Page class", "Stored rows", "Non-Latin", "Latin", "No verdict"], rows)

# %% [markdown]
# ## (c) False positives on Latin pages

# %%
c = summary["c"]
lines.append("### (c) False positives on Latin pages\n")
table(
    ["Part", "Latin pages", "With a verdict", "Non-Latin verdicts"],
    [
        ["c1 flagged pages, before OCR", c["latin_flagged_pages"],
         c["latin_flagged_pages_with_a_verdict"], c["c1_flagged_latin_pages_non_latin_verdict"]],
        ["c2 stored local text", c["latin_stored_rows"], c["latin_stored_rows_with_a_verdict"],
         c["c2_stored_latin_rows_non_latin_verdict"]],
        ["c3 engine text (not gated)", c["c3_not_gated_engine_text_latin_pages"]["pages"],
         c["c3_not_gated_engine_text_latin_pages"]["with_a_verdict"],
         c["c3_not_gated_engine_text_latin_pages"]["non_latin_verdicts"]],
    ],
)

# %% [markdown]
# ## (d) Local seconds saved by `always`

# %%
d = summary["d"]
lines.append("### (d) Local seconds on the 129 non-Latin pages (saved by `always`)\n")
table(
    ["Document", "Seconds"],
    [[doc, v] for doc, v in d["per_document_seconds"].items()]
    + [["Total (129 pages)", d["total_seconds_129_pages"]],
       ["Total without timed-out documents", d["total_seconds_without_timed_out_documents"]],
       [f"Latin-class stored rows ({d['latin_class_stored_rows']} rows)",
        d["latin_class_stored_rows_seconds"]]],
)

# %% [markdown]
# ## (e) Kept by the 0.9 cut, escalated by `detect`

# %%
e = summary["e"]
lines.append("### (e) The 129 non-Latin pages and the 0.9 cut\n")
rows = []
for doc in ("io01", "io02", "io03", "io07"):
    pages = [r for r in verdicts["local_rows"] if r["doc_id"] == doc and r["page_class"] == "non_latin"]
    conf = [r["confidence"] for r in pages if r["confidence"] is not None]
    rows.append([
        doc, len(pages), sum(1 for r in pages if r["kept_by_cut"]),
        sum(1 for r in pages if r["kept_by_cut"] and r["verdict"] is True),
        sum(1 for r in pages if "low_confidence" in r["reasons"]),
        sum(1 for r in pages if "hosted_recommended" in r["reasons"]),
        f"{min(conf):.3f} to {max(conf):.3f}",
    ])
rows.append(["All", e["non_latin_class_rows"], e["e0_kept_by_cut_any_verdict"], e["e"],
             e["reasons_among_129"].get("low_confidence", 0),
             e["reasons_among_129"].get("hosted_recommended", 0),
             f"{e['confidence_min_max_of_129'][0]:.3f} to {e['confidence_min_max_of_129'][1]:.3f}"])
table(["Document", "Pages", "Kept by cut (e0)", "Kept and non-Latin (e)", "Low confidence",
       "Hosted recommended", "Confidence range"], rows)

# %% [markdown]
# ## Descriptive: scripts found in the engine text of the 129 pages
# Not part of any gate. Counts letters by the first word of the Unicode character name.

# %%
inputs = verdicts["meta"]["inputs"]
engine_key = next(k for k in inputs if k.endswith("output/dots-mocr"))
engine_dir = Path(inputs[engine_key].replace("~", str(Path.home()), 1))
if not engine_dir.is_absolute():
    engine_dir = _ROOT.parents[1] / engine_dir
scripts: dict[str, Counter] = {}
for row in verdicts["engine_rows"]:
    if row["page_class"] != "non_latin":
        continue
    text = (engine_dir / row["doc_id"] / f"p{row['page']:03d}.md").read_text(encoding="utf-8")
    counter = scripts.setdefault(row["doc_id"], Counter())
    for char in text:
        if char.isalpha():
            counter[unicodedata.name(char, "UNKNOWN").split()[0]] += 1
described = {doc: dict(c.most_common(5)) for doc, c in sorted(scripts.items())}
tmp = OUT / "script_letters_engine_text.json.tmp"
tmp.write_text(json.dumps(described, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
os.replace(tmp, OUT / "script_letters_engine_text.json")
lines.append("### Descriptive: letters per script in the engine text of the 129 pages\n")
table(["Document", "Top scripts (letters)"], [[d_, json.dumps(v)] for d_, v in described.items()])

# %%
tmp = OUT / "report_tables.md.tmp"
tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
os.replace(tmp, OUT / "report_tables.md")
print("\n".join(lines))
