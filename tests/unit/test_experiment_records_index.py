"""The generated index block in ``EXP_README.md`` (experiment-format-v1, task 4.2, D6).

The block between the markers holds the experiment table and, when numbers
are reserved, a reserved-numbers table. Everything outside the markers is
kept byte for byte.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from omrs.core.experiment_records.index import (
    INDEX_END,
    INDEX_START,
    IndexFileError,
    IndexMarkerError,
    index_is_current,
    read_block,
    render_index,
    replace_block,
    write_index,
)
from omrs.core.experiment_records.record import ExperimentRecord, parse_record
from omrs.core.experiment_records.reserved import Reservation
from omrs.core.experiment_records.scan import ExperimentFolder, scan_experiments

_HEADER = "| # | Experiment | Date | Status | Key Finding / Purpose |\n|---|---|---|---|---|\n"


def _record(number: str, title: str, finding: str = "Found.", **extra: Any) -> ExperimentRecord:
    data: dict[str, Any] = {
        "format": "omrs-experiment/1",
        "number": number,
        "title": title,
        "date": "2026-05-12",
        "category": "retrieval",
        "size": "Quick",
        "status": "PASS",
        "superseded_by": None,
        "finding": finding,
    }
    data.update(extra)
    return parse_record(data)


def _folder(name: str, record: ExperimentRecord | None) -> ExperimentFolder:
    return ExperimentFolder(
        name=name,
        path=Path("/unused") / name,
        parsed=None,
        record=record,
        record_error=None if record else "experiment.json is missing",
        has_record_file=record is not None,
        output_names=(),
    )


def test_single_row_layout() -> None:
    block = render_index([_folder("1-a-2026-05-12", _record("1", "Reranker calibration"))], [])
    assert block == (
        _HEADER + "| 1 | [Reranker calibration](./1-a-2026-05-12/) | 2026-05-12 | PASS | Found. |\n"
    )


def test_rows_order_by_number_then_folder_with_unnumbered_last() -> None:
    folders = [
        _folder("zeta-2026-01-01", _record("", "Zeta")),
        _folder("10-x-2026-01-01", _record("10", "Ten")),
        _folder("alpha-2026-01-01", _record("", "Alpha")),
        _folder("9a-y-2026-01-01", _record("9a", "Nine a y")),
        _folder("9a-b-2026-01-01", _record("9a", "Nine a b")),
        _folder("10.1-x-2026-01-01", _record("10.1", "Ten point one")),
        _folder("5b-x-2026-01-01", _record("5b", "Five b")),
    ]
    rows = render_index(folders, []).splitlines()[2:]
    titles = [row.split("](")[0].split("[", 1)[1] for row in rows]
    assert titles == ["Five b", "Nine a b", "Nine a y", "Ten", "Ten point one", "Alpha", "Zeta"]
    assert rows[-1].startswith("|  | [Zeta]")


def test_output_is_deterministic() -> None:
    folders = [_folder(f"{n}-x-2026-01-01", _record(str(n), f"T{n}")) for n in (3, 1, 2)]
    assert render_index(folders, []) == render_index(list(reversed(folders)), [])


def test_folders_without_a_record_are_left_out() -> None:
    folders = [_folder("1-a-2026-05-12", _record("1", "One")), _folder("2-b-2026-05-12", None)]
    assert render_index(folders, []).count("\n") == 3


def test_pipe_in_a_cell_is_escaped() -> None:
    record = _record("1", "A | B", finding="Hit@1 | MRR both up")
    row = render_index([_folder("1-a-2026-05-12", record)], []).splitlines()[2]
    assert "[A \\| B]" in row
    assert "Hit@1 \\| MRR both up" in row
    unescaped = row.replace("\\|", "")
    assert unescaped.count("|") == 6


def test_brackets_in_a_title_do_not_break_the_link() -> None:
    row = render_index([_folder("1-a-2026-05-12", _record("1", "Exp [draft]"))], []).splitlines()[2]
    assert "[Exp \\[draft\\]](./1-a-2026-05-12/)" in row


def test_superseded_row_shows_status() -> None:
    record = _record("5", "Pool sizing", status="SUPERSEDED", superseded_by="10-x-2026-01-01")
    row = render_index([_folder("5-a-2026-05-12", record)], []).splitlines()[2]
    assert "| SUPERSEDED |" in row


def test_reserved_numbers_follow_the_experiment_table() -> None:
    reservations = [
        Reservation(
            number="41", reason="MLX OCR backends", ref="feat/experiment-41-mlx-ocr-backends"
        ),
        Reservation(number="35", reason="Full-document | RAG", ref="openspec/changes/x"),
    ]
    block = render_index([_folder("1-a-2026-05-12", _record("1", "One"))], reservations)
    _, reserved = block.split("\n\n### Reserved numbers\n\n")
    assert reserved == (
        "| # | Reason | Reference |\n"
        "|---|---|---|\n"
        "| 35 | Full-document \\| RAG | openspec/changes/x |\n"
        "| 41 | MLX OCR backends | feat/experiment-41-mlx-ocr-backends |\n"
    )


def test_no_reserved_heading_without_reservations() -> None:
    block = render_index([_folder("1-a-2026-05-12", _record("1", "One"))], [])
    assert "Reserved" not in block


def _readme(block: str = "old table\n") -> str:
    return (
        f"# Experiments\n\nIntro text.\n\n{INDEX_START}\n{block}{INDEX_END}\n\n## After\n\nTail.\n"
    )


def test_replace_keeps_text_outside_the_markers() -> None:
    text = _readme()
    new = replace_block(text, "| new |\n")
    before, _, rest = text.partition(INDEX_START)
    _, _, after = rest.partition(INDEX_END)
    assert new.startswith(before + INDEX_START + "\n| new |\n" + INDEX_END)
    assert new.endswith(after)
    assert read_block(new) == "| new |\n"


@pytest.mark.parametrize(
    ("text", "missing"),
    [
        ("# Experiments\n", INDEX_START),
        (f"# Experiments\n{INDEX_START}\nrows\n", INDEX_END),
        (f"# Experiments\nrows\n{INDEX_END}\n", INDEX_START),
    ],
)
def test_missing_marker_is_named(text: str, missing: str) -> None:
    with pytest.raises(IndexMarkerError, match=missing):
        read_block(text)


def test_markers_in_wrong_order_are_refused() -> None:
    with pytest.raises(IndexMarkerError, match="before"):
        read_block(f"{INDEX_END}\nrows\n{INDEX_START}\n")


def test_repeated_marker_is_refused() -> None:
    with pytest.raises(IndexMarkerError, match="more than once"):
        read_block(f"{INDEX_START}\n{INDEX_START}\nrows\n{INDEX_END}\n")


def test_marker_must_be_a_whole_line() -> None:
    with pytest.raises(IndexMarkerError):
        read_block(f"text {INDEX_START}\nrows\n{INDEX_END}\n")


def _write_experiment(root: Path, name: str, number: str, title: str) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    data = _record(number, title).model_dump(mode="json", exclude={"refs", "migration"})
    data["date"] = name[-10:]
    (folder / "experiment.json").write_text(json.dumps(data), encoding="utf-8")


def test_write_index_replaces_only_the_block(tmp_path: Path) -> None:
    _write_experiment(tmp_path, "1-a-2026-05-12", "1", "One")
    readme = tmp_path / "EXP_README.md"
    original = _readme().replace("\n", "\r\n", 2)  # a CRLF prefix must survive too
    readme.write_bytes(original.encode("utf-8"))
    folders = scan_experiments(tmp_path)
    assert write_index(readme, folders, []) is True
    written = readme.read_bytes().decode("utf-8")
    prefix = original.partition(INDEX_START)[0]
    suffix = original.partition(INDEX_END)[2]
    assert written.startswith(prefix + INDEX_START + "\n")
    assert written.endswith(INDEX_END + suffix)
    assert read_block(written) == render_index(folders, [])
    assert index_is_current(written, folders, [])
    assert write_index(readme, folders, []) is False


def test_write_refused_without_markers_leaves_file_unchanged(tmp_path: Path) -> None:
    readme = tmp_path / "EXP_README.md"
    readme.write_bytes(b"# Experiments\n\nNo markers here.\n")
    before = readme.stat().st_mtime_ns
    with pytest.raises(IndexMarkerError, match=INDEX_START):
        write_index(readme, [], [])
    assert readme.read_bytes() == b"# Experiments\n\nNo markers here.\n"
    assert readme.stat().st_mtime_ns == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["EXP_README.md"]


def test_stale_table_is_detected() -> None:
    folders = [_folder("1-a-2026-05-12", _record("1", "One"))]
    current = _readme(render_index(folders, []))
    assert index_is_current(current, folders, [])
    assert not index_is_current(_readme(), folders, [])
    reservation = [Reservation(number="35", reason="r", ref="x")]
    assert not index_is_current(current, folders, reservation)


def test_date_cell_uses_the_record_date() -> None:
    record = _record("1", "One", date="2026-09-07")
    assert record.date == date(2026, 9, 7)
    assert "| 2026-09-07 |" in render_index([_folder("1-a-2026-09-07", record)], [])


def _cells(row: str) -> list[str]:
    """Split a table row the way GFM does: a backslash escapes the next character."""
    cells, current, chars = [], "", iter(row.strip()[1:-1])
    for char in chars:
        if char == "\\":
            current += char + next(chars, "")
        elif char == "|":
            cells.append(current)
            current = ""
        else:
            current += char
    return [*cells, current]


def test_backslash_before_pipe_stays_in_one_cell() -> None:
    record = _record("1", "One", finding="a\\|b and c\\d")
    row = render_index([_folder("1-a-2026-05-12", record)], []).splitlines()[2]
    cells = _cells(row)
    assert len(cells) == 5
    assert cells[4].strip() == "a\\\\\\|b and c\\d"


@pytest.mark.parametrize("name", ["my exp", "exp (old)", "exp)"])
def test_link_target_with_space_or_parenthesis_uses_angle_brackets(name: str) -> None:
    row = render_index([_folder(name, _record("1", "One"))], []).splitlines()[2]
    assert f"[One](<./{name}/>)" in row


def test_plain_link_target_has_no_angle_brackets() -> None:
    row = render_index([_folder("1-a-2026-05-12", _record("1", "One"))], []).splitlines()[2]
    assert "[One](./1-a-2026-05-12/)" in row


def test_write_index_refuses_non_utf8_readme(tmp_path: Path) -> None:
    readme = tmp_path / "EXP_README.md"
    readme.write_bytes(f"{INDEX_START}\n\xff\n{INDEX_END}\n".encode("latin-1"))
    before = readme.read_bytes()
    with pytest.raises(IndexFileError, match="UTF-8"):
        write_index(readme, [], [])
    assert readme.read_bytes() == before
