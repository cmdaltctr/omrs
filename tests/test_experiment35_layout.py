"""Experiment 35 output layout (``outputs35.Layout``): tasks 5.1, 5.2, 13.2 and 13.3.

Rules under test: each index has its own store and folder; two ingests of
different indexes into one output folder at the same time leave each store
written by one process only (design D32); search and answer setups sit in
separate folders; ``--local-dir`` moves the scratch settings and
router state out of the output folder; ``--index-from`` reads the store, the
index markers and the fingerprint from another folder.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import lancedb
import pytest
from tests._exp35_fixtures import ROOT, load

arms = load("arms")
outputs35 = load("outputs35")

#: One index pod in a child process: the real ingest stage, the real Layout and a
#: stub engine that writes each file through the OMRS LanceDB store at
#: ``layout.store(index)``, as ``run_arms`` points ``LANCEDB_URI`` there. Each row
#: ID carries the writer's process ID. A file barrier starts both ingests together.
_INDEX_POD = """
import asyncio, os, sys, time
from pathlib import Path
from experiments._lib.trace import TraceWriter
from omrs.core.vectordb.identity import EmbeddingIdentity
from omrs.core.vectordb.lancedb.store import LanceVectorStore
from tests._exp35_fixtures import load

outputs35, stages35 = load("outputs35"), load("stages35")
out, dataset, index, source, go = sys.argv[1:6]
layout = outputs35.Layout(Path(out))


class Engine:
    def __init__(self, uri):
        self.store = LanceVectorStore(uri=uri)

    async def ingest(self, path, *, collection_name):
        name = Path(path).name
        self.store.upsert_precomputed(
            collection_name, [f"{os.getpid()}:{name}"], [name], [{"file_name": name}],
            [[0.5] * 4], embedding_identity=EmbeddingIdentity(provider="test", model="mock"),
        )
        await asyncio.sleep(0.01)
        return {"status": "ok", "chunks_created": 1,
                "file_details": [{"file": name, "status": "indexed", "chunks": 1}]}


trace = TraceWriter(
    layout.index_dir(dataset, index) / "traces.jsonl", benchmark_revision="test",
    run_id=f"{dataset}/{index}/run1", arm=index, repetition=1,
    effective_settings={"setup": index}, model_identities={},
)
ctx = stages35.Ctx(
    dataset=dataset, setup=index, kind="index", run=1, questions=[], layout=layout,
    key=outputs35.run_key(None, None, 20261101, ["q1"], config={"harness_commit": "c"}),
    resume=False, trace=trace, engine=Engine(str(layout.store(index))),
    files=sorted(Path(source).glob("*.md")),
)
(Path(go) / index).touch()
deadline = time.monotonic() + 60
while len(list(Path(go).iterdir())) < 2 and time.monotonic() < deadline:
    time.sleep(0.005)
sys.exit(asyncio.run(stages35.ingest_stage(ctx)))
"""


def test_each_index_has_its_own_store_and_folder(tmp_path: Path) -> None:
    layout = outputs35.Layout(tmp_path / "out")
    assert layout.store("e4b-c1024") == tmp_path / "out" / "stores" / "e4b-c1024" / "lancedb"
    assert layout.store("e8b-c512") != layout.store("e4b-c1024")
    assert layout.index_dir("bioasq", "e4b-c1024") == tmp_path / "out" / "bioasq" / "e4b-c1024"
    assert layout.fingerprint("bioasq", "e4b-c1024") == (
        tmp_path / "out" / "bioasq" / "e4b-c1024" / "index-fingerprint.json"
    )


def test_search_and_answer_setups_of_one_cell_sit_in_separate_folders(tmp_path: Path) -> None:
    layout = outputs35.Layout(tmp_path / "out")
    search = layout.run_dir("bioasq", "search", "e4b-c512-r4b-hon", 1)
    answer = layout.run_dir("bioasq", "answer", "e4b-c512-r4b-hon", 1)
    t20k = layout.run_dir("bioasq", "answer", "e4b-c512-r4b-hon-t20k", 1)
    assert search == tmp_path / "out" / "bioasq" / "search" / "e4b-c512-r4b-hon" / "run1"
    assert len({search, answer, t20k}) == 3
    assert t20k.parent.name == "e4b-c512-r4b-hon-t20k"


def test_without_local_dir_config_and_state_stay_in_the_output_folder(tmp_path: Path) -> None:
    layout = outputs35.Layout(tmp_path / "out")
    assert layout.state_dir == tmp_path / "out" / "state"
    assert layout.config_dir("bioasq", "e4b-c512", "ingest") == (
        tmp_path / "out" / "config" / "bioasq-e4b-c512-ingest"
    )


def test_local_dir_moves_config_and_state_out_of_the_output_folder(tmp_path: Path) -> None:
    layout = outputs35.Layout(tmp_path / "out", local=tmp_path / "local")
    assert layout.state_dir == tmp_path / "local" / "state"
    assert layout.config_dir("bioasq", "e4b-c512", "ingest").is_relative_to(tmp_path / "local")
    assert layout.store("e4b-c512").is_relative_to(tmp_path / "out")


def test_index_from_reads_the_index_and_writes_runs_to_the_output_folder(tmp_path: Path) -> None:
    layout = outputs35.Layout(tmp_path / "out", index_root=tmp_path / "shared")
    assert layout.store("e4b-c1024").is_relative_to(tmp_path / "shared")
    assert layout.index_dir("bioasq", "e4b-c1024").is_relative_to(tmp_path / "shared")
    assert layout.fingerprint("bioasq", "e4b-c1024").is_relative_to(tmp_path / "shared")
    assert layout.environment == tmp_path / "shared" / "environment.json"
    assert layout.run_dir("bioasq", "search", "e4b-c1024-roff-hoff", 1).is_relative_to(
        tmp_path / "out"
    )


@pytest.mark.slow
def test_two_concurrent_ingests_of_different_indexes_write_separate_stores(
    tmp_path: Path,
) -> None:
    out, go, source = tmp_path / "out", tmp_path / "go", tmp_path / "passages"
    go.mkdir()
    source.mkdir()
    names = [f"p{i}.md" for i in range(6)]
    for name in names:
        (source / name).write_text(name, encoding="utf-8")
    indexes = ("e4b-c1024", "e8b-c512")
    path = os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")])
    env = {**os.environ, "PYTHONPATH": path}
    pods = [
        subprocess.Popen(
            [sys.executable, "-c", _INDEX_POD, str(out), "bioasq", index, str(source), str(go)],
            cwd=ROOT,
            env=env,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in indexes
    ]
    for pod in pods:
        _, err = pod.communicate(timeout=120)
        assert pod.returncode == 0, err

    layout = outputs35.Layout(out)
    writers = {}
    for index in indexes:
        collection = arms.index_setup(index).collection("bioasq")
        db = lancedb.connect(str(layout.store(index)))
        assert [t for t in db.list_tables().tables if t.startswith("exp35_")] == [collection]
        ids = db.open_table(collection).to_arrow()["id"].to_pylist()
        assert sorted(i.split(":", 1)[1] for i in ids) == names
        writers[index] = {i.split(":", 1)[0] for i in ids}
        assert len(writers[index]) == 1, f"{index}: store written by {writers[index]}"
        assert (layout.index_dir("bioasq", index) / ".done-ingest.json").exists()
    assert writers[indexes[0]] != writers[indexes[1]]
    assert writers[indexes[0]] | writers[indexes[1]] == {str(p.pid) for p in pods}
