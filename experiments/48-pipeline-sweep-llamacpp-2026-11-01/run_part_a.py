"""Part A: the end-to-end pipeline sweep on llama.cpp (change tasks 3.2 to 3.4, design D4).

Modes:
- default   hash check, chunking guard, live-server check, run record, ingest,
            four search modes, answers with claim checking off then on.
- determinism   rerun the four search modes in this new process on the same
            index and compare rankings exactly (task 3.3).
- arms      rebuild a dense index with one comparison embedding model
            (--model 0.6b or 8b) and answer the 17 questions, reranker off
            (task 3.4).

Every stage writes one JSONL file in ``output/`` and a done-marker it checks
on ``--resume``. One failed item is recorded and the run continues.

Router (task 3.5): the script writes the scratch ``output/config/omrs.jsonc``
(``router_config``) and OMRS's managed router starts in this process and
stops when it exits. ``SWEEP_GGUF_DIR`` names the GGUF folder. ``--dry-run``
writes and loads the file, then exits before any router start or request.
Heavy-run rule: tell the user before a run without ``--dry-run``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
OUTPUT = EXP_DIR / "output"
COLLECTION = "sweep43"
ARM_MODELS = {"0.6b": "Qwen3-Embedding-0.6B-Q8_0.gguf", "8b": "Qwen3-Embedding-8B-Q8_0.gguf"}
BASELINE_MODEL = "Qwen3-Embedding-4B-Q8_0.gguf"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "experiments"))

import router_config  # noqa: E402

router_config.prepare_environment(
    {
        "VECTOR_STORE": "lancedb",
        "LANCEDB_URI": str(OUTPUT / "lancedb"),
        "EMBEDDING__TOKENIZER_MODEL": "Qwen/Qwen3-Embedding-4B",
        "EMBEDDING__TOKENIZER_REVISION": "5cf2132abc99cad020ac570b19d031efec650f2b",
        "METADATA__EXTRACTION_MODE": "disabled",
        "ANSWER__VERIFY_CLAIMS": "false",
    }
)

from _lib.llamacpp_runtime import verify_llamacpp_runtime  # noqa: E402
from _lib.run_record import record_run_start  # noqa: E402
from ranking_lib import (  # noqa: E402
    answer_fields,
    result_id,
    source_matches,
    write_props_snapshot,
)
from sweep_lib import chunking_guard, compare_rankings, verify_input_hashes  # noqa: E402

SEARCH_MODES = {
    "dense": {"hybrid": False, "rerank": False},
    "dense_rerank": {"hybrid": False, "rerank": True},
    "hybrid": {"hybrid": True, "rerank": False},
    "hybrid_rerank": {"hybrid": True, "rerank": True},
}


def frozen_paths(plan: dict) -> dict[str, dict[str, str]]:
    """Split the frozen list into per-folder name-to-SHA-256 maps."""
    maps: dict[str, dict[str, str]] = {"corpus": {}, "pdfs": {}, "gt": {}}
    for entry in plan["frozen"]:
        name, digest = entry["name"], entry["sha256"]
        if name == "ground-truth.json":
            maps["gt"][name] = digest
        elif name.startswith("corpus/"):
            maps["corpus"][name[len("corpus/"):]] = digest
        elif name.startswith("financebench/"):
            maps["pdfs"][name[len("financebench/"):]] = digest
    return maps


def load_questions() -> list[dict]:
    """The 17 Experiment 2 questions, in file order."""
    data = json.loads((EXP_DIR / "ground-truth.json").read_text(encoding="utf-8"))
    return data["queries"]


def load_financebench() -> list[dict]:
    """The frozen FinanceBench questions."""
    with (OUTPUT / "financebench-questions.jsonl").open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(name: str, rows: list[dict]) -> Path:
    """Atomically write one stage file in output/."""
    target = OUTPUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")
    tmp.replace(target)
    return target


def read_jsonl(name: str) -> list[dict]:
    with (OUTPUT / name).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def stage_done(stage: str) -> bool:
    return (OUTPUT / f".done-{stage}.json").exists()


def mark_done(stage: str, payload: dict) -> None:
    tmp = OUTPUT / f".done-{stage}.json.tmp"
    tmp.write_text(json.dumps(payload, default=str), encoding="utf-8")
    tmp.replace(OUTPUT / f".done-{stage}.json")


def score_row(row: dict, expected_source: str) -> dict:
    """Hit@1 and MRR contribution for one question against its gold source."""
    sources = [str(item.get("source", "")) for item in row.get("results", [])]
    hits = [source_matches(source, expected_source) for source in sources]
    return {
        "question": row["question"],
        "mode": row["mode"],
        "hit_at_1": hits[0] if hits else False,
        "reciprocal_rank": 1.0 / (hits.index(True) + 1) if True in hits else 0.0,
        "top_source": sources[0] if sources else "",
    }


def preflight(plan: dict, load: list[str], models: list[str] | None = None) -> dict:
    """Hash check, chunking guard, router start, live-server check, run record.

    The router loads *load*, the models this mode sends requests to. The check
    reads *models* (all plan models by default): the router lists every entry
    with its ``--model`` path, loaded or not.
    """
    from omrs.compose import get_settings

    maps = frozen_paths(plan)
    verify_input_hashes(EXP_DIR, maps["gt"])
    verify_input_hashes(EXP_DIR / "corpus", maps["corpus"])
    verify_input_hashes(OUTPUT / "financebench/pdfs", maps["pdfs"])

    settings = get_settings()
    chunking_guard(settings)
    router_config.start_router(load, plan)
    block = json.loads(json.dumps(plan["runtime"]))
    if models is not None:
        block["models"] = [m for m in block["models"] if m["file"] in models]
    found = verify_llamacpp_runtime(
        _load_block(block), base_url=router_config.verify_url(settings)
    )
    record_run_start(EXP_DIR, runtime=found.as_run_record())
    names = [router_config.model_name(router_config.plan_model(plan, f)) for f in load]
    write_props_snapshot(
        f"http://127.0.0.1:{router_config.ROUTER_PORT}",
        names,
        os.environ,
        OUTPUT / "server-props.jsonl",
        sys.argv,
    )
    return found.as_run_record()


def _load_block(block: dict):
    from omrs.core.experiment_records.runtime_block import RuntimeBlock

    return RuntimeBlock.model_validate(block)


def ingest_documents(build, limit: int | None, collection: str = COLLECTION) -> list[dict]:
    """Ingest each fixed-set document separately; record per-file stats."""
    from omrs.core.ingestion import ingest_path_async

    docs = sorted(p for p in (EXP_DIR / "corpus").iterdir() if p.is_file())
    docs += sorted((OUTPUT / "financebench/pdfs").glob("*.pdf"))
    if limit is not None:
        docs = docs[:limit]
    rows = []
    from omrs.compose import ensure_runtime_setup

    ensure_runtime_setup()  # composes the process-wide default store (module-level ingest)
    engine = build()
    from omrs.core.settings import set_default_effective_settings

    # The module-level ingest entry reads the default EffectiveSettings; the
    # engine lifecycle installs it, so mirror it here (engine_lifecycle.py).
    set_default_effective_settings(engine._effective_settings)  # noqa: SLF001

    async def ingest_all() -> list[dict]:

        stage: list[dict] = []
        for doc in docs:
            started = time.perf_counter()
            error = ""
            try:
                result = await ingest_path_async(str(doc), collection_name=collection)
                summary = json.dumps(result, default=str)[:2000]
            except Exception as exc:  # noqa: BLE001 - record and continue (D4)
                result, summary, error = None, "", f"{type(exc).__name__}: {exc}"
            stage.append({"file": doc.name, "seconds": round(time.perf_counter() - started, 2),
                          "error": error, "result": summary})
            print(f"[ingest] {doc.name}: {stage[-1]['seconds']}s"
                  + (f" ERROR {error}" if error else ""), flush=True)
        return stage

    try:
        rows = asyncio.run(ingest_all())
    finally:
        engine.close()
    return rows


def run_searches(engine_factory, questions: list[dict], financebench: list[dict], limit: int | None,
                 collection: str = COLLECTION, label: str = "") -> list[dict]:
    """Four search modes for each question; one JSONL row per question and mode."""
    if limit is not None:
        questions = questions[:limit]
        financebench = financebench[:limit]
    engine = engine_factory(collection)()
    rows: list[dict] = []
    try:
        for mode, overrides in SEARCH_MODES.items():
            rows.extend(_search_set(engine, questions, financebench, mode, overrides, collection))
    finally:
        engine.close()
    write_jsonl(f"search{label}.jsonl", rows)
    return rows


def _search_set(engine, questions, financebench, mode, overrides, collection):
    batch = []
    for question in questions:
        batch.append(_one_search(engine, question["query"], mode, overrides, collection,
                                 expected=question.get("expected_source", "")))
    for question in financebench:
        gold_pages = [page for evidence in question["evidence"] for page in evidence["pages"]]
        batch.append(_one_search(engine, question["question"], mode, overrides, collection,
                                 expected=question["doc_name"], gold_pages=gold_pages,
                                 qid=question["financebench_id"]))
    return batch


def _one_search(engine, query, mode, overrides, collection, expected, gold_pages=None, qid=""):
    started = time.perf_counter()
    error = ""
    try:
        results = engine.search(query, top_k=10, collection_name=collection, **overrides)
    except Exception as exc:  # noqa: BLE001 - record and continue (D4)
        results, error = [], f"{type(exc).__name__}: {exc}"
    slim = [
        {
            "id": result_id(item),
            "source": item.get("source", item.get("file", "")),
            "page_labels": item.get("page_labels")
            or ([item["page_label"]] if item.get("page_label") else []),
            "score": item.get("score"),
        }
        for item in results
    ]
    row = {"qid": qid or query[:40], "question": query, "mode": mode, "expected": expected,
           "collection": collection, "gold_pages": gold_pages or [],
           "seconds": round(time.perf_counter() - started, 2), "error": error, "results": slim}
    if expected and not error:
        hit = score_row(row, expected)
        row["hit_at_1"], row["reciprocal_rank"] = hit["hit_at_1"], hit["reciprocal_rank"]
        if gold_pages:
            pages = {str(p) for item in slim for p in item["page_labels"]}
            row["hit_at_page"] = bool(pages & {str(p) for p in gold_pages})
    return row


def run_answers(engine_factory, questions: list[dict], financebench: list[dict], limit: int | None,
                verify: bool) -> list[dict]:
    """Answer each question once with the claim-check setting held fixed."""
    os.environ["ANSWER__VERIFY_CLAIMS"] = "true" if verify else "false"
    if limit is not None:
        questions = questions[:limit]
        financebench = financebench[:limit]
    engine = engine_factory()()

    async def answer_all() -> list[dict]:
        stage = []
        for question in [{"qid": q.get("financebench_id", q.get("query", ""))[:40],
                          "text": q.get("question", q.get("query", ""))}
                         for q in questions + financebench]:
            started = time.perf_counter()
            error, answer = "", {}
            try:
                answer = await engine.answer(question["text"], top_k=10,
                                             collection_name=COLLECTION)
            except Exception as exc:  # noqa: BLE001 - record and continue (D4)
                error = f"{type(exc).__name__}: {exc}"
            fields = answer_fields(answer, verify)
            stage.append({"qid": question["qid"], "verify_claims": verify,
                          "seconds": round(time.perf_counter() - started, 2),
                          **fields, "error": error or fields["error"],
                          "answer": str(answer.get("answer", ""))[:500],
                          "citations": len(answer.get("citations", []) or [])})
            print(f"[answer verify={verify}] {question['qid']}: {stage[-1]['seconds']}s"
                  + (f" ERROR {error}" if error else ""), flush=True)
        return stage

    try:
        return asyncio.run(answer_all())
    finally:
        engine.close()


def engine_factory(collection: str = COLLECTION):
    """Build a fresh Engine against the scratch store (env-driven)."""
    from omrs.compose import build_engine

    def build():
        os.environ["COLLECTION_NAME"] = collection
        return build_engine()

    return build


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["part_a", "determinism", "arms"], default="part_a")
    parser.add_argument("--model", choices=sorted(ARM_MODELS),
                        help="arms mode: which comparison model")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap documents and questions (dry run)")
    parser.add_argument("--resume", action="store_true", help="skip stages with a done-marker")
    parser.add_argument("--dry-run", action="store_true",
                        help="write and load the scratch omrs.jsonc, then exit")
    args = parser.parse_args()

    OUTPUT.mkdir(exist_ok=True)
    plan = json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))
    if args.mode == "arms" and not args.model:
        raise SystemExit("arms mode needs --model 0.6b or 8b")
    embed_file = ARM_MODELS[args.model] if args.mode == "arms" else BASELINE_MODEL
    config_path = router_config.configure(plan, embed_file=embed_file)
    if args.dry_run:
        router_config.dry_run(config_path)
    chat_file = router_config.chat_model(plan)["file"]
    questions, financebench = load_questions(), load_financebench()

    if args.mode == "arms":
        collection = f"sweep43_{args.model.replace('.', '')}"
        preflight(plan, load=[embed_file, chat_file], models=[embed_file, chat_file])
        if not (args.resume and stage_done(f"arms-{args.model}-ingest")):
            rows = ingest_documents(engine_factory(collection), args.limit, collection)
            write_jsonl(f"arms-{args.model}-ingest.jsonl", rows)
            mark_done(f"arms-{args.model}-ingest", {"files": len(rows)})
        engine = engine_factory(collection)()
        out = []
        try:
            for question in questions[: args.limit or None]:
                out.append(_one_search(engine, question["query"], "dense", SEARCH_MODES["dense"],
                                       collection, expected=question.get("expected_source", "")))
        finally:
            engine.close()
        write_jsonl(f"arms-{args.model}.jsonl", out)
        print(f"[arms {args.model}] {len(out)} rows -> output/arms-{args.model}.jsonl", flush=True)
        return

    if args.mode == "determinism":
        preflight(plan, load=[BASELINE_MODEL], models=[BASELINE_MODEL])
        if args.limit is not None:
            questions = questions[: args.limit]
            financebench = financebench[: args.limit]
        baseline = read_jsonl("search.jsonl")
        engine = engine_factory()()
        repeat: dict[str, dict[str, list]] = {}
        repeat_rows: list[dict] = []
        try:
            for mode, overrides in SEARCH_MODES.items():
                for question in questions + financebench:
                    text = question.get("query") or question.get("question", "")
                    row = _one_search(engine, text, mode, overrides, COLLECTION,
                                      expected=question.get("expected_source", "")
                                      or question.get("doc_name", ""))
                    repeat_rows.append(row)
                    ids = [r["id"] for r in row["results"]]
                    repeat.setdefault(text, {})[mode] = ids
        finally:
            engine.close()
        first: dict[str, dict[str, list]] = {}
        for row in baseline:
            if row["question"] in repeat:
                ids = [r["id"] for r in row["results"]]
                first.setdefault(row["question"], {})[row["mode"]] = ids
        mismatches = []
        for mode in SEARCH_MODES:
            left = {q: first.get(q, {}).get(mode, []) for q in repeat}
            right = {q: repeat[q].get(mode, []) for q in repeat}
            mismatches += compare_rankings(mode, left, right)
        write_jsonl("determinism-repeat.jsonl", repeat_rows)
        write_jsonl("determinism.jsonl", mismatches)
        print(f"[determinism] {len(mismatches)} mismatches -> output/determinism.jsonl", flush=True)
        return

    preflight(plan, load=[BASELINE_MODEL, chat_file])
    if not (args.resume and stage_done("ingest")):
        rows = ingest_documents(engine_factory(), args.limit)
        write_jsonl("ingest.jsonl", rows)
        mark_done("ingest", {"files": len(rows)})
    if not (args.resume and stage_done("search")):
        rows = run_searches(engine_factory, questions, financebench, args.limit)
        mark_done("search", {"rows": len(rows)})
    if not (args.resume and stage_done("answers-plain")):
        rows = run_answers(engine_factory, questions, financebench, args.limit, verify=False)
        write_jsonl("answers.jsonl", rows)
        mark_done("answers-plain", {"rows": len(rows)})
    if not (args.resume and stage_done("answers-verify")):
        rows = run_answers(engine_factory, questions, financebench, args.limit, verify=True)
        write_jsonl("answers-verify.jsonl", rows)
        mark_done("answers-verify", {"rows": len(rows)})
    print("[part_a] complete", flush=True)


def questions_query_set(questions):
    return {q["query"] for q in questions}


if __name__ == "__main__":
    main()
