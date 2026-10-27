"""The optional ``purpose`` field (reproducible-experiment-runtime, tasks 1.1 and 1.3, design D2).

A record without ``purpose`` stays valid and counts as ``optimisation``. The
folder creator always writes the purpose into a new record.
"""

from __future__ import annotations

import json
from datetime import date
from importlib import resources
from pathlib import Path

import pytest
from typer.testing import CliRunner

from omrs.core.experiment_records import Purpose
from omrs.core.experiment_records.record import (
    Category,
    RecordError,
    Size,
    dump_record,
    load_record,
    parse_record,
    schema_text,
)
from omrs.core.experiment_records.scaffold import create_experiment
from omrs.transports.cli import app as cli_app

_DAY = date(2026, 10, 27)
_OLD_FOLDER = "38-rescue-quality-signal-2026-09-30"


def _data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "format": "omrs-experiment/1",
        "number": "38",
        "title": "Rescue quality signal",
        "date": "2026-09-30",
        "category": "ingestion",
        "size": "Standard",
        "status": "PASS",
        "superseded_by": None,
        "finding": "Found.",
    }
    data.update(overrides)
    return data


# --- Task 1.1: the record field --------------------------------------------


def test_publication_record_loads() -> None:
    record = parse_record(_data(purpose="publication"))
    assert record.purpose is Purpose.PUBLICATION
    assert record.effective_purpose is Purpose.PUBLICATION


def test_optimisation_record_loads() -> None:
    record = parse_record(_data(purpose="optimisation"))
    assert record.effective_purpose is Purpose.OPTIMISATION


def test_record_without_purpose_reads_as_optimisation() -> None:
    record = parse_record(_data())
    assert record.purpose is None
    assert record.effective_purpose is Purpose.OPTIMISATION


def test_unknown_purpose_names_the_field_and_both_values() -> None:
    with pytest.raises(RecordError) as caught:
        parse_record(_data(purpose="paper"))
    message = str(caught.value)
    assert "purpose" in message
    assert "optimisation" in message
    assert "publication" in message


def test_dumping_an_old_record_adds_no_purpose_key() -> None:
    original = json.dumps(_data(), indent=2, ensure_ascii=False) + "\n"
    assert dump_record(parse_record(json.loads(original))) == original


def test_dumping_a_record_with_purpose_keeps_it() -> None:
    dumped = json.loads(dump_record(parse_record(_data(purpose="publication"))))
    assert dumped["purpose"] == "publication"


def test_shipped_schema_matches_generated_schema_with_purpose() -> None:
    shipped = (
        resources.files("omrs.core.experiment_records") / "schema/experiment.v1.schema.json"
    ).read_text(encoding="utf-8")
    assert shipped == schema_text()
    schema = json.loads(shipped)
    assert "purpose" in schema["properties"]
    assert "purpose" not in schema.get("required", [])
    assert schema["$defs"]["Purpose"]["enum"] == ["optimisation", "publication"]


# --- Task 1.3: the folder creator and the CLI --------------------------------


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "experiments"
    path.mkdir()
    old = path / _OLD_FOLDER
    old.mkdir()
    (old / "experiment.json").write_text(
        json.dumps(_data(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def _new(root: Path, **kwargs: object) -> Path:
    options: dict[str, object] = {
        "slug": "rescue-rerun",
        "title": "Rescue rerun",
        "category": Category.INGESTION,
        "size": Size.CONFIRMATORY,
        "day": _DAY,
    }
    options.update(kwargs)
    return create_experiment(root, **options)  # type: ignore[arg-type]


def _raw(folder: Path) -> dict[str, object]:
    return json.loads((folder / "experiment.json").read_text(encoding="utf-8"))


def test_new_record_without_purpose_writes_optimisation(root: Path) -> None:
    folder = _new(root)
    assert _raw(folder)["purpose"] == "optimisation"
    assert load_record(folder / "experiment.json").purpose is Purpose.OPTIMISATION


def test_new_record_with_publication_writes_publication(root: Path) -> None:
    folder = _new(root, purpose=Purpose.PUBLICATION)
    assert _raw(folder)["purpose"] == "publication"


def test_publication_follow_up_leaves_the_old_record_unchanged(root: Path) -> None:
    old_file = root / _OLD_FOLDER / "experiment.json"
    before = old_file.read_bytes()
    folder = _new(root, purpose=Purpose.PUBLICATION, follow_up="38")
    assert folder.name == "38a-rescue-rerun-2026-10-27"
    assert _raw(folder)["purpose"] == "publication"
    assert old_file.read_bytes() == before


def _cli_new(root: Path, *extra: str) -> object:
    return CliRunner().invoke(
        cli_app,
        [
            "experiments",
            "new",
            "rescue-rerun",
            str(root),
            "--title",
            "Rescue rerun",
            "--category",
            "ingestion",
            "--size",
            "Confirmatory",
            "--date",
            "2026-10-27",
            *extra,
        ],
    )


def test_cli_new_defaults_to_optimisation(root: Path) -> None:
    result = _cli_new(root)
    assert result.exit_code == 0, result.stderr  # type: ignore[attr-defined]
    assert _raw(root / "39-rescue-rerun-2026-10-27")["purpose"] == "optimisation"


def test_cli_new_publication_follow_up(root: Path) -> None:
    result = _cli_new(root, "--purpose", "publication", "--follow-up", "38")
    assert result.exit_code == 0, result.stderr  # type: ignore[attr-defined]
    assert _raw(root / "38a-rescue-rerun-2026-10-27")["purpose"] == "publication"


def test_cli_new_unknown_purpose_exits_two(root: Path) -> None:
    result = _cli_new(root, "--purpose", "paper")
    assert result.exit_code == 2  # type: ignore[attr-defined]
    message = result.stderr  # type: ignore[attr-defined]
    assert "optimisation" in message
    assert "publication" in message
    assert not (root / "39-rescue-rerun-2026-10-27").exists()


@pytest.mark.parametrize("purpose", ["optimisation", "publication", "paper", None])
def test_shipped_schema_and_model_agree_on_purpose(purpose: str | None) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    shipped = (
        resources.files("omrs.core.experiment_records") / "schema/experiment.v1.schema.json"
    ).read_text(encoding="utf-8")
    data = _data(purpose=purpose)
    validator = jsonschema.Draft202012Validator(json.loads(shipped))
    try:
        parse_record(data)
        model_ok = True
    except RecordError:
        model_ok = False
    assert validator.is_valid(data) == model_ok
