# Proposal

## Why

lancedb before 0.40.0 does not stop its Tokio runtime at interpreter exit. A short-lived process that writes to LanceDB can crash with SIGSEGV or SIGABRT after the write has finished (TDR-040). lancedb PR #4175 (merged 2026-09-15) fixes this, and 0.40.0 is the first release that contains it. The floor CI jobs hit the crash in five runs on 2026-10-25. The tests now hide it with an `os._exit(0)` step in `tests/_lance_child.py`, but a real CLI process such as `omrs ingest` can still exit with the wrong status.

Users who install without the lock file already get lancedb 0.40.0. `uv tool install` ignores `uv.lock`, and the live app was found on lancedb 0.40.0, pylance 13.0.0 and pyarrow 26.0.0. That app ran a version pair that the project did not test. The project must test the version that its users get.

The upgrade changes how `lancedb.expr.lit` writes four classes of filter value. The fail-closed check in `core/vectordb/lancedb/literal.py` refuses two of the new forms, and two of the forms change which rows a filter matches without an error. This change makes each of these cases explicit.

## What Changes

- Raise the `lancedb` floor from `>=0.37` to `>=0.40` and lock 0.40.0. Keep `pylance>=10` (lock 10.0.0), `pyarrow>=25.0.1` (lock 25.0.1) and `llama-index-vector-stores-lancedb>=0.5.0` (lock 0.5.0). **BREAKING** (install contract: a floor raise).
- Accept the new lancedb 0.40 form for infinite floats: `arrow_cast('inf', 'Float64')` and `arrow_cast('-inf', 'Float64')`, exact text only. On lancedb 0.37.1 these filters failed with a planner error, because the engine read the bare `inf` as a column name. On 0.40.0 they return the correct rows.
- **BREAKING** (library API): refuse a `datetime` filter value without a time zone (a naive datetime). lancedb 0.37.1 read it as local time and converted it to UTC. lancedb 0.40.0 reads it as UTC (lancedb PR #3775). The same filter therefore matches different rows on the two versions. The error tells the caller to pass an aware datetime. Aware datetimes and dates do not change.
- **BREAKING** (library API): refuse a `Decimal` filter value. lancedb 0.40.0 casts the stored float column to a decimal type for the comparison. This drops rows (a row with `1e-20` fails `> Decimal("0")`), adds rows (a row with `0.1 + 0.2` matches `= Decimal("0.3")`), and makes the query fail when a float column holds a large or infinite value. The error tells the caller to pass an `int` or a `float`.
- **BREAKING** (library API): refuse a float NaN filter value. On lancedb 0.37.1 a NaN filter failed with a planner error. On 0.40.0 the engine says `NaN = NaN` is true, but the in-memory BM25 filter says it is false, so dense and sparse results would disagree.
- Remove the `os._exit(0)` step from `tests/_lance_child.py`. Writer child processes run through normal interpreter shutdown again, so a crash at exit fails the test. Keep the finished marker and the `PYTHONFAULTHANDLER=1` diagnostics.
- Re-pin `test_locked_lancedb_versions` to lancedb 0.40.0 and pylance 10.0.0. Update the present-tense version notes that name lancedb 0.37.1.
- Record the decision in ADR-098 (Proposed).

The MCP `metadata_filter` parameter is JSON, and JSON has no datetime, Decimal or NaN values. MCP and HTTP callers see no change. Only Python callers of `Engine.search`, `Engine.answer` and the delete paths can pass these values.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `lancedb-vector-store`: the filter translation requirement changes its accepted value classes (special floats, Decimal, NaN, naive datetime). The filter-policy exception requirement records that lancedb 0.40.0 still has no bind parameters and no struct field access. A new requirement states that writer processes exit cleanly and that the lancedb floor includes the runtime shutdown.

## Impact

- **Dependencies:** `pyproject.toml` (`lancedb>=0.40` and its comment) and `uv.lock` (the `lancedb` package entry and its `requires-dist` specifier only).
- **Code:** `src/omrs/core/vectordb/lancedb/literal.py` (new float forms, three refusals, removal of the naive-datetime local-time branch). Version notes in `filter.py`, `fts.py`, `meta.py` and `store.py` docstrings.
- **Tests:** `tests/test_lance_filter_security.py` (new failing tests first, then changed mismatch and faithful-value cases), `tests/test_lancedb_native_fts_contract.py` (version pin and docstring), `tests/_lance_child.py` and `tests/test_lance_child_helper.py` (no exit bypass), `tests/test_clean_base_tripwire.py` (re-pin).
- **Docs:** ADR-098 and its row in `docs/adr/ADR_README.md`, a dated resolution note in TDR-040, the library usage guide (filter value types), `openspec/specs/lancedb-vector-store/spec.md` on archive.
- **Users:** Python callers that pass a naive datetime, a Decimal or a NaN in `metadata_filter` on the LanceDB store get a `ValueError`. Existing collections need no migration. A table written by lancedb 0.40.0 opens and accepts writes on 0.37.1 (probe in `probes.md`), so a rollback keeps the data readable.
- **CI:** the floor jobs install lancedb 0.40.0. The change merges only after three full CI attempts with every floor job green.
- **Live app:** reinstall it after the merge with the new lock as constraints.
