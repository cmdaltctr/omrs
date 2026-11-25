"""Experiment 35 FreshStack export of repeated corpus IDs (owner decision, 2026-11-23).

The real corpus has 49,514 rows, 49,505 distinct IDs and 49,506 distinct pairs of ID
and text: one ID has two texts, and some rows repeat exactly. The owner decided on
2026-11-23 that ``prepare35.py`` writes one passage file per distinct pair. An exact
repeat is written once. The second text of an ID gets its own file, and its manifest
row keeps the corpus ID, so both files map to one unit. The fixture corpus
(``tests/_exp35_fixtures.py``) has the same shape: 8 rows, 7 distinct pairs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tests._exp35_fixtures import FS_FILES, FS_ROWS, FS_ROWS_DATA, fake_plan, load, make_data_root

datasets35 = load("datasets35")
prepare35 = load("prepare35")

#: The fixture ID with two texts and one exact repeat of its first text.
_SPLIT = "repo/src/util.py_60_90"
_FIRST = "def f():\n    return 1\n"
_SECOND = "def f():\n    return 2\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_data_root(tmp_path / "DATA")


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _manifest(folder: Path) -> list[dict]:
    lines = (folder / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_freshstack_writes_one_file_per_distinct_pair_of_id_and_text(
    root: Path, tmp_path: Path
) -> None:
    assert [text for corpus_id, text in FS_ROWS_DATA if corpus_id == _SPLIT] == [
        _FIRST,
        _SECOND,
        _FIRST,
    ]
    assert (len(FS_ROWS_DATA), len(set(FS_ROWS_DATA))) == (FS_ROWS, FS_FILES)
    folder = prepare35.prepare("freshstack", root, tmp_path / "passages", plan=fake_plan())
    manifest = _manifest(folder)
    assert len(list(folder.glob("*.md"))) == len(manifest) == FS_FILES
    assert len({row["file"] for row in manifest}) == FS_FILES
    assert sum(row["rows"] for row in manifest) == FS_ROWS
    tree = json.loads((folder / "passages-tree.json").read_text(encoding="utf-8"))
    assert set(tree["files"]) == {row["file"] for row in manifest} | {"manifest.jsonl"}


def test_the_second_text_of_an_id_is_named_by_the_id_hash_and_the_text_hash(
    root: Path, tmp_path: Path
) -> None:
    folder = prepare35.prepare("freshstack", root, tmp_path / "passages", plan=fake_plan())
    plain, suffixed = f"{_sha16(_SPLIT)}.md", f"{_sha16(_SPLIT)}-{_sha16(_SECOND)}.md"
    rows = {row["file"]: row for row in _manifest(folder) if row["freshstack_id"] == _SPLIT}
    assert set(rows) == {plain, suffixed}
    assert (folder / plain).read_text(encoding="utf-8") == prepare35.export_row(_SPLIT, _FIRST)[0]
    second = prepare35.export_row(_SPLIT, _SECOND)[0]
    assert (folder / suffixed).read_text(encoding="utf-8") == second
    # The exact repeat of the first text is written once; its manifest row counts both rows.
    assert (rows[plain]["rows"], rows[suffixed]["rows"]) == (2, 1)
    assert rows[plain]["url"] == rows[suffixed]["url"]


def test_both_files_of_a_repeated_id_map_to_its_one_unit(root: Path, tmp_path: Path) -> None:
    passages = tmp_path / "passages"
    folder = prepare35.prepare("freshstack", root, passages, plan=fake_plan())
    units = datasets35.freshstack_unit_map(folder)
    stems = sorted(stem for stem, unit in units.items() if unit == _SPLIT)
    assert len(stems) == 2
    gold = datasets35.Question(qid="q1", text="question", relevant=(_SPLIT,))
    files = datasets35.corpus_files("freshstack", root, [gold], 0, passages, seed=1)
    assert sorted(f.stem for f in files) == stems


def test_an_unexpected_second_text_beyond_the_pinned_file_count_is_refused(
    root: Path, tmp_path: Path
) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    corpus = root / "benchmarks" / "freshstack" / "corpus-oct-2024" / "langchain"
    path = corpus / "train-00000-of-00001.parquet"
    rows = pq.read_table(path).to_pylist()
    rows.append({**rows[0], "text": "# Title\n\nA third text.\n"})
    pq.write_table(pa.Table.from_pylist(rows), path)
    plan = fake_plan()
    pin = plan["pins"]["datasets"]["freshstack"]
    pin["rows"] = FS_ROWS + 1
    pin["corpus_files"] = {path.name: datasets35.file_sha256(path)}
    pin["corpus_tree_sha256"] = datasets35.tree_hash(pin["corpus_files"])
    with pytest.raises(datasets35.DatasetError, match=f"{FS_FILES + 1}.*files {FS_FILES}"):
        prepare35.prepare("freshstack", root, tmp_path / "passages", plan=plan)
    assert not list((tmp_path / "passages" / "freshstack").iterdir())
