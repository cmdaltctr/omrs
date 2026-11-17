"""Experiment 35 output layout (``outputs35.Layout``): tasks 5.1, 5.2, 13.2 and 13.3.

Rules under test: each index has its own store and folder; search and answer
setups sit in separate folders; ``--local-dir`` moves the scratch settings and
router state out of the output folder; ``--index-from`` reads the store, the
index markers and the fingerprint from another folder.
"""

from __future__ import annotations

from pathlib import Path

from tests._exp35_fixtures import load

outputs35 = load("outputs35")


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
