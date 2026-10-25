"""Experiment record model (experiment-format-v1, task 2.1, design D1 to D4).

The record is the one machine-readable file in an experiment folder. These
tests pin its fields, the seven status values, the cross-field rules and
the refusal of unknown keys and unknown format versions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from omrs.core.experiment_records.record import (
    FORMAT,
    ExperimentRecord,
    RecordError,
    Status,
    UnsupportedFormatError,
    dump_record,
    load_record,
    parse_record,
)


def _data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format": "omrs-experiment/1",
        "number": "22",
        "title": "Raw-query Qwen3-Embedding-4B baseline",
        "date": "2026-09-07",
        "category": "retrieval",
        "size": "Standard",
        "status": "MEASURED",
        "superseded_by": None,
        "finding": "One line, no newline.",
        "refs": {"adrs": ["ADR-018"], "changes": [], "tasks": []},
    }
    data.update(overrides)
    return data


_MIGRATION = {
    "from_status": "COMPLETE (measurement)",
    "source": "EXP_README.md",
    "date": "2026-10-25",
}


def test_valid_record_loads() -> None:
    record = parse_record(_data())
    assert record.format == FORMAT == "omrs-experiment/1"
    assert record.number == "22"
    assert record.status is Status.MEASURED
    assert record.date.isoformat() == "2026-09-07"
    assert record.refs is not None
    assert record.refs.adrs == ("ADR-018",)


def test_record_is_frozen() -> None:
    record = parse_record(_data())
    with pytest.raises(ValueError):
        record.title = "changed"  # type: ignore[misc]


def test_unknown_key_is_refused_and_named() -> None:
    with pytest.raises(RecordError, match="owner"):
        parse_record(_data(owner="someone"))


def test_unknown_nested_key_is_refused() -> None:
    with pytest.raises(RecordError, match="links"):
        parse_record(_data(refs={"adrs": [], "links": []}))


def test_unknown_format_version_names_it() -> None:
    with pytest.raises(UnsupportedFormatError) as caught:
        parse_record(_data(format="omrs-experiment/2"))
    message = str(caught.value)
    assert "omrs-experiment/2" in message
    assert "newer" in message
    assert caught.value.version == "omrs-experiment/2"


def test_missing_format_is_refused() -> None:
    data = _data()
    del data["format"]
    with pytest.raises(RecordError, match="format"):
        parse_record(data)


def test_unsupported_format_is_a_record_error() -> None:
    assert issubclass(UnsupportedFormatError, RecordError)


@pytest.mark.parametrize(
    "status",
    ["PLANNED", "ACTIVE", "PASS", "FAIL", "INCONCLUSIVE", "MEASURED"],
)
def test_each_live_status_loads(status: str) -> None:
    assert parse_record(_data(status=status)).status.value == status


def test_superseded_with_pointer_loads() -> None:
    record = parse_record(
        _data(status="SUPERSEDED", superseded_by="10b-reranker-pool-size-corrected-2026-06-29")
    )
    assert record.status is Status.SUPERSEDED


def test_exactly_seven_status_values() -> None:
    assert [s.value for s in Status] == [
        "PLANNED",
        "ACTIVE",
        "PASS",
        "FAIL",
        "INCONCLUSIVE",
        "MEASURED",
        "SUPERSEDED",
    ]


def test_unknown_status_is_refused() -> None:
    with pytest.raises(RecordError, match="status"):
        parse_record(_data(status="COMPLETE"))


def test_superseded_without_pointer_asks_for_folder() -> None:
    with pytest.raises(RecordError, match="superseded_by"):
        parse_record(_data(status="SUPERSEDED", superseded_by=None))


def test_pass_with_pointer_is_refused() -> None:
    with pytest.raises(RecordError, match="superseded_by"):
        parse_record(_data(status="PASS", superseded_by="2-embedding-model-comparison-2026-05-19"))


@pytest.mark.parametrize("field", ["category", "size"])
def test_empty_category_or_size_refused_without_migration(field: str) -> None:
    with pytest.raises(RecordError, match=field):
        parse_record(_data(**{field: None}))


@pytest.mark.parametrize("field", ["category", "size"])
def test_missing_category_or_size_refused_without_migration(field: str) -> None:
    data = _data()
    del data[field]
    with pytest.raises(RecordError, match=field):
        parse_record(data)


@pytest.mark.parametrize("field", ["category", "size"])
def test_empty_category_or_size_allowed_with_migration(field: str) -> None:
    record = parse_record(_data(migration=_MIGRATION, **{field: None}))
    assert getattr(record, field) is None
    assert record.migration is not None
    assert record.migration.from_status == "COMPLETE (measurement)"


def test_migration_note_needs_all_three_fields() -> None:
    with pytest.raises(RecordError, match="source"):
        parse_record(_data(migration={"from_status": "PASS", "date": "2026-10-25"}))


def test_unknown_category_is_refused() -> None:
    with pytest.raises(RecordError, match="category"):
        parse_record(_data(category="chunking"))


@pytest.mark.parametrize("field", ["finding", "title"])
@pytest.mark.parametrize("text", ["first\nsecond", "first\rsecond"])
def test_line_break_is_refused(field: str, text: str) -> None:
    with pytest.raises(RecordError, match=field):
        parse_record(_data(**{field: text}))


def test_empty_title_is_refused() -> None:
    with pytest.raises(RecordError, match="title"):
        parse_record(_data(title=""))


@pytest.mark.parametrize("number", ["22", "5b", "10.1", "", "1", "100"])
def test_number_patterns_accepted(number: str) -> None:
    assert parse_record(_data(number=number)).number == number


@pytest.mark.parametrize("number", ["5B", "5bb", "10.", ".1", "a", "10.1b", "-1", " 5", "5 "])
def test_bad_number_refused(number: str) -> None:
    with pytest.raises(RecordError, match="number"):
        parse_record(_data(number=number))


def test_number_must_be_a_string() -> None:
    with pytest.raises(RecordError, match="number"):
        parse_record(_data(number=22))


def test_bad_date_refused() -> None:
    with pytest.raises(RecordError, match="date"):
        parse_record(_data(date="2026-02-30"))


def test_superseded_by_must_be_a_folder_name() -> None:
    with pytest.raises(RecordError, match="superseded_by"):
        parse_record(_data(status="SUPERSEDED", superseded_by="../outside"))


def test_parse_refuses_non_object() -> None:
    with pytest.raises(RecordError, match="object"):
        parse_record(["not", "a", "record"])


def test_load_record_reads_file(tmp_path: Path) -> None:
    path = tmp_path / "experiment.json"
    path.write_text(json.dumps(_data()), encoding="utf-8")
    assert load_record(path).title == "Raw-query Qwen3-Embedding-4B baseline"


def test_load_record_names_bad_json(tmp_path: Path) -> None:
    path = tmp_path / "experiment.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RecordError, match="JSON"):
        load_record(path)


def test_dump_round_trips_and_ends_with_newline() -> None:
    record = parse_record(_data(migration=_MIGRATION))
    text = dump_record(record)
    assert text.endswith("}\n")
    assert parse_record(json.loads(text)) == record
    keys = list(json.loads(text))
    assert keys[:3] == ["format", "number", "title"]


def test_dump_omits_absent_refs_and_migration() -> None:
    data = _data()
    del data["refs"]
    loaded = json.loads(dump_record(parse_record(data)))
    assert "refs" not in loaded
    assert "migration" not in loaded
    assert loaded["superseded_by"] is None


def test_model_validate_also_refuses_unknown_format() -> None:
    with pytest.raises(ValueError):
        ExperimentRecord.model_validate(_data(format="omrs-experiment/2"))


@pytest.mark.parametrize("version", ["omrs-experiment/0", "junk", "omrs-experiment/x"])
def test_unrecognised_format_is_not_called_newer(version: str) -> None:
    with pytest.raises(UnsupportedFormatError) as caught:
        parse_record(_data(format=version))
    message = str(caught.value)
    assert version in message
    assert "not recognised" in message
    assert "newer" not in message


def test_higher_format_version_asks_for_newer_omrs() -> None:
    with pytest.raises(UnsupportedFormatError, match="needs a newer omrs"):
        parse_record(_data(format="omrs-experiment/12"))
