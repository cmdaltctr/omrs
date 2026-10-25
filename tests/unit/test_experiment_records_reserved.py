"""Reserved experiment numbers (experiment-format-v1, task 3.3, design D7)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from omrs.core.experiment_records.record import RecordError, UnsupportedFormatError
from omrs.core.experiment_records.reserved import (
    RESERVATIONS_FORMAT,
    RESERVED_FILE,
    Reservation,
    load_reservations,
)


def _write(root: Path, data: Any) -> None:
    (root / RESERVED_FILE).write_text(json.dumps(data), encoding="utf-8")


def _file(*entries: dict[str, str]) -> dict[str, Any]:
    return {"format": "omrs-experiment-reservations/1", "reservations": list(entries)}


_E35 = {
    "number": "35",
    "reason": "Full-document RAG benchmark",
    "ref": "openspec/changes/experiment-35-full-document-rag-benchmark",
}
_E40 = {"number": "40", "reason": "Planned in NiftyPM", "ref": "AIE-101"}


def test_valid_file_loads(tmp_path: Path) -> None:
    _write(tmp_path, _file(_E35, _E40))
    loaded = load_reservations(tmp_path)
    assert loaded == (Reservation(**_E35), Reservation(**_E40))
    assert RESERVATIONS_FORMAT == "omrs-experiment-reservations/1"
    assert RESERVED_FILE == "reserved.json"


def test_missing_file_means_no_reservations(tmp_path: Path) -> None:
    assert load_reservations(tmp_path) == ()


def test_unknown_top_level_key_is_refused(tmp_path: Path) -> None:
    data = _file(_E35)
    data["owner"] = "someone"
    _write(tmp_path, data)
    with pytest.raises(RecordError, match="owner"):
        load_reservations(tmp_path)


def test_unknown_entry_key_is_refused(tmp_path: Path) -> None:
    _write(tmp_path, _file({**_E35, "until": "2027-01-01"}))
    with pytest.raises(RecordError, match="until"):
        load_reservations(tmp_path)


@pytest.mark.parametrize("number", ["", "35B", "x", "35-a"])
def test_bad_number_is_refused(tmp_path: Path, number: str) -> None:
    _write(tmp_path, _file({**_E35, "number": number}))
    with pytest.raises(RecordError, match="number"):
        load_reservations(tmp_path)


def test_duplicate_number_is_refused(tmp_path: Path) -> None:
    _write(tmp_path, _file(_E35, {**_E40, "number": "35"}))
    with pytest.raises(RecordError, match="35"):
        load_reservations(tmp_path)


@pytest.mark.parametrize("field", ["reason", "ref"])
def test_reason_and_ref_are_required(tmp_path: Path, field: str) -> None:
    entry = dict(_E35)
    del entry[field]
    _write(tmp_path, _file(entry))
    with pytest.raises(RecordError, match=field):
        load_reservations(tmp_path)


def test_unknown_format_version_is_refused(tmp_path: Path) -> None:
    _write(tmp_path, {"format": "omrs-experiment-reservations/2", "reservations": []})
    with pytest.raises(UnsupportedFormatError, match="reservations/2"):
        load_reservations(tmp_path)


def test_bad_json_is_refused(tmp_path: Path) -> None:
    (tmp_path / RESERVED_FILE).write_text("[", encoding="utf-8")
    with pytest.raises(RecordError, match="JSON"):
        load_reservations(tmp_path)
