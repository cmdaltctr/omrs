# Design

## Context

See proposal.md for the reason. The evidence for each decision is in `probes.md` (P1 to P7). Current state:

- `pyproject.toml` declares `lancedb>=0.37`, `pylance>=10` and `pyarrow>=25.0.1`. `uv.lock` has lancedb 0.37.1, pylance 10.0.0, pyarrow 25.0.1 and `llama-index-vector-stores-lancedb` 0.5.0.
- The floor jobs run `uv sync --resolution lowest-direct` (`.github/workflows/ci.yml`, job `floors`, ten matrix entries). For these packages the floor install and the lock install are the same versions.
- `uv lock --upgrade-package lancedb` moves only lancedb, 0.37.1 to 0.40.0. With that lock, the fast suite had two failures: `tests/test_lance_filter_security.py::test_faithful_scalar_accepted` and `tests/test_lancedb_native_fts_contract.py::test_locked_lancedb_versions`.
- `core/vectordb/lancedb/literal.py` checks each `lit(value).to_sql()` fragment against a closed form per value type and refuses any other form (ADR-046, ADR-058).
- `core/vectordb/lancedb/filter.py` (`_leaf`) folds a predicate on a schema-absent field to a constant before it builds the literal. Field-name and membership checks run before the fold.
- `tests/_lance_child.py` ends each writer child with `os._exit(0)` after a finished marker (TDR-040 decision 1).

## Goals / Non-Goals

**Goals:**

- Production and test processes that write to LanceDB exit with status 0 after a successful write.
- No filter changes the rows it matches without an error, across the upgrade.
- The floor jobs and the normal jobs test the same lancedb version that unlocked installs get.

**Non-Goals:**

- pylance 13 and pyarrow 26 (D1 gives the reason; a later change can move them).
- `llama-index-vector-stores-lancedb` 0.6.0.
- A parameterised filter path. lancedb 0.40.0 still has none (P1), so ADR-058 stays in force.
- Changes to the Chroma store or to `core/retrieval/filters.py`.
- A fix for the apostrophe-run and backslash-apostrophe bugs in `lit`. They are unchanged on 0.40.0 (P1), and the existing refusal stays.

## Decisions

### D1. Move lancedb only: floor `>=0.40`, lock 0.40.0

Raise the floor to `lancedb>=0.40` and lock 0.40.0. Keep `pylance>=10` (lock 10.0.0), `pyarrow>=25.0.1` (lock 25.0.1) and the adapter at 0.5.0. Use `uv lock --upgrade-package lancedb`.

Reasons:

1. The exit crash fix is in lancedb only. PR #4175 changes `python/src/runtime.rs` in lancedb. pylance has a separate runtime with no shutdown hook in v10.0.0 or v13.0.0 (P5). A pylance upgrade does not help the crash.
2. The floor must be 0.40, not `>=0.37` with a lock of 0.40.0. A floor below 0.40 lets the floor jobs install a release that has the crash. ADR-042 sets the floor at the lowest version that is safe for the project's use, and for this crash that is 0.40.0.
3. With the floor equal to the lock, the floor jobs test exactly the lock, so CI verifies the new contract directly.
4. The smallest lock change has the smallest blast radius. `uv lock --upgrade-package lancedb` changed one package entry and one specifier. The fast suite showed only the two expected failures.
5. lancedb 0.40.0 builds on Rust lance 13.0.0, and pylance 10.0.0 builds on lance 10.0.0 (upstream facts in `probes.md`). Two lance cores run in one process. Upstream tests this kind of pair: lancedb v0.40.0 runs its own test suite with `pylance==9.0.0`. The OMRS fast suite passed on 0.40.0 with pylance 10.0.0, apart from the two expected failures. This includes the native FTS contract tests and the `update_schema_metadata` paths. Lance feature flags stop an older writer that does not know a dataset feature, so a mismatch fails loudly.

Alternatives:

| Option | Rejected because |
|---|---|
| Also move pylance to 13.0.0 | Three majors to check for `update_schema_metadata`, the scanner and the epoch metadata. It pulls lance-namespace 0.8.6 to 0.11.1. It does nothing for the crash. P6 shows no difference for this project's calls, so it is a good follow-up, not a part of this fix. |
| Also move pyarrow to 26.0.0 | The 25.0.1 floor exists for apache/arrow GH-50471 (TDR-040). Nothing here needs 26. |
| Keep `lancedb>=0.37`, lock 0.40.0 | The floor jobs would keep installing 0.37.1, which has the crash. The floor would claim support for versions that crash. |
| Add an upper bound such as `lancedb<0.41` | ADR-042 uses floors, not ceilings. lancedb 0.41 can change literal forms again (PR #4449 already changes Decimal parsing). The fail-closed check refuses an unknown form, so a ceiling is not needed for safety. |

### D2. Refuse a naive datetime filter value

A `datetime` without `tzinfo` (or with `utcoffset()` equal to `None`) in a filter raises `ValueError` before the absent-field fold and before `lit`. The message names the value class and tells the caller to pass an aware datetime, for example `datetime(2026, 9, 2, 14, 30, tzinfo=UTC)`. Aware datetimes and dates keep their current forms and checks.

Evidence: lancedb 0.37.1 read a naive datetime as local time and converted it to UTC. lancedb 0.40.0 reads it as UTC wall clock (PR #3775). On a BST host, the same naive filter matched `['c', 'd', 'e']` on 0.37.1 and `['d', 'e']` on 0.40.0, with no error (P2). On a GMT host the two versions agree, so the change shows only on some hosts and only for part of the year.

How OMRS stores and receives datetimes:

- No OMRS table has a timestamp metadata field. The adapter accepts only `str`, `int`, `float` and `None` metadata values, and the upsert path stores other values as text or fails (P4). Date-like metadata such as `creation_date` is ISO text.
- MCP and HTTP `metadata_filter` values come from JSON, which has no datetime type. Only a Python caller of `Engine.search`, `Engine.answer` or a delete path can pass a datetime.

Options:

| Option | Rows match as before? | Time zone explicit? | Decision |
|---|---|---|---|
| (a) Convert naive to aware with the host time zone, then call `lit` | Yes | No. The result depends on the host time zone and on daylight saving time. An ambiguous or missing local time (the hour at a clock change) has no single answer. | Rejected |
| (b) Treat naive as UTC (the 0.40.0 behaviour, stated as a rule) | No, on any host that is not on UTC | Yes, but the change is silent | Rejected |
| (c) Refuse naive, accept aware | Every filter that runs gives the same rows as before, and every other filter fails with an error | Yes | **Chosen** |
| (d) Accept 0.40.0 as is | No | No | Rejected |

Migration impact: stored data does not change and needs no re-ingest. A Python caller that passes a naive datetime gets a `ValueError` and must add `tzinfo`. An aware filter matches the same rows as before. The library usage guide states the accepted value types.

### D3. Literal forms: accept infinite floats, refuse NaN and Decimal

The closed forms after this change:

| Value class | Accepted fragment | Check |
|---|---|---|
| finite `float` | the current `_NUMERIC_FORM` text | `float(sql) == value`, as now |
| `float("inf")` | exactly `arrow_cast('inf', 'Float64')` | string equality |
| `float("-inf")` | exactly `arrow_cast('-inf', 'Float64')` | string equality |
| `float("nan")` | none | refused before `lit` with a value-class error |
| `Decimal` | none | refused before `lit` with a value-class error |
| naive `datetime` | none | refused before `lit` (D2) |
| aware `datetime` | `CAST('<UTC wall clock>' AS TIMESTAMP)` | as now, aware branch only |
| `bool`, `int`, `str`, `bytes`, `date` | unchanged | unchanged |

The bare forms `inf`, `-inf` and `NaN` are no longer accepted. On 0.37.1 they reached the engine and failed as unknown column names (P2), so no working filter loses them.

Infinite floats. The new form is the engine's own typed literal. It returns the correct rows on 0.40.0 (P2), and the Python evaluator gives the same answer for `inf` comparisons. Exact text equality keeps the check closed: a wrong special value, a bare name or a wrong type (`Float32`) fails. The first draft of this change already had a parametrised test for these cases, and task 2.1 carries it over.

NaN. On 0.40.0 the engine says `NaN = NaN` is true and orders NaN above every number. The Python evaluator in `core/retrieval/filters.py` says every NaN comparison is false. A hybrid search would then filter its two branches with different rules, which the hybrid-retrieval spec forbids ("Hybrid metadata filters constrain every retrieval branch"). On 0.37.1 a NaN filter failed, so refusing it removes no working behaviour.

Decimal. Decimal is refused even though the engine's fragment can be checked exactly. The check would pass, but the comparison is still wrong: lancedb 0.40.0 casts the float column to a decimal type, so `1e-20 > Decimal("0")` becomes false, `0.30000000000000004 = Decimal("0.3")` becomes true, and a large or infinite stored float makes the whole query fail (P2, P3). The Python evaluator and lancedb 0.37.1 both compare exactly. OMRS cannot store a Decimal (P4), and Chroma does not accept one as a `where` value. Decimal forms also keep moving upstream (PR #4449 changes exponent parsing after 0.40.0).

The rejected alternative, so that a later change can use it: accept `arrow_cast('<s>', 'Decimal128(<p>, <q>)')` only when all of these are true:

1. `<s>` matches `-?\d+(\.\d+)?` (no exponent, no sign on zero) and `Decimal(<s>) == value`.
2. `<q>` is the count of digits after the point in `<s>`, and `<p>` is the count of all digits in `<s>`, including a leading `0` (P1: `0.05` gives `(3, 2)`, `100` gives `(3, 0)`, `-0.001` gives `(4, 3)`).
3. `1 <= <p> <= 38` and `0 <= <q> <= <p>`. P1 shows that the engine emits `Decimal128(39, 0)` for 39 digits, which is not a valid Arrow type, so rule 3 must refuse it.

This rule is faithful to the value. It does not fix the column cast, so it was not chosen.

Where the refusal runs: one function in `literal.py` checks the value class. `filter.py` calls it for the scalar and for each membership item, before the absent-field fold, the same as the field-name and membership checks. `_literal_sql` also calls it, so no path reaches `lit` with a refused class. `_is_faithful_literal` returns false for Decimal, NaN and naive datetime, so a later caller that skips the class check still fails closed. The local-time branch in `_datetime_matches` is removed, because no naive value reaches it.

Test changes:

- `test_faithful_scalar_accepted`: remove `Decimal` and naive datetime values. Keep `inf` and `-inf` (they now need the new form). Keep aware datetimes.
- `test_mismatched_scalar_refused`: remove the Decimal, NaN and naive datetime cases from this test, because they now fail at the class check with a different message. New tests cover them (task group 2). Add `float("inf")` and `float("-inf")` cases where the fake `lit` emits a different `arrow_cast` value.
- `_MismatchedLit` and `_SwappedCastLit` lose their naive-datetime local-time code.
- New tests: the special-float form table from the draft patch, a refusal test per refused class (scalar, `$in` item, schema-absent field), and an engine test that `inf` and `-inf` filters return the expected rows.

### D4. Remove the exit bypass from the child helper

`tests/_lance_child.py` keeps `PYTHONFAULTHANDLER=1`, the stdout and stderr in the assertion message, and the `lance child finished` marker as the last line of the script body. It no longer calls `os._exit(0)`, so the child runs normal interpreter shutdown. TDR-040 names this as its revisit trigger.

The helper tests change:

- `test_a_crash_at_shutdown_after_the_body_does_not_fail` becomes a test that a crash in an `atexit` handler fails the run, and the failure message holds the marker and the faulthandler output.
- A new test shows that the child runs its `atexit` handlers: the child registers one that prints a second marker, and the test asserts that stdout holds it. It fails while the bypass is still in the helper.
- A new test runs a short LanceDB write in a child 20 times through the helper and asserts that each run exits 0. It is a regression guard on the real fix. macOS did not reproduce the crash in 40 runs on 0.37.1 (TDR-040), so this test alone is not the proof.

The proof is CI: three full CI attempts on the pull request head, with all ten floor jobs, the test job and the other jobs green in each attempt. PR #129 used the same rule. Each floor job runs the three writer tests (`test_sparse_cache_freshness.py`, `test_lance_dataset_epoch.py`, `test_bm25_validity_token.py`) in parallel with the rest of the suite, which is the load that crashed them before.

Fallback: if a writer child crashes at exit in any attempt, read the faulthandler output and the marker. A crash after the marker on 0.40.0 points at the pylance runtime (P5, lance issue #4152). Then restore the epilogue, keep the upgrade (it still fixes the lancedb part), and record the new cause in TDR-040. Do not retry jobs to get green runs.

### D5. Version pin and present-tense version notes

- `test_locked_lancedb_versions` asserts lancedb 0.40.0 and pylance 10.0.0. The module docstring names the new pair. The FTS behaviour pins in that file passed unchanged on 0.40.0.
- `test_hybrid_retrieval.py` docstring, and the docstrings in `literal.py`, `filter.py`, `fts.py`, `meta.py` and `store.py` that describe current behaviour: name the verified pair. Where a fact was checked on both versions (the apostrophe bug, no struct field access), say both.
- The `pyproject.toml` comment for lancedb gives the new reason (PR #4175, TDR-040, ADR-098) and keeps the `lancedb.expr` reason.
- Accepted ADRs (046, 054, 058) and TDR-012 are records of their date. They are not edited. ADR-098 lists them as related. TDR-040 gets a dated note that its revisit trigger fired, with the result of D4.
- `openspec/specs/lancedb-vector-store/spec.md` changes through the delta in this change.

### D6. Tripwire re-pin by collected test IDs

Collect the fast-suite test IDs on v3 at `ed212f67` and on the feature branch (`pytest -m "not slow" --collect-only -q`). Diff the two lists. Change `_BASE_EXECUTED` by the added IDs minus the removed IDs, with a dated comment that names each file and count. A count per file can hide a case that one test replaced with another, so the ID diff is the source.

## Risks / Trade-offs

- [The crash has a second cause in the pylance runtime] → D4 fallback. The faulthandler and marker show where it happened.
- [Two lance cores in one process (lancedb on lance 13, pylance 10)] → The fast suite and the FTS contract pins pass. Upstream tests a similar pair. A follow-up change moves pylance to 13 with its own probes (P6 is the start).
- [Unlocked installs get pylance 13 and pyarrow 26, which CI does not test] → P6 shows the same behaviour for this project's calls. The follow-up change above closes the gap. Until then, install the app with the lock as constraints (Migration Plan).
- [A Python caller passes a naive datetime, a Decimal or a NaN] → It gets a `ValueError` that names the value class and the accepted type. MCP and HTTP callers cannot send these values in standard JSON.
- [A later lancedb release changes a literal form again] → The fail-closed check refuses the unknown form, and the floor jobs and `test_faithful_scalar_accepted` show it.
- [A Python caller passed an aware datetime to compare a text date field] → The form is unchanged on 0.40.0 and the rows match as before (P2).

## Migration Plan

1. Merge after three green CI attempts (D4).
2. Users with a locked install run `uv sync`. Users who install the tool get lancedb 0.40.0 already. Existing collections need no migration (P7 shows that data written on 0.40.0 stays readable on 0.37.1).
3. Reinstall the live app with the lock as constraints, so that `uv tool install` cannot pick other versions. From the checkout that holds the merged lock, run:

   ```bash
   uv export --frozen --no-hashes --no-emit-project --extra web > /tmp/omrs-constraints.txt
   uv tool install --reinstall -c /tmp/omrs-constraints.txt "omrs[web] @ file://$PWD"
   omrs web restart
   ```

   Name every extra that the app uses in both commands. Then check the versions in the tool environment: lancedb 0.40.0, pylance 10.0.0, pyarrow 25.0.1.
4. Rollback: revert the merge commit and run `uv sync`. P7 shows that lancedb 0.37.1 reads and appends to tables written by 0.40.0. The test helper returns to the `os._exit(0)` epilogue with the revert.
5. After the merge, set ADR-098 to Accepted and update its row in `docs/adr/ADR_README.md`.
