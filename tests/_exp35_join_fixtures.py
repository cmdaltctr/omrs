"""A built Experiment 35 output folder for the join tests (task 6.1).

Two datasets (BioASQ, Legal), two setups used as search and answer setups,
three answer runs, two questions. File shapes follow the B2 stage note: the
search and answer run folders, done-markers with ``checks``, key files,
``machine.jsonl``, ``traces.jsonl``, judge, Ragas and claim-kind rows.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tests._exp35_fixtures import load

DATASETS = ("bioasq", "legal")
SETUPS = ("e4b-c512-roff-hoff", "e4b-c512-r4b-hoff")
RUNS = (1, 2, 3)
QIDS = ("q1", "q2")
ENV = {
    "gpu": "RTX 4090",
    "image": "img@sha256:abc",
    "llama_cpp_build": 11941,
    "gguf_sha256": {"a.gguf": "1" * 64},
}
CHECKS = {
    "fingerprint": {"table_version": 3, "sparse_backend": "bm25", "fts": None},
    "table_version_unchanged": True,
}
ANSWER = "Fact one [1]. Uncited fact."
REQUESTED = {"answer": "deepseek/deepseek-v4.1-flash-1017", "ragas-judge": "openai/gpt-oss-120b"}


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write JSON lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def write_json(path: Path, value: Any) -> None:
    """Write one JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _trace(stage: str, dataset: str, qid: str) -> dict[str, Any]:
    return {
        "benchmark_revision": "r",
        "run_id": "x",
        "arm": "s",
        "repetition": 1,
        "dataset": dataset,
        "question_id": qid,
        "stage": stage,
        "status": "ok",
    }


def record(command: str, minute: int, **flags: bool) -> dict[str, Any]:
    """Return one valid run-record line."""
    started = datetime(2026, 12, 1, tzinfo=UTC) + timedelta(minutes=minute)
    return {
        "format": "omrs-run-record/1",
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "git_commit": "a" * 40,
        "git_dirty": False,
        "plan_sha256": "",
        "command": command,
        **{k: v for k, v in flags.items() if v},
    }


def command(dataset: str, setup: str, stage: str, run: int) -> str:
    """Return a stage command as ``run_arms._command`` writes it."""
    return f"run_arms.py --dataset {dataset} --setup {setup} --stage {stage} --run {run}"


def _search_run(out: Path, dataset: str, setup: str) -> None:
    folder = out / dataset / "search" / setup / "run1"
    write_json(folder / ".done-search.json", {"questions": 2, "checks": CHECKS})
    write_json(folder / "search.key.json", {"seed": 1, "qids": list(QIDS)})
    write_rows(folder / "search.jsonl", [{"qid": q, "chunks": []} for q in QIDS])
    write_rows(folder / "machine.jsonl", [{"host": "h", "pod_id": "p", "environment": ENV}])
    write_rows(folder / "traces.jsonl", [_trace("search", dataset, q) for q in QIDS])


def _answer_run(out: Path, dataset: str, setup: str, run: int) -> None:
    claimkinds35 = load("claimkinds35")
    folder = out / dataset / "answer" / setup / f"run{run}"
    for stage in ("answer", "judge-chat", "judge-clef_flash"):
        write_json(folder / f".done-{stage}.json", {"checks": CHECKS})
    write_json(folder / ".done-ragas.json", {"rows": 2})
    write_json(folder / ".done-claimkinds.json", {"claims": 2})
    for stage in ("answer", "judge-chat", "judge-clef_flash"):
        write_json(folder / f"{stage}.key.json", {"seed": 1, "qids": list(QIDS)})
    answers = [
        {
            "qid": q,
            "dataset": dataset,
            "setup": setup,
            "run": run,
            "doc_id": None,
            "answer": ANSWER,
            "evidence": [{"ordinal": 1, "chunk_ids": ["c"], "text": "t"}],
            "cut_tokens": 1000,
            "evidence_tokens": 900,  # answers35 saves the realised (assembled) total
            "model_returned": REQUESTED["answer"],
        }
        for q in QIDS
    ]
    write_rows(folder / "answer.jsonl", answers)
    verdicts = [{"index": 0, "ordinals": [1], "verdict": "supported"}]
    write_rows(folder / "judge-chat.jsonl", [{"qid": q, "verdicts": verdicts} for q in QIDS])
    write_rows(folder / "judge-clef_flash.jsonl", [{"qid": q, "verdicts": verdicts} for q in QIDS])
    ragas = [
        {
            "qid": q,
            "metrics": {"ragas_answer_correctness": {"score": 0.75}},
            "model_returned": [REQUESTED["ragas-judge"]],
        }
        for q in QIDS
    ]
    write_rows(folder / "ragas.jsonl", ragas)
    kinds = []
    for q in QIDS:
        kinds.append(
            {
                "claim_key": claimkinds35.claim_key(q, "Fact one."),
                "qid": q,
                "index": 0,
                "kind": "factual",
                "version": "v",
            }
        )
        kinds.append(
            {
                "claim_key": claimkinds35.claim_key(q, "Uncited fact."),
                "qid": q,
                "index": 0,
                "kind": "factual",
                "version": "v",
                "uncited": True,
            }
        )
    write_rows(folder / "claim-kinds.jsonl", kinds)
    write_rows(folder / "machine.jsonl", [{"host": "h", "pod_id": "p", "environment": ENV}])
    stages = ("answer", "judge-chat", "judge-clef_flash")
    write_rows(folder / "traces.jsonl", [_trace(s, dataset, q) for s in stages for q in QIDS])


def build(out: Path, experiment: Path, *, runs: tuple[int, ...] = RUNS) -> list[Path]:
    """Write a complete output folder; return three pod run-record files (not merged)."""
    write_json(out / "environment.json", ENV)
    write_json(out / "selection.json", {"configuration_hash": "a" * 64})
    stamp = {"uploaded_at": "t", "file_sha256": "f" * 64, "configuration_hash": "a" * 64}
    write_json(out / "osf-timestamp.json", stamp)
    lines: list[dict[str, Any]] = []
    minute = 0
    for dataset in DATASETS:
        write_json(out / dataset / "rebuild.json", {"ok": True})
        write_json(out / dataset / "e4b-c512" / "index-fingerprint.json", {"table_version": 3})
        for setup in SETUPS:
            _search_run(out, dataset, setup)
            lines.append(record(command(dataset, setup, "search", 1), minute))
            minute += 1
            for run in runs:
                _answer_run(out, dataset, setup, run)
                lines.append(record(command(dataset, setup, "answer", run), minute))
                minute += 1
    (experiment / "output").mkdir(parents=True, exist_ok=True)
    pods = []
    for n in range(3):
        path = experiment / f"pod{n + 1}.jsonl"
        write_rows(path, lines[n::3])
        pods.append(path)
    return pods
