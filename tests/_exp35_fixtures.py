"""Shared fixtures for the Experiment 35 harness tests (``test_experiment35_*.py``).

Everything is synthetic: a fake plan, empty GGUF files and a tiny copy of the
four dataset layouts in a tmp folder. Nothing reads the DATA folder, a GGUF
file or the network.
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
_RERANK = {
    "reranker-0.6b": "Qwen3-Reranker-0.6B-Q8_0.gguf",
    "reranker-4b": "Qwen3-Reranker-4B-Q8_0.gguf",
    "reranker-8b": "Qwen3-Reranker-8B-Q8_0.gguf",
}
#: The FreshStack corpus pin of the fake plan (the real one is recorded at P1).
FS_REVISION = "fixture-revision-0001"
FS_ROWS = 6


def load(name: str) -> ModuleType:
    """Import one experiment module by path, once per name."""
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


def _model(role: str, file: str, digest: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": role,
        "repository": f"Qwen/{file.rsplit('-', 1)[0]}-GGUF",
        "file": file,
        "sha256": digest * 64,
        "runtime": "llama.cpp",
        "build": 11941,
        "server_args": args,
    }


def fake_plan() -> dict[str, Any]:
    """Return a plan with three embedders, three rerankers, Clef-Flash, seeds and pins."""
    embed_args = {
        "embeddings": True,
        "pooling": "last",
        "ctx-size": 8192,
        "batch-size": 8192,
        "ubatch-size": 8192,
    }
    rank_args = {"embeddings": True, "pooling": "rank", "ctx-size": 8192}
    models = [_model(r, f, "a", embed_args) for r, f in _EMBED.items()]
    models += [_model(r, f, "d", rank_args) for r, f in _RERANK.items()]
    models.append(
        {
            **_model("judge-clef-flash", "Clef-Flash-Q8_0.gguf", "b", {"ctx-size": 32768}),
            "repository": "ggml-org/Clef-Flash-GGUF",
        }
    )
    return {
        "protocol_version": 2,
        "seed": 20261101,
        "frozen": [],
        "runtime": {"models": models},
        "seeds": {
            "answer": 20261101,
            "question_order": 20261101,
            "smoke_sample": 20261101,
            "glm": 20261109,
            "ragas_judge": 20261140,
            "classifier": 20261141,
        },
        "pins": {
            "settings": {
                "pdf_reader": "pdf_inspector",
                "embedding": {"query_instruction": ""},
                "answer": {"reasoning": "low", "max_output_tokens": 2048},
                "retrieval": {"hybrid_rrf_k": 60},
            },
            "recorded": {
                "reranker_instruction": "Given a web search query, retrieve relevant passages",
                "hybrid": {"fusion_depth": 100, "bm25_tokeniser": "omrs-default"},
            },
            "datasets": {"freshstack": {"revision": FS_REVISION, "rows": FS_ROWS}},
        },
    }


def make_gguf(folder: Path) -> Path:
    """Write an empty file per fake plan model; return the folder."""
    folder.mkdir(parents=True, exist_ok=True)
    for model in fake_plan()["runtime"]["models"]:
        (folder / model["file"]).write_bytes(b"")
    return folder


def _jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _parquet(path: Path, columns: dict[str, list[Any]]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(columns), path)


#: FreshStack corpus rows of the fixture: (corpus ID, text).
FS_ROWS_DATA = [
    ("repo/README.md_0_40", "# Title\n\nSome prose.\n"),
    ("repo/docs/guide.mdx_0_20", "Guide text\n"),
    ("repo/src/app.py_0_60", "# a comment\nprint('x')\n```\ninside\n```\n"),
    ("repo/LICENSE_0_10", "MIT licence\n"),
    ("repo/nb/demo.ipynb_0_30", '{"cells": []}\n'),
    ("repo/src/util.py_60_90", "def f():\n    return 1\n"),
]


def make_data_root(root: Path) -> Path:
    """Write a tiny copy of the four dataset layouts under *root*; return it.

    FinanceBench: 6 questions over 4 PDFs. FreshStack: 5 queries plus one
    continuity query over 6 corpus rows. BioASQ: 6 questions over 12 passages.
    Legal RAG Bench: 100 questions over 101 passages.
    """
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

    corpus = root / "benchmarks" / "freshstack" / "corpus-oct-2024" / "langchain"
    _parquet(
        corpus / "train-00000-of-00001.parquet",
        {"_id": [r[0] for r in FS_ROWS_DATA], "text": [r[1] for r in FS_ROWS_DATA]},
    )
    (corpus / "download.json").write_text(
        json.dumps({"repository": "freshstack/corpus-oct-2024", "revision": FS_REVISION}),
        encoding="utf-8",
    )
    gt = root / "experiments" / "22-raw-query-qwen4b-baseline-2026-09-07" / "ground-truth.json"
    queries = [
        {
            "query_id": f"7650{i:04d}",
            "query_title": f"FreshStack title {i}",
            "query_text": f"FreshStack body {i}?",
            "query": "ignored",
            "answer_text": f"fs answer {i}",
            "relevant_parent_ids": [FS_ROWS_DATA[i][0]],
        }
        for i in range(5)
    ]
    queries.append(
        {
            "query_id": "continuity_009",
            "query_title": "Which token",
            "query_text": "do I rotate?",
            "answer_text": "rotate amber token",
            "relevant_parent_ids": ["continuity/zzqj-9097-runbook.md"],
        }
    )
    gt.parent.mkdir(parents=True)
    gt.write_text(json.dumps({"queries": queries}), encoding="utf-8")

    bio = root / "benchmarks" / "bioasq"
    _parquet(
        bio / "question-answer-passages" / "test-00000-of-00001.parquet",
        {
            "question": [f"BioASQ question {i}?" for i in range(6)],
            "answer": [f"bio answer {i}" for i in range(6)],
            "id": list(range(100, 106)),
            "relevant_passage_ids": [[1000 + i, 1006 + i] for i in range(6)],
        },
    )
    _parquet(
        bio / "text-corpus" / "test-00000-of-00001.parquet",
        {
            "passage": [f"abstract {i}\n# not a heading" for i in range(12)],
            "id": [1000 + i for i in range(12)],
        },
    )

    legal = root / "benchmarks" / "legal-rag-bench"
    _parquet(
        legal / "qa" / "test-00000-of-00001.parquet",
        {
            "id": [f"lq{i:03d}" for i in range(100)],
            "question": [f"Legal question {i}?" for i in range(100)],
            "answer": [f"legal answer {i}" for i in range(100)],
            "relevant_passage_id": [f"lp{i:03d}" for i in range(100)],
        },
    )
    _parquet(
        legal / "corpus" / "test-00000-of-00001.parquet",
        {
            "id": [f"lp{i:03d}" for i in range(101)],
            "title": [f"Section {i}" for i in range(101)],
            "text": [f"Text of passage {i}.\n#5 is a number" for i in range(101)],
            "footnotes": [f"Footnote {i}." if i % 2 else "" for i in range(101)],
        },
    )
    return root
