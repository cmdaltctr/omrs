"""Shared fixtures for the Experiment 35 arm runner tests (``test_experiment35_*.py``).

Everything here is synthetic: a fake plan, empty GGUF files and a tiny copy of
the three dataset layouts in a tmp folder. Nothing reads the DATA folder, a
GGUF file or the network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "experiments" / "35-full-rag-benchmark-2026-11-01"

_EMBED = {
    "embedding-baseline-4b": "Qwen3-Embedding-4B-Q8_0.gguf",
    "embedding-0.6b": "Qwen3-Embedding-0.6B-Q8_0.gguf",
    "embedding-8b": "Qwen3-Embedding-8B-Q8_0.gguf",
}


def load(name: str) -> ModuleType:
    """Import one experiment module by path, once (the modules import each other by name)."""
    for folder in (ROOT, FOLDER):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, FOLDER / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fake_plan() -> dict[str, Any]:
    """A plan with the three embedders and the two local judges (valid OMRS presets)."""
    embed_args = {
        "embeddings": True,
        "pooling": "last",
        "ctx-size": 8192,
        "batch-size": 8192,
        "ubatch-size": 8192,
    }
    models: list[dict[str, Any]] = [
        {
            "role": role,
            "repository": f"Qwen/{file.rsplit('-', 1)[0]}-GGUF",
            "file": file,
            "sha256": "a" * 64,
            "runtime": "llama.cpp",
            "build": 11671,
            "server_args": dict(embed_args),
        }
        for role, file in _EMBED.items()
    ]
    for role, repo, file, digest in (
        ("judge-clef-flash", "ggml-org/Clef-Flash-GGUF", "Clef-Flash-Q8_0.gguf", "b"),
        (
            "judge-granite-guardian",
            "ibm-granite/granite-guardian-3.3-8b-GGUF",
            "granite-guardian-3.3-8b-Q8_0.gguf",
            "c",
        ),
    ):
        models.append(
            {
                "role": role,
                "repository": repo,
                "file": file,
                "sha256": digest * 64,
                "runtime": "llama.cpp",
                "build": 11671,
                "server_args": {"ctx-size": 32768, "parallel": 1},
            }
        )
    return {"protocol_version": 1, "seed": 20261101, "runtime": {"models": models}}


def make_gguf(folder: Path) -> Path:
    """Write an empty file for every fake plan model; return the folder."""
    folder.mkdir(parents=True, exist_ok=True)
    for model in fake_plan()["runtime"]["models"]:
        (folder / model["file"]).write_bytes(b"")
    return folder


def _jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def make_data_root(root: Path) -> Path:
    """Write a tiny copy of the three dataset layouts under *root*; return it.

    FinanceBench: 6 questions over 4 PDFs. FreshStack: 6 queries over 8 parents
    plus the overlay file. BioASQ: 6 questions over 12 passages.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    fb = root / "benchmarks" / "financebench"
    docs = ["ACME_2020_10K", "ACME_2021_10K", "BETA_2022_10K", "GAMMA_2023_10K"]
    (fb / "pdfs").mkdir(parents=True)
    for doc in docs:
        (fb / "pdfs" / f"{doc}.pdf").write_bytes(doc.encode())
    (fb / "PDFS_MANIFEST.json").write_text(
        json.dumps({"files": {doc: {"sha256": "0" * 64} for doc in docs}}), encoding="utf-8"
    )
    _jsonl(
        fb / "financebench_merged.jsonl",
        [
            {
                "financebench_id": f"financebench_id_{i:05d}",
                "doc_name": docs[i % 3],
                "question": f"FinanceBench question {i}?",
                "answer": f"answer {i}",
                "evidence": [
                    {"doc_name": docs[i % 3], "evidence_page_num": i, "evidence_text": ""}
                ],
            }
            for i in range(6)
        ],
    )

    fs = root / "experiments" / "freshstack-corpus"
    manifest = []
    for i in range(8):
        topic = "continuity" if i == 7 else "langchain"
        name = f"{i:05d}_{i:012x}.md"
        parent = "continuity/sample.md" if i == 7 else f"repo/file{i}.md_0_10"
        (fs / topic).mkdir(parents=True, exist_ok=True)
        (fs / topic / name).write_text(f"parent {i}", encoding="utf-8")
        manifest.append({"freshstack_id": parent, "metadata": {"file_name": name, "topic": topic}})
    _jsonl(fs / "langchain_manifest.jsonl", manifest)
    overlay = root / "benchmarks" / "freshstack" / "overlay" / "zzqj-9097-runbook.md"
    overlay.parent.mkdir(parents=True)
    overlay.write_text("rotate the amber token", encoding="utf-8")
    gt = root / "experiments" / "22-raw-query-qwen4b-baseline-2026-09-07" / "ground-truth.json"
    gt.parent.mkdir(parents=True)
    queries = [
        {
            "query_id": f"7650{i:04d}",
            "query": f"FreshStack query {i}",
            "answer_text": f"fs answer {i}",
            "relevant_parent_ids": [f"repo/file{i}.md_0_10"],
        }
        for i in range(5)
    ]
    queries.append(
        {
            "query_id": "continuity_009",
            "query": "Which token do I rotate?",
            "answer_text": "rotate the amber token",
            "relevant_parent_ids": ["continuity/zzqj-9097-runbook.md"],
        }
    )
    gt.write_text(json.dumps({"queries": queries}), encoding="utf-8")

    bio = root / "benchmarks" / "bioasq"
    (bio / "question-answer-passages").mkdir(parents=True)
    (bio / "text-corpus").mkdir(parents=True)
    questions = pa.table(
        {
            "question": [f"BioASQ question {i}?" for i in range(6)],
            "answer": [f"bio answer {i}" for i in range(6)],
            "id": list(range(100, 106)),
            "relevant_passage_ids": [[1000 + i, 1006 + i] for i in range(6)],
        }
    )
    pq.write_table(questions, bio / "question-answer-passages" / "test-00000-of-00001.parquet")
    corpus = pa.table(
        {"passage": [f"abstract {i}" for i in range(12)], "id": [1000 + i for i in range(12)]}
    )
    pq.write_table(corpus, bio / "text-corpus" / "test-00000-of-00001.parquet")
    return root
