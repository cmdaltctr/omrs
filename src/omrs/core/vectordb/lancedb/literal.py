"""Engine literal serialisation and fail-closed verification.

The LanceDB filter adapter (``filter.py``) serialises every VALUE
through the engine's own literal builder — ``lit(value).to_sql()`` —
whose unparser performs the engine's quoting.  The engine's unparser is
treated as untrusted: every fragment is checked against a closed form
per value type, and string fragments are re-decoded with the standard
SQL literal grammar and compared to the original value.

This is not theoretical: on lancedb 0.37.1 and 0.40.0, ``lit("''").to_sql()``
is ``''''`` — the engine parses it as ONE apostrophe, so an unverified
filter on a double-apostrophe value silently matches the WRONG row —
and a backslash directly before an apostrophe emits ``\'`` undoubled,
which is unfaithful under every decode convention.  Values the engine
cannot serialise faithfully are refused with an actionable
``ValueError`` rather than emitted.

Three value classes are refused before ``lit`` runs (ADR-098), because
their comparison changed between lancedb 0.37.1 and 0.40.0 or differs
between the dense and sparse filter paths: a ``Decimal``, a float NaN
and a ``datetime`` without a time zone.

This module is the sole sanctioned exception to the parameterised-query
invariant (ADR-058), scoped to the LanceDB filter adapter.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal

from lancedb.expr import lit

__all__ = ["_check_value_class", "_is_faithful_literal", "_literal_sql"]


def _is_naive_datetime(value: object) -> bool:
    """Return True when *value* is a ``datetime`` with no UTC offset."""
    return isinstance(value, datetime) and value.utcoffset() is None


def _check_value_class(value: object) -> None:
    """Refuse a filter value whose comparison is ambiguous (ADR-098).

    lancedb 0.40.0 reads a naive datetime as UTC where 0.37.1 read it as
    local time, casts a float column to a decimal type for a ``Decimal``,
    and says ``NaN = NaN`` where the in-memory sparse filter says it is
    false.  Each case changes the matched rows without an error, so the
    value is refused with the accepted alternative named.

    Args:
        value: One comparison operand, or one membership-list item.

    Raises:
        ValueError: When *value* is a ``Decimal``, a float NaN or a
            ``datetime`` without a time zone.
    """
    if isinstance(value, Decimal):
        raise ValueError(
            "metadata_filter value is a Decimal. LanceDB compares a Decimal "
            "with a decimal cast of the stored field, which changes the "
            "matched rows. Pass an int or a float instead."
        )
    if isinstance(value, float) and value != value:
        raise ValueError(
            "metadata_filter value is a float NaN. The dense and sparse "
            "filters compare NaN differently. Remove the NaN clause."
        )
    if _is_naive_datetime(value):
        raise ValueError(
            "metadata_filter value is a naive datetime (it has no time zone), "
            "so the matched rows would depend on the lancedb version and the "
            "host clock. Pass a datetime with a time zone, for example "
            "datetime(2026, 9, 2, 14, 30, tzinfo=UTC)."
        )


def _decode_single_quoted_literal(fragment: str) -> str | None:
    """Decode *fragment* as exactly one standard-grammar SQL literal.

    A literal opens with ``'``, closes with a ``'`` that is not doubled,
    and an interior ``''`` decodes to one ``'``.  Returns ``None`` when
    the fragment is not exactly one well-formed literal — including a
    literal that closes early or ends on a doubled pair.

    Args:
        fragment: The candidate SQL fragment.

    Returns:
        The decoded literal value, or ``None`` when the fragment is not
        exactly one well-formed quoted literal.
    """
    if len(fragment) < 2 or fragment[0] != "'" or fragment[-1] != "'":
        return None
    chars: list[str] = []
    i = 1
    last = len(fragment) - 1
    while i < last:
        if fragment[i] == "'":
            if fragment[i + 1] == "'":
                chars.append("'")
                i += 2
                continue
            return None  # closes early or is a stray quote
        chars.append(fragment[i])
        i += 1
    return "".join(chars) if i == last else None


# Closed serialisation forms per value type.  Anything the engine's
# unparser emits outside these forms is refused (fail closed).
_BOOL_FORMS = frozenset({"true", "false"})
_INT_FORM = re.compile(r"-?\d+")
_NUMERIC_FORM = re.compile(r"-?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")
# lancedb 0.40.0 writes an infinity as the engine's typed cast.  Only
# this exact text is accepted for each infinity (ADR-098).
_INF_FORMS = {
    float("inf"): "arrow_cast('inf', 'Float64')",
    float("-inf"): "arrow_cast('-inf', 'Float64')",
}
_BYTES_FORM = re.compile(r"X'([0-9a-fA-F]*)'")
# The CAST target type is CAPTURED (not discarded): a date value in a
# TIMESTAMP cast — or a datetime in a DATE cast — is a different SQL
# value class even when the inner string round-trips, so the target
# type must be validated against the value type, not assumed.
_CAST_FORM = re.compile(r"CAST\('([^']*)' AS (DATE|TIMESTAMP)\)")


def _is_faithful_literal(value: object, sql: str) -> bool:
    """Check the engine's serialisation against a closed form per type.

    The engine's unparser is treated as untrusted: each fragment must
    not only match a valid SQL shape but also *represent* the original
    value.  For every supported scalar type the fragment is parsed or
    decoded and compared with the original using exact or canonical
    type semantics, so a regression that emits a different valid-looking
    value is refused.

    Args:
        value: The original comparison value handed to ``lit``.
        sql: The fragment the engine's unparser produced.

    Returns:
        True only when *sql* is a well-formed, faithful serialisation
        of *value* for its type.  ``bool`` is checked before ``int``
        because ``bool`` subclasses ``int``.
    """
    if isinstance(value, bool):
        # bool: exact match against the two SQL boolean literals.
        return sql == ("true" if value else "false")
    if isinstance(value, int):
        # int: the fragment must parse to the same integer.
        match = _INT_FORM.fullmatch(sql)
        return match is not None and int(sql) == value
    if isinstance(value, float):
        # float: NaN is a refused class; an infinity must be the exact
        # Float64 cast of the same infinity; ordinary floats compared by
        # numeric equality so that equivalent representations (1e10 vs
        # 10000000000.0) pass.
        if value != value:  # NaN
            return False
        if value in _INF_FORMS:
            return sql == _INF_FORMS[value]
        match = _NUMERIC_FORM.fullmatch(sql)
        return match is not None and float(sql) == value
    if isinstance(value, Decimal):
        # Decimal: a refused class (ADR-098), whatever the fragment.
        return False
    if isinstance(value, str):
        decoded = _decode_single_quoted_literal(sql)
        return decoded is not None and decoded == value
    if isinstance(value, bytes):
        match = _BYTES_FORM.fullmatch(sql)
        return match is not None and bytes.fromhex(match.group(1)) == value
    if isinstance(value, (date, datetime)):
        # date/datetime: the engine emits CAST('...' AS DATE|TIMESTAMP).
        # The target type must agree with the value type (a swapped cast
        # is a different SQL value class even when the inner string
        # round-trips), the fragment must match the CAST form at all,
        # and the inner string must parse to the same calendar date or
        # instant.  A naive datetime is a refused class (ADR-098).
        if _is_naive_datetime(value):
            return False
        match = _CAST_FORM.fullmatch(sql)
        if match is None:
            return False
        inner, target = match.group(1), match.group(2)
        if isinstance(value, datetime):
            return target == "TIMESTAMP" and _datetime_matches(value, inner)
        return target == "DATE" and _date_matches(value, inner)
    return False


def _date_matches(value: date, inner: str) -> bool:
    """Check whether a CAST(... AS DATE) inner string matches *value*.

    Args:
        value: The original ``date`` value.
        inner: The date string inside the CAST, e.g. ``2026-09-02``.

    Returns:
        True when *inner* parses to the same calendar date.
    """
    try:
        parsed = date.fromisoformat(inner)
    except ValueError:
        return False
    return parsed == value


def _datetime_matches(value: datetime, inner: str) -> bool:
    """Check whether a CAST(... AS TIMESTAMP) inner string matches *value*.

    The engine serialises an aware datetime as its UTC wall clock.  A
    naive datetime never reaches this check (ADR-098).

    Args:
        value: The original aware ``datetime`` value.
        inner: The timestamp string inside the CAST, e.g.
            ``2026-09-02 14:30:45``.

    Returns:
        True when *inner* represents the same UTC instant as *value*.
    """
    try:
        parsed = datetime.fromisoformat(inner)
    except ValueError:
        return False
    return parsed == value.astimezone(UTC).replace(tzinfo=None)


def _literal_sql(value: object) -> str:
    """Serialise one value through the type-safe literal builder.

    The engine's unparser output is verified against a closed form per
    value type (and, for strings, decoded back and compared to the
    original value) before it is allowed into a filter.  The engine has
    demonstrated mis-serialisation classes — apostrophe runs collapse,
    and a backslash before an apostrophe emits ``\'`` undoubled — so an
    unverified fragment is a wrong-row or broken-SQL hazard, and this
    boundary refuses it.

    Args:
        value: A scalar supported by ``lit`` (bool/int/float/str/bytes/
            date/aware datetime).

    Returns:
        The verified, engine-quoted SQL literal.

    Raises:
        TypeError: When ``lit`` rejects the value's type — the trust
            boundary that keeps structured values from reaching SQL.
        ValueError: When the value is a refused class
            (:func:`_check_value_class`), or when the engine's
            serialisation fails the closed-form or round-trip check.
            The filter is refused rather than emitted with an
            unfaithful literal.
    """
    _check_value_class(value)
    sql = lit(value).to_sql()
    if not _is_faithful_literal(value, sql):
        raise ValueError(
            "metadata_filter value cannot be serialised safely: the engine's "
            f"literal builder returned an unfaithful fragment for a "
            f"{type(value).__name__} value (sample {str(value)[:60]!r}). "
            "Refusing to build the filter; values containing runs of "
            "apostrophes, or a backslash directly before an apostrophe, are "
            "known to be affected."
        )
    return sql
