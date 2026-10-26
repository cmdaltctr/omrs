# Tasks

## 1. Baseline

- [x] 1.1 Confirm the worktree with `git rev-parse --show-toplevel` and `git branch --show-current`. Verify: the root is the `llamaindex-rag-mcp-feat-upgrade-lancedb-0-40` worktree and the branch is `feat/upgrade-lancedb-0-40`.
- [x] 1.2 Save the v3 fast-suite test IDs. In the v3 worktree at `ed212f67`, run `uv run --no-sync pytest -m "not slow" --collect-only -q > <scratch>/ids-v3.txt`. Do not change files in that worktree. Verify: the file lists one test ID per line and ends with the collected count.
- [x] 1.3 Run the fast suite on the branch before any change: `uv run --no-sync pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`. Verify: it passes on lancedb 0.37.1.

## 2. Failing tests for the literal rules (design D2, D3)

Write every test in this group before any change to `src/` or `uv.lock`. Run each new test on lancedb 0.37.1 and record that it fails for the expected reason.

- [x] 2.1 Add `test_special_float_needs_its_own_float64_cast` to `tests/test_lance_filter_security.py`. Parametrise it over the bare names (`inf`, `-inf`), a cast of the other infinity, and `arrow_cast('inf', 'Float32')`. Assert `_is_faithful_literal` refuses each one. Add a positive case that `arrow_cast('inf', 'Float64')` and `arrow_cast('-inf', 'Float64')` are accepted for their own value. Verify: the positive case fails on the current code and the refusal cases for bare names fail too.
- [x] 2.2 Add `test_naive_datetime_is_refused`. Call `translate_where` with a naive datetime as a scalar, as a `$in` item, and on a schema-absent field (`known_fields` without the field). Assert a `ValueError` whose message contains `naive datetime` and `time zone`. Verify: all three cases fail on the current code (it accepts the value, or folds the absent field to a constant).
- [x] 2.3 Add `test_decimal_is_refused` with the same three shapes. Assert a `ValueError` whose message contains `Decimal` and `int or a float`. Verify: all three cases fail on the current code.
- [x] 2.4 Add `test_nan_is_refused` with the same three shapes. Assert a `ValueError` whose message contains `NaN`. Verify: all three cases fail on the current code.
- [x] 2.5 Add `test_refused_classes_are_unfaithful`. Assert `_is_faithful_literal` returns false for a Decimal with its 0.37.1 form and its 0.40.0 form, for NaN with `NaN` and `arrow_cast('NaN', 'Float64')`, and for a naive datetime with a `CAST(... AS TIMESTAMP)` fragment. Verify: it fails on the current code.
- [x] 2.6 Add an engine test that writes rows with `inf`, `-inf` and finite floats to a real table under `tmp_path` and filters with `$eq` on `float("inf")`, `$eq` on `float("-inf")` and `$lt` on `float("inf")`. Assert the row IDs listed in `probes.md` P2. Verify: it fails on lancedb 0.37.1 with the planner error `No field named inf`.
- [x] 2.7 Add an engine test with ISO date text in a metadata field and an aware datetime filter (`$gte`, `tzinfo=UTC`). Assert the row IDs from `probes.md` P2. Verify: it passes on 0.37.1. It is a guard that must stay green after the upgrade.

## 3. Dependency and literal changes (design D1, D3)

- [x] 3.1 Change `"lancedb>=0.37"` to `"lancedb>=0.40"` in `pyproject.toml`. Rewrite its comment: 0.40.0 is the first release that shuts its Tokio runtime down at interpreter exit (lancedb PR #4175, TDR-040, ADR-098), and 0.37 added `lancedb.expr` (PR #3150). Run `uv lock --upgrade-package lancedb`. Verify: `git diff uv.lock` changes only the `lancedb` package entry (0.37.1 to 0.40.0, with its wheels) and the `lancedb` specifier in `requires-dist`. pylance stays 10.0.0 and pyarrow stays 25.0.1. The commit that raises the floor carries a `BREAKING CHANGE` footer that names `lancedb`, the old floor 0.37 and the new floor 0.40 (spec `dependency-floor-integrity`, "Floor raises are declared as breaking changes").
- [x] 3.2 Run `uv sync --frozen --extra web`. Verify: `uv run --no-sync python -c "import lancedb, lance, pyarrow; print(lancedb.__version__, lance.__version__, pyarrow.__version__)"` prints `0.40.0 10.0.0 25.0.1`.
- [x] 3.3 In `src/omrs/core/vectordb/lancedb/literal.py`, replace `_FLOAT_SPECIAL_FORMS` with exact accepted text for `inf` and `-inf`. Add one value-class check function that refuses a Decimal, a float NaN and a naive datetime with the messages from tasks 2.2 to 2.4. Call it from `_literal_sql`. Make `_is_faithful_literal` return false for the three refused classes. Remove the local-time branch from `_datetime_matches`. Verify: tests 2.1, 2.3 to 2.6 pass, and the file stays under 500 lines.
- [x] 3.4 In `src/omrs/core/vectordb/lancedb/filter.py` (`_leaf`), call the value-class check for the scalar operand and for each membership item before the absent-field fold. Verify: the schema-absent cases of tests 2.2 to 2.4 pass.
- [x] 3.5 Update the existing tests that the new rules change (design D3, "Test changes"): `test_faithful_scalar_accepted`, `test_mismatched_scalar_refused`, `_MismatchedLit` and `_SwappedCastLit`. Do not weaken any other assertion. Verify: `uv run --no-sync pytest tests/test_lance_filter_security.py tests/test_lance_filter.py -q` passes, and the diff removes only Decimal, NaN and naive-datetime cases from those tests.
- [x] 3.6 Do a mutation check. Change the accepted infinity text to `arrow_cast('inf', 'Float32')` for one run. Then remove the value-class call from `filter.py` for one run. Verify: test 2.1 fails on the first mutation, the schema-absent cases of tests 2.2 to 2.4 fail on the second, and both mutations are reverted.
- [x] 3.7 Update the present-tense version notes in the docstrings of `literal.py`, `filter.py`, `fts.py`, `meta.py` and `store.py` (design D5). Where a fact was checked on both versions, name both. Verify: `git grep -n "0\.37" src/` lists only lines that also name 0.40.0 or that describe history.
- [x] 3.8 State the accepted filter value types in `docs/guides/library-usage.md` next to the `metadata_filter` argument of `search`: `str`, `int`, finite or infinite `float`, `bool`, and `date` or a datetime with a time zone on LanceDB; naive datetime, Decimal and NaN raise `ValueError`. Verify: the text names each refused class and its alternative.

## 4. Version pin (design D5)

- [x] 4.1 Change `test_locked_lancedb_versions` in `tests/test_lancedb_native_fts_contract.py` to assert lancedb `0.40.0` and pylance `10.0.0`. Update the module docstring to the new pair. Verify: the test passes, and it fails when the assertion is set back to `0.37.1`.
- [x] 4.2 Update the docstring of `test_sparse_backend_auto_selects_native_when_supported` in `tests/test_hybrid_retrieval.py` to name lancedb 0.40.0. Verify: `uv run --no-sync pytest tests/test_lancedb_native_fts_contract.py tests/test_hybrid_retrieval.py -q` passes.

## 5. Child helper without the exit bypass (design D4)

- [x] 5.1 In `tests/test_lance_child_helper.py`, add a test that a child registers an `atexit` handler that prints `exit handlers ran`, and assert that stdout holds that line. Change `test_a_crash_at_shutdown_after_the_body_does_not_fail` so that the crash in the `atexit` handler fails the run, and the failure message holds the finished marker and `Fatal Python error`. Verify: both tests fail with the current helper.
- [x] 5.2 Remove `import os as _os` and `_os._exit(0)` from the epilogue in `tests/_lance_child.py`. Keep the marker print, the stderr flush and `PYTHONFAULTHANDLER=1`. Update the module docstring: lancedb 0.40.0 and later shut the runtime down at exit, and the child runs normal shutdown, so a crash at exit fails the test. Verify: the tests from 5.1 pass, and the other helper tests still pass or are updated to the new rule with a reason in the diff.
- [x] 5.3 Add a test that runs a short LanceDB write (create a table under `tmp_path`, add one row, call `to_lance().update_schema_metadata`) in a child through `run_lance_child` 20 times. Verify: all 20 runs exit 0 locally on lancedb 0.40.0.
- [x] 5.4 Run the three writer tests 40 times in a loop with `-n auto`: `test_sparse_cache_freshness.py`, `test_lance_dataset_epoch.py` and `test_bm25_validity_token.py`. Verify: 40 of 40 runs pass. Record the result in `openspec/changes/upgrade-lancedb-0-40/probes.md`.
- [ ] 5.5 Add a dated note under Revisit Triggers in `docs/tdr/040-lancedb-writer-processes-crashed-at-interpreter-exit-on-the-floor-jobs.md`: the upgrade landed, the epilogue is removed, and the CI result from task 7.3. Verify: the note names the pull request and the three run IDs.

## 6. Decision record

- [x] 6.1 Review `docs/adr/098-upgrade-lancedb-to-0-40-and-refuse-ambiguous-filter-values.md` against the final code. Verify: each decision in the ADR matches the code and the tests, and the status is Proposed.
- [x] 6.2 Check that `docs/adr/ADR_README.md` has the ADR-098 row. Verify: the link opens the file.

## 7. Integration

- [x] 7.1 Re-pin the tripwire (design D6). Collect the branch test IDs with `uv run --no-sync pytest -m "not slow" --collect-only -q > <scratch>/ids-branch.txt`. Diff them against `ids-v3.txt` from task 1.2. Change `_BASE_EXECUTED` in `tests/test_clean_base_tripwire.py` by added minus removed IDs, with a dated comment that names each file and its count (each line under 100 characters). Verify: the tripwire passes with `OMRS_TRIPWIRE_JUNIT` set and without it.
- [ ] 7.2 Run `./scripts/local_ci.sh`. Verify: every step passes, and no step prints `SKIPPED`.
- [ ] 7.3 Push the branch and open the pull request against `v3`. Run the full CI three times on the same head commit (the first run plus two re-runs of all jobs). Verify: each of the three attempts is fully green, with all ten floor jobs. Do not re-run only failed jobs. If a writer child crashes in any attempt, follow the D4 fallback and stop the merge.
- [x] 7.4 Search the docs for stale version text: `git grep -n "0\.37\.1\|lancedb>=0\.37\|lancedb 0\.37" -- docs AGENTS.md CLAUDE.md README.md src tests openspec/specs`. Verify: every hit is in an accepted ADR or TDR (a dated record), in this change, or names 0.40.0 as well.
- [x] 7.5 Run `openspec validate upgrade-lancedb-0-40 --strict` and `openspec validate --all --strict`. Verify: both pass.
- [ ] 7.6 After the merge, set ADR-098 to Accepted, with the merge date, in the ADR and in `docs/adr/ADR_README.md`. Verify: both say Accepted.
- [ ] 7.7 After the merge, reinstall the live app with the lock as constraints (design Migration Plan step 3). Verify: the tool environment reports lancedb 0.40.0, pylance 10.0.0 and pyarrow 25.0.1, and `omrs web status` shows the new version running.
