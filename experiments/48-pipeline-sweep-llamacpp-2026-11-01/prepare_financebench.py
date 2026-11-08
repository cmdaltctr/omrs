"""Select and freeze the FinanceBench arm of the fixed set (change task 2.3, design D1).

Rule (D1): rank the open-sample documents by question count, highest first,
ties by document name. Take the first 5 with 200 pages or fewer.

Writes, all inside this folder:
- ``output/financebench/pdfs/<doc>.pdf`` (CC BY-NC 4.0; gitignored)
- ``output/financebench-selection.json`` (names, SHA-256, pages, question IDs)
- ``output/financebench-questions.jsonl`` (the frozen questions, gold pages converted)

Run: uv run --no-sync python prepare_financebench.py
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

from pypdf import PdfReader
from sweep_lib import convert_evidence_page, file_sha256, select_financebench, stray_files

HERE = Path(__file__).resolve().parent
SOURCE = Path.home() / "Development/DATA/omrs/benchmarks/financebench"
QUESTIONS = SOURCE / "financebench_merged.jsonl"
MANIFEST = SOURCE / "PDFS_MANIFEST.json"
PDFS = SOURCE / "pdfs"


def load_questions() -> list[dict]:
    """Load the 150 open-sample questions."""
    with QUESTIONS.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def evidence_pages(item: dict) -> list[int | None]:
    """Read the gold pages of one evidence entry, converted to 1-based pages."""
    page = item.get("evidence_page_num", item.get("page_num"))
    return [convert_evidence_page(page)] if isinstance(page, int) else []


def main() -> None:
    questions = load_questions()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    counts = Counter(q["doc_name"] for q in questions)

    candidates = []
    for doc_name, count in counts.items():
        pdf = PDFS / f"{doc_name}.pdf"
        pages = len(PdfReader(str(pdf)).pages)
        entry = manifest["files"].get(doc_name, {})
        candidates.append(
            {
                "doc_name": doc_name,
                "pages": pages,
                "question_count": count,
                "sha256": entry.get("sha256") or file_sha256(pdf),
                "bytes": entry.get("bytes", pdf.stat().st_size),
            }
        )

    chosen = select_financebench(candidates, limit=5)
    chosen_names = {doc["doc_name"] for doc in chosen}

    out_dir = HERE / "output" / "financebench" / "pdfs"
    strays = stray_files(out_dir, [f"{doc['doc_name']}.pdf" for doc in chosen])
    if strays:
        raise SystemExit(
            f"{out_dir} holds files outside the selection: {', '.join(strays)}. "
            "Both runners would ingest them. Remove them and run again."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    for doc in chosen:
        shutil.copy2(PDFS / f"{doc['doc_name']}.pdf",
                    out_dir / f"{doc['doc_name']}.pdf")
        found = file_sha256(out_dir / f"{doc['doc_name']}.pdf")
        if found != doc["sha256"]:
            raise SystemExit(
                f"{doc['doc_name']}: copied PDF hash {found} != manifest {doc['sha256']}")

    rows = []
    for question in questions:
        if question["doc_name"] not in chosen_names:
            continue
        rows.append(
            {
                "financebench_id": question["financebench_id"],
                "doc_name": question["doc_name"],
                "question": question["question"],
                "answer": question.get("answer", ""),
                "evidence": [
                    {
                        "doc_name": item.get("doc_name") or question["doc_name"],
                        "pages": evidence_pages(item),
                    }
                    for item in question.get("evidence", [])
                ],
            }
        )

    (HERE / "output" / "financebench-selection.json").write_text(
        json.dumps(chosen, indent=2) + "\n", encoding="utf-8"
    )
    with (HERE / "output" / "financebench-questions.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    total_pages = sum(doc["pages"] for doc in chosen)
    print(f"selected {len(chosen)} PDFs, {total_pages} pages, {len(rows)} questions", flush=True)
    for doc in chosen:
        print(
            f"  {doc['doc_name']}: {doc['pages']} pages, {doc['question_count']} questions, "
            f"sha256 {doc['sha256'][:12]}",
            flush=True,
        )


if __name__ == "__main__":
    main()
