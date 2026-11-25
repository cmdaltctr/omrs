"""Shared fixtures for the Experiment 35 harness tests (``test_experiment35_*.py``).

Everything is synthetic: a fake plan, empty GGUF files and a tiny copy of the
four dataset layouts in a tmp folder. Nothing reads the DATA folder, a GGUF
file or the network.
"""

from __future__ import annotations

import functools
import hashlib
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
FS_ROWS = 8
#: Distinct pairs of corpus ID and text, one passage file each (owner decision, 2026-11-23).
FS_FILES = 7
#: The one parquet file of the fixture FreshStack corpus.
FS_CORPUS_FILE = "train-00000-of-00001.parquet"


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
    corpus = {FS_CORPUS_FILE: hashlib.sha256(fs_corpus_bytes()).hexdigest()}
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
                "ocr_fallback_enabled": False,
                "embedding": {"query_instruction": ""},
                "answer": {"reasoning": "low", "max_output_tokens": 2048},
                "retrieval": {"hybrid_rrf_k": 60},
            },
            "recorded": {
                "reranker_instruction": "Given a web search query, retrieve relevant passages",
                "hybrid": {"fusion_depth": 100, "bm25_tokeniser": "omrs-default"},
            },
            "ragas_judge": {"host": "hostj", "reasoning": "low", "temperature": 0.0},
            "datasets": {
                "freshstack": {
                    "revision": FS_REVISION,
                    "rows": FS_ROWS,
                    "files": FS_FILES,
                    "corpus_files": corpus,
                    "corpus_tree_sha256": load("datasets35").tree_hash(corpus),
                }
            },
            "prompts": {"answer": "b" * 64},
            "pending": [],
        },
    }


def unpin(plan: dict[str, Any], key: str, task: str) -> dict[str, Any]:
    """Set the plan value at dotted *key* to ``null`` and list it in ``pins.pending``.

    This is how ``plan.json`` holds a value that a pre-freeze task has not recorded yet.
    """
    *parents, leaf = key.split(".")
    node = plan
    for part in parents:
        node = node[part]
    node[leaf] = None
    plan["pins"]["pending"].append({"key": key, "task": task})
    return plan


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


#: FreshStack corpus rows of the fixture: (corpus ID, text). As in the real corpus, one
#: non-gold ID repeats: once with a second text and once exactly (same ID, same text).
FS_ROWS_DATA = [
    ("repo/README.md_0_40", "# Title\n\nSome prose.\n"),
    ("repo/docs/guide.mdx_0_20", "Guide text\n"),
    ("repo/src/app.py_0_60", "# a comment\nprint('x')\n```\ninside\n```\n"),
    ("repo/LICENSE_0_10", "MIT licence\n"),
    ("repo/nb/demo.ipynb_0_30", '{"cells": []}\n'),
    ("repo/src/util.py_60_90", "def f():\n    return 1\n"),
    ("repo/src/util.py_60_90", "def f():\n    return 2\n"),
    ("repo/src/util.py_60_90", "def f():\n    return 1\n"),
]


def fs_source(corpus_id: str) -> dict[str, Any]:
    """Return the fixture row's published ``metadata``: source URL and byte span from its ID."""
    path, start, end = corpus_id.rsplit("_", 2)
    url = f"https://github.com/example/{path}"
    return {"url": url, "start_byte": int(start), "end_byte": int(end)}


@functools.lru_cache(maxsize=1)
def fs_corpus_bytes() -> bytes:
    """Return the fixture FreshStack parquet file, built once so that its SHA-256 is fixed.

    ``fake_plan`` pins this SHA-256 in ``corpus_files``; ``make_data_root`` writes the bytes.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    columns = {
        "_id": [r[0] for r in FS_ROWS_DATA],
        "text": [r[1] for r in FS_ROWS_DATA],
        "metadata": [fs_source(r[0]) for r in FS_ROWS_DATA],
    }
    sink = pa.BufferOutputStream()
    pq.write_table(pa.table(columns), sink)
    return bytes(sink.getvalue().to_pybytes())


def make_data_root(root: Path) -> Path:
    """Write a tiny copy of the four dataset layouts under *root*; return it.

    FinanceBench: 6 questions over 4 PDFs. FreshStack: 5 queries plus one
    continuity query over 8 corpus rows (7 distinct pairs of ID and text). BioASQ:
    6 questions over 12 passages.
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
    corpus.mkdir(parents=True)
    (corpus / FS_CORPUS_FILE).write_bytes(fs_corpus_bytes())
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


# --- search, answer and judge stage fixtures (package B2) --------------------------------

#: The configuration the fixture index's ingest done-marker holds (review R2-05).
INDEX_CONFIG = {"settings_sha256": "1" * 64, "harness_commit": "c0ffee", "run_mode": "main"}


def seal_fixture(layout: Any, dataset: str, setup: str, *, backend: str = "bm25") -> Any:
    """Write a small LanceDB table, its fingerprint and a passing ``rebuild.json``.

    Returns the setup's ``arms.Setup``. Nothing reads a model or the network.
    """
    import lancedb
    import pyarrow as pa

    arms = load("arms")
    outputs35 = load("outputs35")
    factors = arms.parse_setup(setup)
    collection = factors.collection(dataset)
    store = layout.store(factors.index)
    rows = [{"id": f"c{i}", "text": f"chunk {i}", "vector": [0.1, 0.2]} for i in range(3)]
    schema = pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), 2)),
        ]
    )
    db = lancedb.connect(str(store))
    db.create_table(collection, data=pa.Table.from_pylist(rows, schema=schema), exist_ok=True)
    version = db.open_table(collection).version
    outputs35.write_json(
        layout.fingerprint(dataset, factors.index),
        {"collection": collection, "table_version": version, "sparse_backend": backend},
    )
    outputs35.write_json(layout.root / dataset / "rebuild.json", {"ok": True})
    outputs35.write_json(
        layout.index_dir(dataset, factors.index) / ".done-ingest.json", {"config": INDEX_CONFIG}
    )
    return factors


class FakeTokens:
    """A whitespace token counter: one token per word."""

    @staticmethod
    def count(text: str) -> int:
        return len(text.split())

    @staticmethod
    def truncate(text: str, n: int) -> str:
        return " ".join(text.split()[:n])


def open_half_b(root: Path, **selection: Any) -> None:
    """Write ``selection.json`` and an OSF time-stamp of its hash: half B is open (task 16.17)."""
    digest = "a" * 64
    root.mkdir(parents=True, exist_ok=True)
    (root / "selection.json").write_text(json.dumps({**selection, "configuration_hash": digest}))
    stamp = {"uploaded_at": "t", "file_sha256": "f" * 64, "configuration_hash": digest}
    (root / "osf-timestamp.json").write_text(json.dumps(stamp))


def stage_ctx(
    tmp_path: Path,
    stage: str,
    setup: str,
    *,
    kind: str,
    questions: Any,
    engine: Any = None,
    dataset: str = "bioasq",
    resume: bool = False,
    overlap: int | None = None,
    args: Any = None,
    run: int = 1,
    judge: Any = None,
) -> Any:
    """Return a ``stages35.Ctx`` of one setup on a sealed fixture index."""
    from types import SimpleNamespace

    from experiments._lib.trace import TraceWriter

    arms = load("arms")
    outputs35 = load("outputs35")
    stages35 = load("stages35")
    layout = outputs35.Layout(tmp_path / "out")
    open_half_b(layout.root)
    factors = seal_fixture(layout, dataset, setup)
    run_dir = layout.run_dir(dataset, kind, setup, run)
    trace = TraceWriter(
        run_dir / "traces.jsonl",
        benchmark_revision="test",
        run_id=f"{dataset}/{setup}/run{run}",
        arm=setup,
        repetition=run,
        effective_settings={"setup": setup},
        model_identities={},
    )
    settings = SimpleNamespace(
        retrieval=SimpleNamespace(hybrid_sparse_backend="bm25"),
        chunking=SimpleNamespace(
            chunk_overlap=overlap if overlap is not None else arms.OVERLAPS[factors.chunk]
        ),
        answer=SimpleNamespace(context_window=131072, max_output_tokens=2048, max_rounds=1),
    )
    defaults = {
        "answer_concurrency": 8,
        "chat_concurrency": 4,
        "rate_limit_attempts": 6,
        "prefreeze": False,
        "smoke": False,
        "judges": "",
        "answers": None,
    }
    return stages35.Ctx(
        dataset=dataset,
        setup=setup,
        kind=kind,
        run=run,
        questions=list(questions),
        layout=layout,
        key=outputs35.run_key(
            None, None, 20261101, [q.qid for q in questions], config={"index_config": INDEX_CONFIG}
        ),
        resume=resume,
        trace=trace,
        engine=engine,
        settings=settings,
        args=SimpleNamespace(**{**defaults, **(args or {})}),
        tokens=FakeTokens(),
        judge=judge,
    )
