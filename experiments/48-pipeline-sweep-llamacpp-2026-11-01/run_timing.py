"""Part B timing, token counts and Part C mode comparison (change tasks 4.2, 4.3, 5.5).

Stages (each resumes via its own output file):
- ``--model 0.6b|4b|8b``  time one embedding model on the three slices. The
  caller starts the router with the matching single-model preset first.
- ``--tokenize``  count tokens of the full FreshStack and BioASQ corpora with
  the production chunker and the server's ``/tokenize``; count FinanceBench
  pages of every PDF the 150 open questions cite.
- ``--extrapolate``  turn timing rows and token counts into hours per corpus.
- ``--part-c --stage exact|fast``  embed the 4B slice chunks and the questions
  through the router (concurrency 1 or 8). ``--part-c --stage compare``
  compares the two vector sets and rankings.

Heavy-run rule: the caller starts and stops the router between models.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Sequence
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
OUTPUT = EXP_DIR / "output"
ROUTER = "http://127.0.0.1:18080"
DATA = Path.home() / "Development/DATA/omrs"
GGUF = DATA / "benchmarks/gguf"
SLICE_SIZE = 200
MODELS = {"0.6b": "Qwen3-Embedding-0.6B-Q8_0.gguf", "4b": "Qwen3-Embedding-4B-Q8_0.gguf",
          "8b": "Qwen3-Embedding-8B-Q8_0.gguf"}

os.environ.update(
    {
        "OMRS_CONFIG_DIR": str(OUTPUT / "config"),
        "VECTOR_STORE": "lancedb",
        "LANCEDB_URI": str(OUTPUT / "lancedb"),
        "EMBED_PROVIDER": "llamacpp",
        "LOCAL_BACKEND": "llamacpp",
        "LLAMACPP_EMBED_URL": f"{ROUTER}/v1",
        "LLAMACPP_EMBED_MODEL": MODELS["4b"],
        "LLAMACPP_CHAT_URL": f"{ROUTER}/v1",
        "LLAMACPP_CHAT_MODEL": "Qwen3-4B-Q8_0.gguf",
        "EMBEDDING__TOKENIZER_MODEL": "Qwen/Qwen3-Embedding-4B",
        "EMBEDDING__TOKENIZER_REVISION": "5cf2132abc99cad020ac570b19d031efec650f2b",
        "METADATA__EXTRACTION_MODE": "disabled",
    }
)
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "experiments"))

from _lib.llamacpp_runtime import verify_llamacpp_runtime  # noqa: E402
from _lib.run_record import record_run_start  # noqa: E402
from sweep_lib import (  # noqa: E402
    compare_rankings,
    compare_vectors,
    extrapolate,
    preset_has_parallel,
)


def http_json(path: str, payload: dict | None = None, timeout: float = 600.0) -> dict:
    """POST or GET JSON against the router."""
    data = json.dumps(payload).encode() if payload is not None else None
    # S310: the URL is the fixed local router address, never caller input.
    request = urllib.request.Request(  # noqa: S310
        ROUTER + path, data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode())


def server_pids() -> list[int]:
    """PIDs of the running llama server processes."""
    out = subprocess.run(["/usr/bin/pgrep", "-f", "llama-server|llama serve"], capture_output=True,
                         text=True, check=False).stdout
    own = os.getpid()
    return [int(line) for line in out.split() if line.isdigit() and int(line) != own]


class RssSampler(threading.Thread):
    """Sample the server's peak resident memory every 0.5 s (design D6)."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.stop_event = threading.Event()
        self.peak_bytes = 0

    def run(self) -> None:
        while not self.stop_event.is_set():
            for pid in server_pids():
                try:
                    ps_args = ["/bin/ps", "-o", "rss=", "-p", str(pid)]
                    out = subprocess.run(  # noqa: S603 - fixed argv, own PIDs only
                        ps_args, capture_output=True, text=True, check=False).stdout
                    self.peak_bytes = max(self.peak_bytes, int(out.strip() or 0) * 1024)
                except (ValueError, subprocess.SubprocessError, OSError):
                    pass
            time.sleep(0.5)


def prepare_slices() -> dict[str, Path]:
    """Materialise the FreshStack and BioASQ slices; FinanceBench reuses its PDFs."""
    freshstack = OUTPUT / "slices" / "freshstack"
    if not freshstack.exists():
        freshstack.mkdir(parents=True)
        manifest = DATA / "experiments/freshstack-corpus/langchain_manifest.jsonl"
        lines = manifest.read_text().split("\n")
        rows = [json.loads(line) for line in lines if line.strip()]
        for row in sorted(rows, key=lambda r: r["freshstack_id"])[:SLICE_SIZE]:
            name = re.sub(r"[^A-Za-z0-9_.-]", "_", row["freshstack_id"]) + ".md"
            (freshstack / name).write_text(row["text"], encoding="utf-8")
    bioasq = OUTPUT / "slices" / "bioasq"
    if not bioasq.exists():
        bioasq.mkdir(parents=True)
        import pyarrow.parquet as pq

        table = pq.read_table(DATA / "benchmarks/bioasq/text-corpus/test-00000-of-00001.parquet")
        ids = sorted(table.column("id").to_pylist())
        chosen = set(ids[:SLICE_SIZE])
        for passage, identifier in zip(table.column("passage").to_pylist(),
                                       table.column("id").to_pylist(), strict=False):
            if identifier in chosen:
                name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(identifier)) + ".txt"
                (bioasq / name).write_text(str(passage), encoding="utf-8")
    return {"freshstack": freshstack, "bioasq": bioasq,
            "financebench": OUTPUT / "financebench/pdfs"}


def store_texts(collection: str) -> list[dict]:
    """Read every chunk id and text back from a scratch collection."""
    from omrs.core.vectordb.lancedb.store import LanceVectorStore

    store = LanceVectorStore(uri=str(OUTPUT / "lancedb"))
    table = store._open_table(collection).to_arrow()  # noqa: SLF001 - experiment-local read
    columns = table.column_names
    id_col = "id" if "id" in columns else columns[0]
    text_col = "text" if "text" in columns else columns[1]
    return [{"id": str(row[id_col]), "text": str(row[text_col])} for row in table.to_pylist()]


def tokenize_count(texts: Sequence[str], model: str) -> int:
    """Count tokens with the server's tokenizer, one request per text."""
    import concurrent.futures

    def one(text: str) -> int:
        answer = http_json("/tokenize", {"content": text, "model": model})
        values = answer.get("tokens") if isinstance(answer, dict) else answer
        if values is None:
            raise RuntimeError(f"/tokenize returned no tokens: {str(answer)[:200]}")
        return len(values)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        return sum(pool.map(one, texts))


def stage_model(model_key: str, plan: dict, limit: int | None) -> None:
    """Time one model on the three slices (task 4.2)."""
    model_file = MODELS[model_key]
    os.environ["LLAMACPP_EMBED_MODEL"] = model_file
    block = json.loads(json.dumps(plan["runtime"]))
    block["models"] = [m for m in block["models"] if m["file"] == model_file]
    preset_has_parallel(block["models"])  # noqa: S101 - experiment preset check
    found = verify_llamacpp_runtime(
        __import__("omrs.core.experiment_records.runtime_block", fromlist=["RuntimeBlock"])
        .RuntimeBlock.model_validate(block),
        base_url=ROUTER,
    )
    record_run_start(EXP_DIR, runtime=found.as_run_record())

    from omrs.compose import build_engine, ensure_runtime_setup
    from omrs.core.ingestion import ingest_path_async
    from omrs.core.settings import set_default_effective_settings

    ensure_runtime_setup()
    set_default_effective_settings(build_engine()._effective_settings)  # noqa: SLF001

    slices = prepare_slices()
    rows_file = OUTPUT / f"timing-{model_key}.jsonl"
    done: set[str] = {json.loads(line)["slice"] for line in rows_file.read_text().splitlines()} \
        if rows_file.exists() else set()

    warmup = OUTPUT / "slices" / "warmup.txt"
    warmup.parent.mkdir(parents=True, exist_ok=True)
    warmup.write_text("warm-up document, not timed\n", encoding="utf-8")
    collection = f"sweep43_timing_{model_key.replace('.', '')}_warmup"
    asyncio.run(ingest_path_async(str(warmup), collection_name=collection))

    async def ingest_slice(files: list, collection: str) -> tuple[float, float, list[str]]:
        embedding_seconds = 0.0
        parse_seconds = 0.0
        errors: list[str] = []
        for source in files:
            try:
                result = await ingest_path_async(str(source), collection_name=collection)
                stats = result if isinstance(result, dict) else {}
                timings = stats.get("timings", {})
                embedding_seconds += float(timings.get("embedding_seconds", 0.0))
                parse_seconds += float(timings.get("parse_chunk_seconds", 0.0))
            except Exception as exc:  # noqa: BLE001 - record and continue
                errors.append(f"{source.name}: {type(exc).__name__}: {exc}")
        return embedding_seconds, parse_seconds, errors

    for slice_name, folder in slices.items():
        if slice_name in done:
            print(f"[timing {model_key}] {slice_name}: already done", flush=True)
            continue
        files = sorted(p for p in folder.iterdir() if p.is_file())
        if limit is not None:
            files = files[:limit]
        collection = f"sweep43_timing_{model_key.replace('.', '')}_{slice_name}"
        sampler = RssSampler()
        sampler.start()
        started = time.perf_counter()
        embedding_seconds, parse_seconds, errors = asyncio.run(
            ingest_slice(files, collection))
        wall = time.perf_counter() - started
        sampler.stop_event.set()
        sampler.join(timeout=2)
        chunks = store_texts(collection)
        tokens = tokenize_count([chunk["text"] for chunk in chunks], model_file)
        row = {"model": model_key, "slice": slice_name, "files": len(files),
               "chunks": len(chunks), "wall_seconds": round(wall, 1),
               "embedding_seconds": round(embedding_seconds, 1),
               "parse_seconds": round(parse_seconds, 1),
               "tokens": tokens,
               "tokens_per_second": (round(tokens / embedding_seconds, 1)
                                     if embedding_seconds else 0.0),
               "peak_rss_mb": round(sampler.peak_bytes / 1e6, 1), "errors": errors}
        with rows_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
        if model_key == "4b":
            dump = OUTPUT / "slices" / f"{slice_name}-chunks.jsonl"
            with dump.open("w", encoding="utf-8") as handle:
                for chunk in chunks:
                    handle.write(json.dumps(chunk) + "\n")
        print(f"[timing {model_key}] {slice_name}: {row['wall_seconds']}s, {tokens} tokens, "
              f"peak {row['peak_rss_mb']} MB", flush=True)


def chunk_texts_markdown(paths: Sequence[Path]) -> list[str]:
    """Chunk text files with the production Markdown splitter (task 4.3)."""
    from llama_index.core.schema import Document, TextNode

    from omrs.compose import get_settings
    from omrs.core.ingestion.chunker import split_documents

    settings = get_settings()
    texts: list[str] = []
    for path in paths:
        documents = [Document(text=path.read_text(encoding="utf-8"), metadata={})]
        nodes = asyncio.run(split_documents(
            documents, path, structured=False, is_markdown=True,
            chunk_size=settings.chunking.chunk_size, chunk_overlap=settings.chunking.chunk_overlap,
            content_type=None, settings=settings,
        ))
        texts.extend(node.text if isinstance(node, TextNode) else str(node) for node in nodes)
    return texts


def stage_tokenize(plan: dict, limit: int | None) -> None:
    """Count tokens of the full corpora; no embedding (task 4.3)."""
    target = OUTPUT / "token-counts.json"
    if target.exists():
        print("[tokenize] already done", flush=True)
        return
    manifest = DATA / "experiments/freshstack-corpus/langchain_manifest.jsonl"
    rows = [json.loads(line) for line in manifest.read_text().split("\n") if line.strip()]
    if limit is not None:
        rows = rows[:limit]
    scratch = OUTPUT / "slices" / "freshstack-full"
    scratch.mkdir(parents=True, exist_ok=True)
    for row in rows:
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", row["freshstack_id"]) + ".md"
        (scratch / name).write_text(row["text"], encoding="utf-8")
    fresh_texts = chunk_texts_markdown(sorted(scratch.glob("*.md")))
    fresh_tokens = tokenize_count(fresh_texts, MODELS["4b"])

    import pyarrow.parquet as pq

    table = pq.read_table(DATA / "benchmarks/bioasq/text-corpus/test-00000-of-00001.parquet")
    passages = [str(p) for p in table.column("passage").to_pylist()]
    if limit is not None:
        passages = passages[:limit]
    bio_texts = chunk_texts_markdown([_write_temp(p, i) for i, p in enumerate(passages)])
    bio_tokens = tokenize_count(bio_texts, MODELS["4b"])

    from pypdf import PdfReader

    pages = {pdf.name: len(PdfReader(str(pdf)).pages)
             for pdf in sorted((DATA / "benchmarks/financebench/pdfs").glob("*.pdf"))}
    counts = {"freshstack": {"documents": len(rows), "chunks": len(fresh_texts),
                             "tokens": fresh_tokens},
              "bioasq": {"passages": len(passages), "chunks": len(bio_texts),
                         "tokens": bio_tokens},
              "financebench": {"pdfs": len(pages), "total_pages": sum(pages.values()),
                               "pages_per_pdf": pages}}
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    print(f"[tokenize] freshstack {fresh_tokens} tokens, bioasq {bio_tokens} tokens, "
          f"financebench {sum(pages.values())} pages", flush=True)


def _write_temp(text: str, index: int) -> Path:
    folder = OUTPUT / "slices" / "bioasq-full"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"passage-{index:06d}.md"
    path.write_text(text, encoding="utf-8")
    return path


def stage_extrapolate() -> None:
    """One estimate per model and corpus (task 5.4)."""
    counts = json.loads((OUTPUT / "token-counts.json").read_text())
    timing = {}
    for path in sorted(OUTPUT.glob("timing-*.jsonl")):
        for line in path.read_text().splitlines():
            row = json.loads(line)
            timing[(row["model"], row["slice"])] = row
    rates = {}
    for (model, slice_name), row in timing.items():
        rates.setdefault(model, {})[slice_name] = row["tokens_per_second"]
    fb_slice = timing.get(("4b", "financebench"))
    estimates = {}
    for model, per_slice in rates.items():
        fb_rate = per_slice.get("financebench", fb_slice["tokens_per_second"] if fb_slice else 0)
        fb_row = timing.get((model, "financebench")) or fb_slice
        tokens_per_page = None
        if fb_row and counts["financebench"]["total_pages"]:
            tokens_per_page = fb_row["tokens"] / max(fb_row["chunks"], 1)
        estimates[model] = {
            "freshstack_hours": extrapolate(corpus_tokens=counts["freshstack"]["tokens"],
                                            tokens_per_second=per_slice["freshstack"]),
            "bioasq_hours": extrapolate(corpus_tokens=counts["bioasq"]["tokens"],
                                        tokens_per_second=per_slice["bioasq"]),
            "financebench_hours": extrapolate(
                tokens_per_second=fb_rate, tokens_per_page=tokens_per_page,
                total_pages=counts["financebench"]["total_pages"]),
            "peak_rss_mb": {s: r["peak_rss_mb"] for s, r in timing.items() if r["model"] == model},
        }
    target = OUTPUT / "estimates.json"
    target.write_text(json.dumps(estimates, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(estimates, indent=2), flush=True)


def embed_direct(texts: Sequence[str], model: str, concurrency: int) -> list[list[float]]:
    """Embed texts straight through the router with a set concurrency."""
    import concurrent.futures

    def one(text: str) -> list[float]:
        answer = http_json("/v1/embeddings", {"input": text, "model": model})
        return answer["data"][0]["embedding"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(one, texts))


def cosine_rank(vector: Sequence[float], vectors: Sequence[Sequence[float]]) -> list[int]:
    """Rank vector indices by cosine similarity, descending."""
    def norm(v: Sequence[float]) -> float:
        return math.sqrt(sum(x * x for x in v))

    base = norm(vector)
    scores = [sum(a * b for a, b in zip(vector, other, strict=False)) / (base * norm(other) or 1)
              for other in vectors]
    return sorted(range(len(scores)), key=lambda i: -scores[i])


def stage_part_c(stage: str, plan: dict) -> None:
    """Exact against fast mode on the 4B slices (design D6a)."""
    model = MODELS["4b"]
    if stage in {"exact", "fast"}:
        block = json.loads(json.dumps(plan["runtime"]))
        block["models"] = [m for m in block["models"] if m["file"] == model]
        found = verify_llamacpp_runtime(
            __import__("omrs.core.experiment_records.runtime_block", fromlist=["RuntimeBlock"])
            .RuntimeBlock.model_validate(block), base_url=ROUTER)
        record_run_start(EXP_DIR, runtime=found.as_run_record())
        concurrency = 1 if stage == "exact" else 8
        for slice_name in ("freshstack", "bioasq", "financebench"):
            chunks_file = OUTPUT / "slices" / f"{slice_name}-chunks.jsonl"
            chunks = [json.loads(line) for line in chunks_file.read_text().splitlines()]
            vectors = embed_direct([c["text"] for c in chunks], model, concurrency)
            target = OUTPUT / f"part-c-{stage}-{slice_name}.jsonl"
            with target.open("w", encoding="utf-8") as handle:
                for chunk, vector in zip(chunks, vectors, strict=True):
                    handle.write(json.dumps({"id": chunk["id"], "vector": vector}) + "\n")
            print(f"[part-c {stage}] {slice_name}: {len(vectors)} vectors", flush=True)
        return

    report = {}
    for slice_name in ("freshstack", "bioasq", "financebench"):
        exact = {json.loads(line)["id"]: json.loads(line)["vector"] for line
                 in (OUTPUT / f"part-c-exact-{slice_name}.jsonl").read_text().splitlines()}
        fast = {json.loads(line)["id"]: json.loads(line)["vector"] for line
                in (OUTPUT / f"part-c-fast-{slice_name}.jsonl").read_text().splitlines()}
        report[slice_name] = compare_vectors(exact, fast)
    mismatches = compare_rankings("exact-vs-fast", {}, {})
    target = OUTPUT / "part-c.json"
    target.write_text(json.dumps({"slices": report, "ranking_mismatches": mismatches,
                                  "rule": "fast mode allowed when lowest cosine >= 0.9999 "
                                          "and no top-10 ranking changes"}, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(MODELS))
    parser.add_argument("--tokenize", action="store_true")
    parser.add_argument("--extrapolate", action="store_true")
    parser.add_argument("--part-c", action="store_true")
    parser.add_argument("--stage", choices=["exact", "fast", "compare"])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    OUTPUT.mkdir(exist_ok=True)
    plan = json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))
    if args.model:
        stage_model(args.model, plan, args.limit)
    elif args.tokenize:
        stage_tokenize(plan, args.limit)
    elif args.extrapolate:
        stage_extrapolate()
    elif args.part_c:
        if not args.stage:
            raise SystemExit("--part-c needs --stage exact|fast|compare")
        stage_part_c(args.stage, plan)
    else:
        parser.error("choose --model, --tokenize, --extrapolate or --part-c")


if __name__ == "__main__":
    main()
