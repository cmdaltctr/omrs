"""Filter value classes that changed meaning in lancedb 0.40 (ADR-098).

lancedb 0.40.0 serialises four value classes differently from 0.37.1
(``probes.md`` P1 and P2 of the ``upgrade-lancedb-0-40`` change):

* An infinite float becomes ``arrow_cast('inf', 'Float64')``. On 0.37.1
  the bare ``inf`` was read as a column name and the filter failed. On
  0.40.0 it matches the correct rows, so the translator accepts it.
* A naive datetime is read as UTC wall clock, not as local time, so the
  same filter matches different rows on a host that is not on UTC.
* A Decimal makes the engine cast the float column to a decimal type,
  which drops or adds rows without an error.
* A NaN compares equal to itself in the engine but not in the in-memory
  sparse filter, so dense and sparse results would disagree.

The translator refuses the last three classes with a ``ValueError`` that
names the class and the alternative. The refusal runs before a
schema-absent field folds to a constant, so it does not depend on the
table's schema.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import lancedb
import pyarrow as pa
import pytest

from omrs.core.vectordb.lancedb.filter import translate_where

_KNOWN_FIELDS = frozenset({"id", "tag", "score"})


def _shapes(value: object) -> list[tuple[dict, frozenset[str] | None]]:
    """Return the filter shapes that must each refuse *value*.

    The shapes are a scalar operand, a ``$in`` item, and the same two on
    a field that the schema does not hold (``nope``).
    """
    return [
        ({"tag": value}, None),
        ({"tag": {"$in": ["x", value]}}, None),
        ({"nope": value}, _KNOWN_FIELDS),
        ({"nope": {"$nin": ["x", value]}}, _KNOWN_FIELDS),
    ]


_SHAPE_IDS = ["scalar", "in-item", "absent-scalar", "absent-nin-item"]


@pytest.mark.parametrize("shape", range(4), ids=_SHAPE_IDS)
def test_naive_datetime_is_refused(shape: int) -> None:
    """A datetime without a time zone is refused in every filter shape."""
    where, known = _shapes(datetime(2026, 9, 2, 15, 30, 45))[shape]
    with pytest.raises(ValueError, match="naive datetime") as caught:
        translate_where(where, known_fields=known)
    assert "time zone" in str(caught.value)


@pytest.mark.parametrize("shape", range(4), ids=_SHAPE_IDS)
def test_decimal_is_refused(shape: int) -> None:
    """A Decimal is refused in every filter shape."""
    where, known = _shapes(Decimal("3.14"))[shape]
    with pytest.raises(ValueError, match="Decimal") as caught:
        translate_where(where, known_fields=known)
    assert "int or a float" in str(caught.value)


@pytest.mark.parametrize("shape", range(4), ids=_SHAPE_IDS)
def test_nan_is_refused(shape: int) -> None:
    """A float NaN is refused in every filter shape."""
    where, known = _shapes(float("nan"))[shape]
    with pytest.raises(ValueError, match="NaN"):
        translate_where(where, known_fields=known)


# ── Engine round trip (probes.md P2) ──────────────────────────────────

_P2_ROWS = [
    ("a", 0.05, "2026-09-01"),
    ("b", 3.14, "2026-09-02"),
    ("c", float("inf"), "2026-09-03"),
    ("d", float("-inf"), "2026-09-04"),
    ("e", float("nan"), "2026-09-05"),
]


@pytest.fixture
def p2_table(tmp_path: Path):
    """Return the probes.md P2 table: user metadata inside a struct column."""
    schema = pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), 2)),
            pa.field(
                "metadata",
                pa.struct([("score", pa.float64()), ("creation_date", pa.string())]),
            ),
        ]
    )
    rows = [
        {"id": rid, "vector": [0.0, 0.1], "metadata": {"score": s, "creation_date": d}}
        for rid, s, d in _P2_ROWS
    ]
    db = lancedb.connect(str(tmp_path / "lancedb"))
    return db.create_table("p2", pa.Table.from_pylist(rows, schema=schema))


def _matched_ids(table, where: dict) -> list[str]:
    """Return the sorted IDs of the rows that the translated filter selects."""
    sql = translate_where(where, metadata_column="metadata")
    assert sql is not None
    result = table.search().where(sql).select(["id"]).limit(100).to_arrow()
    return sorted(result["id"].to_pylist())


@pytest.mark.parametrize(
    ("where", "expected"),
    [
        ({"score": {"$eq": float("inf")}}, ["c"]),
        ({"score": {"$eq": float("-inf")}}, ["d"]),
        ({"score": {"$lt": float("inf")}}, ["a", "b", "d"]),
    ],
    ids=["eq-inf", "eq-minus-inf", "lt-inf"],
)
def test_infinite_float_filters_match_expected_rows(
    p2_table, where: dict, expected: list[str]
) -> None:
    """Infinite float filters return the rows that the comparison selects."""
    assert _matched_ids(p2_table, where) == expected


@pytest.fixture(params=["Europe/London", "America/Los_Angeles"])
def host_tz(request, monkeypatch: pytest.MonkeyPatch):
    """Run the test with the process time zone set to each parameter."""
    monkeypatch.setenv("TZ", request.param)
    time.tzset()
    yield request.param
    monkeypatch.undo()
    time.tzset()


def test_aware_datetime_on_iso_text_keeps_its_rows(p2_table, host_tz: str) -> None:
    """An aware datetime compares its UTC instant, whatever the host time zone."""
    plus_eight = timezone(timedelta(hours=8))
    for value in (datetime(2026, 9, 3, tzinfo=UTC), datetime(2026, 9, 3, 8, tzinfo=plus_eight)):
        where = {"creation_date": {"$gte": value}}
        assert _matched_ids(p2_table, where) == ["c", "d", "e"], (host_tz, value)
