# ADR-098: Upgrade lancedb to 0.40 and Refuse Ambiguous Filter Values

- **Date:** 2026-10-25
- **Status:** Proposed
- **Deciders:** Maintainer
- **Related:** [ADR-042](042-dependency-floor-integrity.md) (dependency floors), [ADR-046](046-lancedb-vector-store-backend.md) (LanceDB backend), [ADR-058](058-lancedb-filter-policy-exception.md) (filter policy exception), TDR-040 (writer crash at interpreter exit)
- **Change:** `openspec/changes/upgrade-lancedb-0-40/` (design D1 to D6, evidence in `probes.md`)

## Context

lancedb before 0.40.0 does not shut its Tokio runtime down at interpreter exit. A short-lived process that writes to LanceDB can crash with SIGSEGV or SIGABRT after the write has finished. The floor CI jobs hit this in five runs on 2026-10-25 (TDR-040). lancedb PR #4175 (merged 2026-09-15) registers an `atexit` callback that shuts the runtime down. lancedb 0.40.0 (2026-10-07) is the first release with it.

The tests hide the crash: `tests/_lance_child.py` ends each writer child with `os._exit(0)`. Real processes such as `omrs ingest` still carry it, on lancedb 0.37.1 from the lock.

Unlocked installs already run 0.40.0. `uv tool install` ignores `uv.lock`, and the live app was found on lancedb 0.40.0, pylance 13.0.0 and pyarrow 26.0.0, a set that CI never tested.

The upgrade changes the output of `lancedb.expr.lit`, which the filter adapter uses for every value (ADR-046, ADR-058). Probes on 0.37.1 and 0.40.0 (`probes.md`) found four changes:

| Value | 0.37.1 | 0.40.0 | Effect |
|---|---|---|---|
| `float("inf")`, `-inf` | bare `inf`, `-inf`; the engine reads them as column names and the filter fails | `arrow_cast('inf', 'Float64')`; correct rows | the fail-closed check refuses the new form |
| `float("nan")` | bare `NaN`; the filter fails | `arrow_cast('NaN', 'Float64')`; the engine says `NaN = NaN` | dense and in-memory sparse filters would disagree |
| `Decimal` | plain number; compared as a float | `arrow_cast('3.14', 'Decimal128(3, 2)')`; the float column is cast to decimal | rows dropped (`1e-20 > 0` false) or added (`0.1 + 0.2 = 0.3` true) with no error, or the query fails |
| naive `datetime` | local time converted to UTC | kept as UTC wall clock (lancedb PR #3775) | on a BST host the same filter matched `c, d, e` before and `d, e` after, with no error |

OMRS cannot store a datetime or a Decimal metadata value: the adapter accepts only `str`, `int`, `float` and `None`, and the upsert path stores other values as text or fails. MCP and HTTP filters come from JSON, which has no datetime, Decimal or NaN value. Only Python callers of the Engine can pass these values.

## Decision

1. **Raise the lancedb floor from `>=0.37` to `>=0.40` and lock 0.40.0.** Keep `pylance>=10` (lock 10.0.0), `pyarrow>=25.0.1` (lock 25.0.1) and `llama-index-vector-stores-lancedb` 0.5.0. The crash fix is in lancedb only: pylance has its own runtime with no shutdown hook in 10.0.0 or 13.0.0. With the floor equal to the lock, the floor jobs test the exact contract. lancedb 0.40.0 builds on Rust lance 13.0.0, so it runs beside pylance 10.0.0 with two lance cores. Upstream runs lancedb 0.40.0 tests with pylance 9.0.0, and the OMRS fast suite passes on this pair.
2. **Accept infinite floats only as the exact typed form** `arrow_cast('inf', 'Float64')` or `arrow_cast('-inf', 'Float64')`. The bare names, the other infinity and any other type are refused.
3. **Refuse a naive datetime, a Decimal and a float NaN** in a filter with a `ValueError` that names the value class and the accepted alternative: a datetime with a time zone, or an `int` or a `float`. The check runs for scalars and membership items, before a schema-absent field folds to a constant, and before `lit`. `_is_faithful_literal` also returns false for these classes. Aware datetimes, dates, bytes, ints, bools, strings and finite floats keep their forms and checks.
4. **Remove the `os._exit(0)` step from `tests/_lance_child.py`.** Writer children run normal interpreter shutdown again, so a crash at exit fails the test. The finished marker and `PYTHONFAULTHANDLER=1` stay.
5. **Merge only after three full CI attempts on one head commit are green, with all ten floor jobs.** If a writer child crashes at exit in any attempt, restore the epilogue, keep the upgrade, and record the new cause in TDR-040.

## Consequences

### Positive

- A process that writes to LanceDB exits with status 0 after a successful write. `omrs ingest` no longer reports a wrong exit status after a good write.
- The tests cover interpreter shutdown of LanceDB writers again.
- No filter matches different rows across the upgrade without an error. A filter either gives the rows it gave before or fails with an error that says what to pass.
- Infinite float filters work. On 0.37.1 they failed.
- CI tests the lancedb version that unlocked installs get.

### Negative

- **Breaking for Python callers:** a naive datetime, a Decimal or a NaN in `metadata_filter` on the LanceDB store now raises `ValueError`. The caller must add `tzinfo`, or pass an `int` or a `float`.
- **Breaking install contract:** the lancedb floor rises from 0.37 to 0.40.
- Two lance cores run in one process (lancedb on lance 13, pylance 10) until a later change moves pylance.
- Unlocked installs resolve pylance 13 and pyarrow 26, which CI does not test. A probe showed the same behaviour for the calls OMRS makes.

### Neutral

- Existing collections need no migration. lancedb 0.37.1 reads and appends to a table written by 0.40.0, so a rollback keeps data readable.
- The apostrophe-run and backslash-apostrophe bugs in `lit` are the same on 0.40.0. The existing refusal stays.
- lancedb 0.40.0 still has no bind parameters and no struct field access, so ADR-058 stays in force.
- The accepted ADRs 046, 054 and 058 name lancedb 0.37.1 as the verified version of their date. They are not edited.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Upgrade pylance to 13.0.0 and pyarrow to 26.0.0 in the same change | Neither helps the crash. pylance 13 is three majors and moves lance-namespace from 0.8.6 to 0.11.1. It is a follow-up with its own probes. |
| Keep the floor at `>=0.37` and lock 0.40.0 | The floor jobs would keep testing 0.37.1, which has the crash, and the floor would claim support for versions that crash. |
| Convert a naive datetime with the host time zone (the 0.37.1 behaviour) | The rows depend on the host time zone and on daylight saving time. A local time in a clock change hour has no single answer. |
| Treat a naive datetime as UTC (the 0.40.0 behaviour) | It changes which rows match on every host that is not on UTC, with no error. |
| Accept the Decimal form with an exact `Decimal128(p, s)` check | The literal would be faithful, but the engine casts the float column, so the comparison is wrong or fails. The exact rule is in design D3 for a later change. |
| Accept NaN in the new form | Dense filtering would say `NaN = NaN` and the in-memory BM25 filter would not, so one hybrid search would use two rules. |
| Keep the `os._exit(0)` epilogue after the upgrade | It hides any crash at exit, including one from a later regression. TDR-040 names its removal as the revisit trigger. |
| Add a ceiling such as `lancedb<0.41` | ADR-042 uses floors. The fail-closed literal check already refuses an unknown form from a later release. |

## References

- lancedb PR #4175, runtime shutdown at interpreter exit: https://github.com/lancedb/lancedb/pull/4175
- lancedb PR #3775, naive `lit(datetime)` as UTC wall clock: https://github.com/lancedb/lancedb/pull/3775
- lancedb PR #4449, Decimal exponent parsing (after 0.40.0): https://github.com/lancedb/lancedb/pull/4449
- lance issue #4152, shutdown crash in the pylance runtime (open): https://github.com/lance-format/lance/issues/4152
- `openspec/changes/upgrade-lancedb-0-40/probes.md` (P1 to P7)
- `src/omrs/core/vectordb/lancedb/literal.py`, `src/omrs/core/vectordb/lancedb/filter.py`
- `tests/_lance_child.py`, `tests/test_lance_child_helper.py`, `tests/test_lance_filter_security.py`, `tests/test_lance_filter_value_classes.py`, `tests/test_lancedb_native_fts_contract.py`
- `docs/tdr/040-lancedb-writer-processes-crashed-at-interpreter-exit-on-the-floor-jobs.md`
