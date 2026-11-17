"""A main-run output folder written through ``outputs35.Layout`` (integration test, F3).

Stub stages write the file formats of the B2 stage note into the folders the
runner's ``Layout`` gives: search rows (run 1), answer rows with evidence,
``chat`` and ``clef_flash`` judge rows, Ragas rows and claim-kind rows, each
with its key file and done-marker (``outputs35.RowFile``), plus machine lines,
the build environment, fingerprints, rebuild checks, the selection and its
OSF time-stamp, drop step 1 and the pod run records.

Three core datasets, two answer setups, three runs, four questions: ``q1`` and
``q2`` in half A, ``q3`` and ``q4`` in half B.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests._exp35_fixtures import load
from tests._exp35_join_fixtures import CHECKS, ENV, REQUESTED, command, record, write_rows

DATASETS = ("bioasq", "financebench", "freshstack")
SETUPS = ("e4b-c512-roff-hoff", "e4b-c1024-r4b-hon")
RUNS = (1, 2, 3)
QIDS = ("q1", "q2", "q3", "q4")
HALVES = {d: {"q1": "A", "q2": "A", "q3": "B", "q4": "B"} for d in DATASETS}
KEY = {"limit": None, "corpus_sample": None, "seed": 1, "qids": list(QIDS)}
ANSWER = "Fact one [1]. Fact two [1]."
CLAIMS = ("Fact one.", "Fact two.")
VERSION = "v1"


def unit(dataset: str, qid: str) -> str:
    """Return the gold unit of a question: its document, a page for FinanceBench."""
    return f"doc-{qid}#p1" if dataset == "financebench" else f"doc-{qid}"


def questions() -> dict[str, dict[str, dict[str, str]]]:
    """Return the question text and reference per dataset and question ID."""
    return {
        d: {q: {"question": f"{d} {q}?", "reference": f"ref {q}"} for q in QIDS} for d in DATASETS
    }


def _rows(folder: Path, stage: str, rows: list[dict[str, Any]], marker: dict[str, Any]) -> None:
    outputs35 = load("outputs35")
    with outputs35.RowFile(folder, stage, KEY, resume=False) as log:
        for row in rows:
            log.append(row)
        log.mark_done(marker)


def _machine(folder: Path) -> None:
    write_rows(folder / "machine.jsonl", [{"host": "h", "pod_id": "p", "environment": ENV}])


def stub_search(layout: Any, dataset: str, setup: str) -> None:
    """Write one search stage (run 1): 12 stored chunks per question, gold first."""
    folder = layout.run_dir(dataset, "search", setup, 1)
    rows = [
        {
            "qid": q,
            "chunks": [
                {
                    "chunk_id": f"{q}-c{i}",
                    "score": 1.0 - i / 100,
                    "stem": f"doc-{q}" if i == 0 else f"other-{i}",
                    "page_label": "1",
                    "tokens": 100,
                }
                for i in range(12)
            ],
            "seconds": 0.1,
        }
        for q in QIDS
    ]
    _rows(folder, "search", rows, {"questions": len(QIDS), "checks": CHECKS})
    _machine(folder)


def _verdicts(judge: str) -> list[dict[str, Any]]:
    return [
        {"index": i, "ordinals": [1], "verdict": "supported", "call": None}
        for i in range(len(CLAIMS))
    ]


def stub_answer(layout: Any, dataset: str, setup: str, run: int) -> None:
    """Write one answer run: answer, both judges, Ragas and claim kinds."""
    claimkinds35 = load("claimkinds35")
    folder = layout.run_dir(dataset, "answer", setup, run)
    answers = [
        {
            "qid": q,
            "dataset": dataset,
            "setup": setup,
            "run": run,
            "doc_id": f"doc-{q}" if dataset == "financebench" else None,
            "status": "answered",
            "answer": ANSWER,
            "citations": [1],
            "evidence": [
                {
                    "ordinal": 1,
                    "chunk_id": f"{q}-c0",
                    "chunk_ids": [f"{q}-c0"],
                    "source": "s",
                    "text": f"passage {q}",
                    "truncated": False,
                }
            ],
            "cut_tokens": 100,
            "model_returned": REQUESTED["answer"],
            "provider_returned": "deepinfra",
        }
        for q in QIDS
    ]
    _rows(folder, "answer", answers, {"questions": len(QIDS), "checks": CHECKS})
    for judge in ("chat", "clef_flash"):
        rows = [{"qid": q, "judge": judge, "verdicts": _verdicts(judge)} for q in QIDS]
        _rows(folder, f"judge-{judge}", rows, {"checks": CHECKS})
    ragas = [
        {
            "qid": q,
            "metrics": {"ragas_answer_correctness": {"score": 0.75}},
            "model_returned": [REQUESTED["ragas-judge"]],
        }
        for q in QIDS
    ]
    _rows(folder, "ragas", ragas, {"rows": len(QIDS)})
    kinds = [
        {
            "item": claimkinds35.claim_key(q, c),
            "claim_key": claimkinds35.claim_key(q, c),
            "qid": q,
            "index": i,
            "uncited": False,
            "kind": "factual",
            "version": VERSION,
        }
        for q in QIDS
        for i, c in enumerate(CLAIMS)
    ]
    write_rows(folder / "claim-kinds.jsonl", kinds)
    (folder / ".done-claimkinds.json").write_text(json.dumps({"claims": len(kinds)}))
    _machine(folder)


def build(out: Path, experiment: Path) -> list[Path]:
    """Write the whole folder through ``Layout``; return the pod run-record file."""
    outputs35 = load("outputs35")
    arms = load("arms")
    layout = outputs35.Layout(out)
    outputs35.write_json(layout.environment, ENV)
    outputs35.write_json(out / "selection.json", {"configuration_hash": "a" * 64})
    stamp = {"uploaded_at": "t", "file_sha256": "f" * 64, "configuration_hash": "a" * 64}
    outputs35.write_json(out / "osf-timestamp.json", stamp)
    outputs35.write_json(out / "drops.json", {"drops": [{"step": 1, "reason": "test"}]})
    (out.parent / "halves.json").write_text(json.dumps({"seed": 20261115, "halves": HALVES}))
    lines = []
    for dataset in DATASETS:
        outputs35.write_json(out / dataset / "rebuild.json", {"ok": True})
        for setup in SETUPS:
            index = arms.parse_setup(setup).index
            outputs35.write_json(layout.fingerprint(dataset, index), {"table_version": 3})
            stub_search(layout, dataset, setup)
            lines.append(record(command(dataset, setup, "search", 1), len(lines)))
            for run in RUNS:
                stub_answer(layout, dataset, setup, run)
                lines.append(record(command(dataset, setup, "answer", run), len(lines)))
    pods = experiment / "pod1.jsonl"
    write_rows(pods, lines)
    (experiment / "output").mkdir(parents=True, exist_ok=True)
    return [pods]
