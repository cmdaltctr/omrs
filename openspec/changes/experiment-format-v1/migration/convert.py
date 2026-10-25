"""One-off move of the existing experiment folders to format v1 (design D11).

Reads the hand-written index in ``experiments/EXP_README.md`` and each
experiment folder, then writes one ``experiment.json`` per folder that has
none. It changes no existing file. Every judgement it makes goes into
``migration/report.md`` for review.

Run from the repository root::

    uv run --no-sync python openspec/changes/experiment-format-v1/migration/convert.py --dry-run
    uv run --no-sync python openspec/changes/experiment-format-v1/migration/convert.py

This script does not ship. It is archived with the change.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from omrs.core.experiment_records import naming, record

REPO = Path(__file__).resolve().parents[4]
EXPERIMENTS = REPO / "experiments"
REPORT = Path(__file__).resolve().parent / "report.md"
MOVE_DATE = "2026-10-25"
NOT_EXPERIMENTS = {"_lib", "ARCHIVED", "example", "__pycache__"}

# Category per folder. Fixed by hand from the folder title and its index row,
# using the six categories of the format. Every value is listed in the report.
CATEGORY = {
    "1-reranker-threshold-calibration-2026-05-12": "retrieval",
    "2-embedding-model-comparison-2026-05-19": "retrieval",
    "3-e2e-smoke-test-metadata-2026-05-20": "ingestion",
    "4-async-chunking-responsiveness-2026-05-27": "runtime",
    "5-reranker-pool-sizing-2026-05-27": "retrieval",
    "5b-persistent-mps-reranker-worker-2026-08-20": "runtime",
    "6-markdown-chunking-quality-2026-05-27": "retrieval",
    "6b-qasper-markdown-chunking-2026-05-28": "retrieval",
    "6c-markdown-chunking-quickwins-2026-05-28": "retrieval",
    "7-chunk-overlap-sensitivity-2026-05-27": "retrieval",
    "7a-chunk-overlap-evidence-2026-05-29": "retrieval",
    "8-query-embedding-cache-2026-05-27": "runtime",
    "8a-query-embedding-cache-fullsize-2026-05-29": "runtime",
    "9-hybrid-retrieval-2026-05-27": "retrieval",
    "9a-hybrid-retrieval-freshstack-langchain-2026-05-30": "retrieval",
    "9a-rerun-post-adr021-reranker-2026-06-29": "retrieval",
    "10-reranker-technical-workload-calibration-2026-05-31": "retrieval",
    "10.1-doc-similarity-threshold-calibration-2026-06-29": "graph",
    "10b-reranker-pool-size-corrected-2026-06-29": "retrieval",
    "11-liteparse-pdf-quality-2026-06-20": "ingestion",
    "12-hybrid-default-promotion-2026-06-29": "retrieval",
    "13-hard-technical-threshold-calibration-2026-06-29": "retrieval",
    "14-liteparse-qasper-promotion-2026-06-29": "ingestion",
    "15-gte-reranker-swap-2026-07-31": "retrieval",
    "16-reranker-coreml-fp16-2026-08-03": "runtime",
    "17-reranker-mps-vs-onnx-cpu-2026-08-11": "runtime",
    "18-ingestion-lock-scope-ab-2026-08-19": "runtime",
    "19-lancedb-lifecycle-qualification-2026-08-21": "runtime",
    "19-native-fts-vs-bm25-sparse-2026-08-29": "retrieval",
    "20-citation-faithfulness-2026-09-02": "generation",
    "21-lancedb-literal-faithfulness-2026-09-02": "runtime",
    "22-raw-query-qwen4b-baseline-2026-09-07": "retrieval",
    "23-ocr-routing-gate-calibration-2026-09-07": "ingestion",
    "24-ocr-routing-eval-2026-09-08": "ingestion",
    "25-token-chunking-ablation-2026-09-08": "retrieval",
    "26-query-instruction-ablation-2026-09-08": "retrieval",
    "27-combined-candidate-path-2026-09-09": "retrieval",
    "28-pdf-classification-prevalence-2026-09-09": "ingestion",
    "29-pdf-routing-repeat-2026-09-13": "ingestion",
    "30-reader-fallback-chain-2026-09-13": "ingestion",
    "31-reader-rescue-retrieval-impact-2026-09-15": "ingestion",
    "32-misnamed-extension-detection-2026-09-16": "ingestion",
    "33-ocr-routing-natural-positive-2026-09-17": "ingestion",
    "34-worker-sample-review-2026-09-19": "review",
    "36-reader-output-normalisation-2026-09-25": "ingestion",
    "37-dots-mocr-routing-acceptance-2026-09-30": "ingestion",
    "38-rescue-quality-signal-2026-09-30": "ingestion",
    "39-local-tier-escalation-2026-09-30": "ingestion",
    "42-clef-flash-confirmation-2026-10-08": "ingestion",
    "leiden-vs-louvain-2026-08-14": "graph",
}

# Targets of SUPERSEDED rows. "SUPERSEDED D17" means the D17 factorial,
# which runs in 10b (10b protocol.md line 1).
SUPERSEDED_BY = {
    "12-hybrid-default-promotion-2026-06-29": "10b-reranker-pool-size-corrected-2026-06-29",
    "9a-rerun-post-adr021-reranker-2026-06-29": "10b-reranker-pool-size-corrected-2026-06-29",
}

# Folders with no index row. Status, title and finding come from the named
# file in the folder; the text is quoted or closely summarised from it.
NO_ROW = {
    "15-gte-reranker-swap-2026-07-31": (
        "gte-reranker-modernbert-base A/B comparison",
        "INCONCLUSIVE",
        "results.md: **Status:** INCONCLUSIVE (small sample + reduced candidate pool; see caveats)",
        "gte did not beat the rerank-off baseline; both rerankers degraded "
        "technical retrieval (30-query subset).",
    ),
    "19-lancedb-lifecycle-qualification-2026-08-21": (
        "LanceDB production-lifecycle qualification",
        "PASS",
        "results.md: ## Verdict **PASS** (run2, 14/14 gates)",
        "LanceDB passed 14/14 production-lifecycle gates on run 2.",
    ),
    "5b-persistent-mps-reranker-worker-2026-08-20": (
        "Persistent MPS reranker worker",
        "FAIL",
        "results.md: **Overall verdict:** **FAIL — promotion rejected; ONNX "
        "CPU remains the production default**",
        "Promotion rejected: ONNX CPU stays the production reranker default.",
    ),
    "6b-qasper-markdown-chunking-2026-05-28": (
        "Evidence-level Markdown chunking on Qasper",
        "FAIL",
        "results.md: **Status**: COMPLETE (real negative result)",
        "Heading-aware Markdown chunker lowered Evidence Recall@5 by 5.66 "
        "points (reranker off) and 1.89 points (reranker on).",
    ),
    "6c-markdown-chunking-quickwins-2026-05-28": (
        "Quick-win interventions for Markdown chunking on Qasper",
        "PASS",
        "results.md: **Status**: PASS",
        "With chunk_size=1024, heading-aware Markdown chunking beats the bare "
        "splitter with the reranker on.",
    ),
    "leiden-vs-louvain-2026-08-14": (
        "Leiden versus Louvain community detection",
        "MEASURED",
        "ADR-044 section Experiment (no status recorded; a comparison without a gate)",
        "Both algorithms found the same 8 communities on both test graphs; "
        "Louvain was slightly faster.",
    ),
}

STATUS_WORDS = {"PASS", "FAIL", "INCONCLUSIVE", "PLANNED", "SUPERSEDED", "ACTIVE", "MEASURED"}
LEGACY_STATUS = {"COMPLETE": "MEASURED", "PARTIAL": "INCONCLUSIVE", "REBUILT": "ACTIVE"}


@dataclass(frozen=True)
class Row:
    """One row of the hand-written index."""

    folder: str
    title: str
    date: str
    status_text: str
    finding: str


def _cells(line: str) -> list[str]:
    body = line.strip()[1:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", body)]


def read_rows(readme: Path) -> tuple[dict[str, Row], list[str]]:
    """Return index rows by folder, and rows that link to no folder."""
    lines = readme.read_text(encoding="utf-8").splitlines()
    start = lines.index("## Index")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
    rows: dict[str, Row] = {}
    orphans: list[str] = []
    for line in lines[start:end]:
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        cells = _cells(line)
        if cells[0] == "#":
            continue
        link = re.match(r"^\[(?P<title>.+)\]\(\./(?P<folder>[^)]+?)/?\)$", cells[1])
        if link is None:
            orphans.append(line)
            continue
        rows[link["folder"]] = Row(link["folder"], link["title"], cells[2], cells[3], cells[4])
    return rows, orphans


def _number(name: str) -> str:
    parsed = naming.parse_folder_name(name)
    return parsed.number if parsed else ""


def map_status(text: str) -> str:
    """Map an old status cell to a format v1 status (design D11)."""
    word = re.match(r"[A-Z]+", text.strip())
    if word is None:
        raise ValueError(f"no status word in {text!r}")
    head = word.group(0)
    if head in STATUS_WORDS:
        return head
    if head in LEGACY_STATUS:
        return LEGACY_STATUS[head]
    raise ValueError(f"unknown status {text!r}")


def infer_size(folder: Path) -> str | None:
    """Standard with protocol and plan, Quick with neither, else unknown."""
    has_protocol = (folder / "protocol.md").exists()
    has_plan = (folder / "plan.json").exists()
    if has_protocol and has_plan:
        return "Standard"
    if not has_protocol and not has_plan:
        return "Quick"
    return None


def build(folder: Path, rows: dict[str, Row]) -> tuple[dict, list[str]]:
    """Return the record payload for *folder* and the notes for the report."""
    name = folder.name
    parsed = naming.parse_folder_name(name)
    if parsed is None:
        raise SystemExit(f"{name}: folder name does not follow the naming pattern")
    folder_date = parsed.date.isoformat()
    notes: list[str] = []
    if name in rows:
        row = rows[name]
        title, finding, from_status, source = (
            row.title,
            row.finding,
            row.status_text,
            "EXP_README.md",
        )
        status = map_status(row.status_text)
        if row.date != folder_date:
            notes.append(
                f"index date {row.date} differs from folder date {folder_date}; folder date kept"
            )
    elif name in NO_ROW:
        title, status, from_status, finding = NO_ROW[name]
        source = from_status.split(":", 1)[0]
        notes.append("no index row; status, title and finding taken from the folder")
    else:
        raise SystemExit(f"{name}: no index row and no NO_ROW entry. Add one; do not guess.")
    if from_status.strip() != status:
        notes.append(f"status `{from_status}` mapped to `{status}`")
    superseded_by = SUPERSEDED_BY.get(name)
    if status == "SUPERSEDED" and superseded_by is None:
        raise SystemExit(
            f"{name}: SUPERSEDED row without a SUPERSEDED_BY entry. Add one; do not guess."
        )
    if superseded_by:
        notes.append(f"superseded_by `{superseded_by}`")
    size = infer_size(folder)
    notes.append(f"category `{CATEGORY[name]}`, size `{size}`")
    payload = {
        "format": record.FORMAT,
        "number": parsed.number,
        "title": title,
        "date": folder_date,
        "category": CATEGORY[name],
        "size": size,
        "status": status,
        "superseded_by": superseded_by,
        "finding": " ".join(finding.split()),
        "migration": {"from_status": from_status, "source": source, "date": MOVE_DATE},
    }
    if name == "leiden-vs-louvain-2026-08-14":
        payload["refs"] = {"adrs": ["ADR-044"], "changes": [], "tasks": []}
    return payload, notes


def main(argv: list[str] | None = None) -> int:
    """Convert every experiment folder that has no record yet."""
    parser = argparse.ArgumentParser(description="Move experiment folders to format v1.")
    parser.add_argument("--dry-run", action="store_true", help="validate and report, write nothing")
    args = parser.parse_args(argv)
    rows, orphans = read_rows(EXPERIMENTS / "EXP_README.md")
    folders = sorted(
        (p for p in EXPERIMENTS.iterdir() if p.is_dir() and p.name not in NOT_EXPERIMENTS),
        key=lambda p: naming.folder_sort_key(_number(p.name), p.name),
    )
    lines = [
        "# Move report: experiment format v1",
        "",
        f"Date: {MOVE_DATE}. Folders: {len(folders)}. Index rows without a folder: {len(orphans)}.",
        "",
        "Each line lists the judgements the move made for one folder. The "
        "original status text is kept in",
        "`migration.from_status` in each `experiment.json`.",
        "",
        "| Folder | Status | Notes |",
        "|---|---|---|",
    ]
    written = 0
    for folder in folders:
        payload, notes = build(folder, rows)
        rec = record.ExperimentRecord.model_validate(payload)
        lines.append(
            f"| `{folder.name}` | {rec.status.value} | {'; '.join(notes).replace('|', '/')} |"
        )
        target = folder / "experiment.json"
        if target.exists():
            continue
        if not args.dry_run:
            target.write_text(record.dump_record(rec), encoding="utf-8")
            written += 1
    lines += ["", "## Index rows without a folder", ""]
    lines += [f"- `{line[:160]}`" for line in orphans] or ["None."]
    lines += ["", "These become entries in `experiments/reserved.json`.", ""]
    if not args.dry_run:
        REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"folders={len(folders)} written={written} dry_run={args.dry_run}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
