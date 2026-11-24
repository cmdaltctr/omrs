"""Experiment 35 index stages with a stub engine and a temporary LanceDB store.

Rules under test: the ingest failure rule (task 5.4b), the ``seal`` stage and
its fingerprint (tasks 5.4, 5.4a), and the machine and environment record
(task 5.6). No router, no model and no network.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import lancedb
import pyarrow as pa
import pytest
from experiments._lib.trace import TraceWriter
from tests._exp35_fixtures import load

from omrs.core.vectordb.lancedb.fts import ensure_fts_index

arms = load("arms")
outputs35 = load("outputs35")
stages35 = load("stages35")

INDEX = "e4b-c1024"
ENV = {
    "gpu": "NVIDIA GeForce RTX 4090",
    "image": "runpod/base@sha256:" + "1" * 64,
    "llama_cpp_build": 11941,
    "gguf_sha256": {"Qwen3-Embedding-4B-Q8_0.gguf": "a" * 64},
}


def _settings(backend: str = "bm25") -> Any:
    return SimpleNamespace(retrieval=SimpleNamespace(hybrid_sparse_backend=backend))


class _Engine:
    """Stub engine: ``ingest`` returns the planned result of each file name."""

    def __init__(self, results: Mapping[str, Any] | None = None) -> None:
        self.results = dict(results or {})
        self.calls: list[str] = []

    async def ingest(self, path: str, *, collection_name: str) -> dict[str, Any]:
        name = Path(path).name
        self.calls.append(name)
        result = self.results.get(name, "ok")
        if isinstance(result, Exception):
            raise result
        if result == "failed":
            return {
                "status": "error",
                "message": "All 1 file(s) failed to index.",
                "chunks_created": 0,
                "file_details": [{"file": name, "status": "failed", "chunks": 0, "error": "x"}],
                "warnings": [f"{name}: x"],
            }
        return {
            "status": "ok",
            "chunks_created": 3,
            "file_details": [{"file": name, "status": "indexed", "chunks": 3}],
            **({"warnings": [result]} if result != "ok" else {}),
        }


def _ctx(
    tmp_path: Path,
    stage: str,
    *,
    dataset: str = "bioasq",
    index: str = INDEX,
    engine: Any = None,
    files: Sequence[Path] = (),
    resume: bool = False,
    backend: str = "bm25",
    environment: Mapping[str, Any] | None = None,
) -> Any:
    layout = outputs35.Layout(tmp_path / "out")
    folder = layout.index_dir(dataset, index)
    trace = TraceWriter(
        folder / "traces.jsonl",
        benchmark_revision="test",
        run_id=f"{dataset}/{index}/run1",
        arm=index,
        repetition=1,
        effective_settings={"setup": index},
        model_identities={},
    )
    key = outputs35.run_key(None, None, 20261101, ["q1"], config={"harness_commit": "c"})
    return stages35.Ctx(
        dataset=dataset,
        setup=index,
        kind="index",
        run=1,
        questions=[],
        layout=layout,
        key=key,
        resume=resume,
        trace=trace,
        engine=engine,
        settings=_settings(backend),
        files=list(files),
        environment=dict(environment or ENV),
    )


def _files(tmp_path: Path, *names: str) -> list[Path]:
    folder = tmp_path / "passages"
    folder.mkdir(exist_ok=True)
    for name in names:
        (folder / name).write_text(name, encoding="utf-8")
    return [folder / name for name in names]


def _ingest(ctx: Any) -> Any:
    return asyncio.run(stages35.ingest_stage(ctx))


def _marker(ctx: Any) -> dict[str, Any]:
    return json.loads((ctx.folder / ".done-ingest.json").read_text(encoding="utf-8"))


# --- ingest failure rule (task 5.4b) ------------------------------------------------------


def test_a_clean_ingest_writes_the_marker_with_per_file_chunks_and_warnings(tmp_path: Path) -> None:
    files = _files(tmp_path, "a.md", "b.md")
    engine = _Engine({"b.md": "page 3 is empty"})
    ctx = _ctx(tmp_path, "ingest", engine=engine, files=files)
    assert _ingest(ctx) == 0
    marker = _marker(ctx)
    assert marker["files"] == {"a.md": 3, "b.md": 3}
    assert marker["warnings"] == {"b.md": ["page 3 is empty"]}
    assert marker["failed"] == []
    assert engine.calls == ["a.md", "b.md"]
    trace = [json.loads(line) for line in ctx.trace.path.read_text().splitlines()]
    assert [row["question_id"] for row in trace] == ["a.md", "b.md"]


def test_a_failed_file_writes_no_marker_and_resume_retries_only_that_file(tmp_path: Path) -> None:
    files = _files(tmp_path, "a.md", "b.md", "c.md")
    first = _Engine({"b.md": "failed", "c.md": RuntimeError("store unreachable")})
    with pytest.raises(stages35.StageIncomplete, match=r"b\.md, c\.md"):
        _ingest(_ctx(tmp_path, "ingest", engine=first, files=files))
    assert not (_ctx(tmp_path, "ingest").folder / ".done-ingest.json").exists()
    again = _Engine()
    ctx = _ctx(tmp_path, "ingest", engine=again, files=files, resume=True)
    assert _ingest(ctx) == 0
    assert again.calls == ["b.md", "c.md"]
    assert _marker(ctx)["files"] == {"a.md": 3, "b.md": 3, "c.md": 3}


def test_a_warning_alone_is_not_a_failure(tmp_path: Path) -> None:
    files = _files(tmp_path, "a.md")
    ctx = _ctx(tmp_path, "ingest", engine=_Engine({"a.md": "empty page"}), files=files)
    assert _ingest(ctx) == 0
    rows = [json.loads(line) for line in (ctx.folder / "ingest.jsonl").read_text().splitlines()]
    assert rows[0]["status"] == "ok"
    assert rows[0]["warnings"] == ["empty page"]


def test_a_finished_ingest_is_skipped_on_resume(tmp_path: Path) -> None:
    files = _files(tmp_path, "a.md")
    assert _ingest(_ctx(tmp_path, "ingest", engine=_Engine(), files=files)) == 0
    engine = _Engine()
    assert _ingest(_ctx(tmp_path, "ingest", engine=engine, files=files, resume=True)) == 0
    assert engine.calls == []


class _StuckEngine:
    """Stub engine whose ``ingest`` waits in a worker thread until *release* is set."""

    def __init__(self, release: Any) -> None:
        self.release = release

    async def ingest(self, path: str, *, collection_name: str) -> dict[str, Any]:
        await asyncio.to_thread(self.release.wait)
        return {"status": "ok", "chunks_created": 1, "file_details": []}


def test_a_stuck_file_stops_the_stage_with_its_name_and_the_stacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    # The 2026-11-24 t-fb hang: AMCOR_2020_10K.pdf gave no result and no error for 17 min.
    release, codes = threading.Event(), []

    def hard_exit(code: int) -> None:
        codes.append(code)
        release.set()  # the real exit never returns; let the stub finish instead

    monkeypatch.setattr(stages35, "FILE_WATCHDOG_SECONDS", 0.2)
    monkeypatch.setattr(stages35, "_hard_exit", hard_exit)
    files = _files(tmp_path, "AMCOR_2020_10K.pdf")
    _ingest(_ctx(tmp_path, "ingest", engine=_StuckEngine(release), files=files))
    out, err = capfd.readouterr()
    assert codes == [stages35.EXIT_STUCK] == [6]
    assert "AMCOR_2020_10K.pdf: no result after" in out
    assert "most recent call first" in err


def test_the_file_watchdog_does_not_fire_after_the_file_is_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codes: list[int] = []
    monkeypatch.setattr(stages35, "FILE_WATCHDOG_SECONDS", 0.2)
    monkeypatch.setattr(stages35, "_hard_exit", codes.append)
    files = _files(tmp_path, "a.md")
    assert _ingest(_ctx(tmp_path, "ingest", engine=_Engine(), files=files)) == 0
    time.sleep(0.4)
    assert codes == []


# --- seal (tasks 5.4, 5.4a, 5.4b) ---------------------------------------------------------


def _table(store: Path, name: str, labels: Sequence[str | None], epoch: str = "ep-1") -> None:
    schema = pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("doc_id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), 4)),
            pa.field("text", pa.string()),
            pa.field(
                "metadata",
                pa.struct(
                    [pa.field("file_name", pa.string()), pa.field("page_label", pa.string())]
                ),
            ),
        ],
        metadata={"omrs_dataset_epoch": json.dumps(epoch)},
    )
    rows = [
        {
            "id": f"{name}-{i}",
            "doc_id": "d",
            "vector": [0.1, 0.2, 0.3, 0.4],
            "text": f"chunk {i}",
            "metadata": {"file_name": "f.md", "page_label": label},
        }
        for i, label in enumerate(labels)
    ]
    lancedb.connect(str(store)).create_table(name, data=pa.Table.from_pylist(rows, schema=schema))


def _ingested(tmp_path: Path, dataset: str, index: str = INDEX, **marker: Any) -> Path:
    layout = outputs35.Layout(tmp_path / "out")
    folder = layout.index_dir(dataset, index)
    body = {"files": {"f.md": 3}, "warnings": {}, "failed": [], **marker}
    outputs35.write_json(folder / ".done-ingest.json", body)
    return layout.store(index)


def _seal(ctx: Any) -> int:
    return asyncio.run(stages35.seal_stage(ctx))


def _version(store: Path, name: str) -> int:
    return lancedb.connect(str(store)).open_table(name).version


def test_seal_writes_the_fingerprint_and_changes_no_table(tmp_path: Path) -> None:
    store = _ingested(tmp_path, "bioasq")
    _table(store, "exp35_bioasq_e4b_c1024", ["1", "1", None])
    _table(store, "exp35_freshstack_e4b_c1024", ["1"])
    before = _version(store, "exp35_bioasq_e4b_c1024")
    ctx = _ctx(tmp_path, "seal")
    assert _seal(ctx) == 0
    assert _version(store, "exp35_bioasq_e4b_c1024") == before
    found = json.loads(ctx.layout.fingerprint("bioasq", INDEX).read_text(encoding="utf-8"))
    assert found["collection"] == "exp35_bioasq_e4b_c1024"
    assert found["table_version"] == before
    assert found["dataset_epoch"] == "ep-1"
    assert found["chunks"] == 3
    assert found["embedding_dimension"] == 4
    assert found["sparse_backend"] == "bm25"
    assert found["fts"] is None
    assert (ctx.folder / ".done-seal.json").exists()


def test_seal_refuses_an_index_without_its_ingest_marker(tmp_path: Path) -> None:
    with pytest.raises(stages35.StageOrderError, match=r"e4b-c1024.*bioasq"):
        _seal(_ctx(tmp_path, "seal"))


def test_seal_refuses_native_without_a_full_text_index(tmp_path: Path) -> None:
    store = _ingested(tmp_path, "bioasq")
    _table(store, "exp35_bioasq_e4b_c1024", ["1"])
    with pytest.raises(stages35.SealRefused, match="full-text index"):
        _seal(_ctx(tmp_path, "seal", backend="native"))


def test_seal_refuses_native_with_unindexed_rows(tmp_path: Path) -> None:
    store = _ingested(tmp_path, "bioasq")
    _table(store, "exp35_bioasq_e4b_c1024", ["1"])
    table = lancedb.connect(str(store)).open_table("exp35_bioasq_e4b_c1024")
    ensure_fts_index(table)
    table.add(
        [
            {
                "id": "late",
                "doc_id": "d",
                "vector": [0.1] * 4,
                "text": "late",
                "metadata": {"file_name": "g.md", "page_label": "1"},
            }
        ]
    )
    with pytest.raises(stages35.SealRefused, match="1 unindexed"):
        _seal(_ctx(tmp_path, "seal", backend="native"))


def test_seal_refuses_a_financebench_index_with_unpaged_chunks(tmp_path: Path) -> None:
    store = _ingested(tmp_path, "financebench")
    _table(store, "exp35_financebench_e4b_c1024", ["1", None, ""])
    with pytest.raises(stages35.SealRefused, match="2 chunks with no page label"):
        _seal(_ctx(tmp_path, "seal", dataset="financebench"))


def test_seal_passes_a_financebench_index_where_every_chunk_has_a_page(tmp_path: Path) -> None:
    store = _ingested(tmp_path, "financebench")
    _table(store, "exp35_financebench_e4b_c1024", ["1", "2"])
    ctx = _ctx(tmp_path, "seal", dataset="financebench")
    assert _seal(ctx) == 0
    found = json.loads(ctx.layout.fingerprint("financebench", INDEX).read_text("utf-8"))
    assert found["unpaged_chunks"] == 0


def test_seal_refuses_chunk_counts_that_differ_across_embedders(tmp_path: Path) -> None:
    store = _ingested(tmp_path, "bioasq", files={"f.md": 3, "g.md": 2})
    _ingested(tmp_path, "bioasq", "e0.6b-c1024", files={"f.md": 3, "g.md": 4})
    _table(store, "exp35_bioasq_e4b_c1024", ["1"])
    with pytest.raises(stages35.SealRefused, match=r"g\.md.*e0\.6b-c1024"):
        _seal(_ctx(tmp_path, "seal"))


def test_seal_refuses_warning_lists_that_differ_across_embedders(tmp_path: Path) -> None:
    store = _ingested(tmp_path, "bioasq", warnings={"f.md": ["empty page"]})
    _ingested(tmp_path, "bioasq", "e8b-c1024", warnings={})
    _table(store, "exp35_bioasq_e4b_c1024", ["1"])
    with pytest.raises(stages35.SealRefused, match=r"f\.md"):
        _seal(_ctx(tmp_path, "seal"))


def test_seal_records_the_embedders_it_compared(tmp_path: Path) -> None:
    store = _ingested(tmp_path, "bioasq")
    _ingested(tmp_path, "bioasq", "e8b-c1024")
    _ingested(tmp_path, "bioasq", "e8b-c512", files={"other.md": 9})
    _table(store, "exp35_bioasq_e4b_c1024", ["1"])
    ctx = _ctx(tmp_path, "seal")
    assert _seal(ctx) == 0
    found = json.loads(ctx.layout.fingerprint("bioasq", INDEX).read_text("utf-8"))
    assert found["compared_with"] == ["e8b-c1024"]


# --- machine and environment record (task 5.6) --------------------------------------------


def _machine(**over: Any) -> dict[str, Any]:
    return {"host": "pod-a", "pod_id": "abc", "gpu": ENV["gpu"], "image": ENV["image"], **over}


def _image_plan(image: Any = ENV["image"]) -> dict[str, Any]:
    """A plan with only the pod image pin (``null`` is listed as pending, like plan.json)."""
    pending = [] if image else [{"key": "pins.environment.image", "task": "RDY 9.1"}]
    return {"pins": {"environment": {"image": image}, "pending": pending}}


def _found() -> Any:
    model = {"file": "Qwen3-Embedding-4B-Q8_0.gguf", "sha256": "a" * 64}
    return SimpleNamespace(build=11941, models=[model])


def test_the_environment_record_holds_gpu_image_build_and_gguf_hashes() -> None:
    assert stages35.environment_record(_machine(), _found()) == ENV


@pytest.mark.parametrize(
    ("field", "value", "named"),
    [("gpu", None, "gpu"), ("image", None, "image"), ("image", "runpod/base:1.6.0", "sha256")],
)
def test_check_machine_refuses_a_missing_field_or_an_undigested_image(
    field: str, value: Any, named: str
) -> None:
    with pytest.raises(stages35.EnvironmentMismatch, match=named):
        stages35.check_machine(_machine(**{field: value}), _image_plan())


@pytest.mark.parametrize(
    "plan",
    [_image_plan("runpod/base@sha256:" + "2" * 64), _image_plan(None), {"pins": {"pending": []}}],
)
def test_check_machine_refuses_an_image_that_is_not_the_plan_pin(plan: dict[str, Any]) -> None:
    with pytest.raises(stages35.EnvironmentMismatch, match=r"pins\.environment\.image"):
        stages35.check_machine(_machine(), plan)


def test_check_machine_accepts_the_pinned_image() -> None:
    stages35.check_machine(_machine(), _image_plan())


def test_seal_writes_the_build_environment_record(tmp_path: Path) -> None:
    store = _ingested(tmp_path, "bioasq")
    _table(store, "exp35_bioasq_e4b_c1024", ["1"])
    ctx = _ctx(tmp_path, "seal")
    assert _seal(ctx) == 0
    assert json.loads(ctx.layout.environment.read_text(encoding="utf-8")) == ENV


def test_a_stage_appends_its_machine_line_and_matches_the_build_record(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "ingest")
    outputs35.write_json(ctx.layout.environment, ENV)
    stages35.record_machine(ctx, _machine(), ENV)
    stages35.record_machine(ctx, _machine(host="pod-b", pod_id=None), ENV)
    lines = [json.loads(x) for x in (ctx.folder / "machine.jsonl").read_text().splitlines()]
    assert [(x["host"], x["pod_id"]) for x in lines] == [("pod-a", "abc"), ("pod-b", None)]
    assert lines[0]["environment"] == ENV


def test_a_stage_on_another_gpu_refuses_and_names_the_field(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "ingest")
    outputs35.write_json(ctx.layout.environment, ENV)
    other = {**ENV, "gpu": "NVIDIA A40"}
    with pytest.raises(stages35.EnvironmentMismatch, match="gpu"):
        stages35.record_machine(ctx, _machine(gpu="NVIDIA A40"), other)
    assert not (ctx.folder / "machine.jsonl").exists()


def test_a_search_kind_stage_refuses_without_the_build_record(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "ingest")
    ctx.kind = "search"
    with pytest.raises(stages35.EnvironmentMismatch, match="environment.json"):
        stages35.record_machine(ctx, _machine(), ENV)
