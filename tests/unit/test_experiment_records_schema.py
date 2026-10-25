"""The shipped JSON Schema matches the record model (experiment-format-v1, task 2.3).

The schema file is generated from ``ExperimentRecord.model_json_schema()``
with sorted keys. Regenerate it with::

    uv run --no-sync python -c "from omrs.core.experiment_records.record import schema_text; \
print(schema_text(), end='')" > src/omrs/core/experiment_records/schema/experiment.v1.schema.json
"""

from __future__ import annotations

import json
from importlib import resources

import pytest

from omrs.core.experiment_records.record import (
    ExperimentRecord,
    RecordError,
    parse_record,
    schema_text,
)

_SCHEMA = "schema/experiment.v1.schema.json"


def _shipped() -> str:
    return (resources.files("omrs.core.experiment_records") / _SCHEMA).read_text(encoding="utf-8")


def test_shipped_schema_matches_generated_schema() -> None:
    assert _shipped() == schema_text(), (
        f"{_SCHEMA} is out of date; regenerate it (see this test's docstring)"
    )


def test_schema_text_is_the_model_schema_with_sorted_keys() -> None:
    assert json.loads(schema_text()) == ExperimentRecord.model_json_schema()
    assert schema_text() == json.dumps(json.loads(schema_text()), indent=2, sort_keys=True) + "\n"


def test_schema_carries_the_cross_field_rules() -> None:
    schema = json.loads(_shipped())
    assert schema["additionalProperties"] is False
    assert schema["properties"]["format"]["const"] == "omrs-experiment/1"
    rules = json.dumps(schema["allOf"])
    assert "SUPERSEDED" in rules
    assert "migration" in rules


def _base(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "format": "omrs-experiment/1",
        "number": "1",
        "title": "x",
        "date": "2026-01-01",
        "category": "retrieval",
        "size": "Quick",
        "status": "PASS",
        "superseded_by": None,
        "finding": "f",
    }
    data.update(overrides)
    return data


_MIGRATION = {"from_status": "P", "source": "s", "date": "2026-01-01"}

_PARITY_CASES = {
    "valid": _base(),
    "superseded without pointer": _base(status="SUPERSEDED"),
    "superseded with empty pointer": _base(status="SUPERSEDED", superseded_by=""),
    "superseded with pointer": _base(status="SUPERSEDED", superseded_by="2-a-2026-01-01"),
    "pass with pointer": _base(superseded_by="a"),
    "category null without migration": _base(category=None),
    "category null with null migration": _base(category=None, migration=None),
    "converted without size": {**_base(size=None), "migration": _MIGRATION},
    "bad date": _base(date="2026-02-30"),
    "unknown key": _base(owner="x"),
    "multi-line finding": _base(finding="a\nb"),
    "bad number": _base(number="5B"),
    "newer format": _base(format="omrs-experiment/2"),
}


@pytest.mark.parametrize("case", sorted(_PARITY_CASES))
def test_shipped_schema_and_model_agree(case: str) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    data = _PARITY_CASES[case]
    validator = jsonschema.Draft202012Validator(
        json.loads(_shipped()), format_checker=jsonschema.FormatChecker()
    )
    try:
        parse_record(data)
        model_ok = True
    except RecordError:
        model_ok = False
    assert validator.is_valid(data) == model_ok
