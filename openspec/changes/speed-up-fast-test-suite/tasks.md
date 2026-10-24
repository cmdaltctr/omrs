# Tasks

## 1. Baseline

- [ ] 1.1 Confirm the worktree root and branch with `git rev-parse --show-toplevel` and `git branch --show-current`. Verify: both match the feature worktree for this change.
- [ ] 1.2 Run the fast suite in parallel with `--junitxml` and `--durations=25`. Record the wall time, the 25 slowest tests and the passed count in `openspec/changes/speed-up-fast-test-suite/timing.md`. Also record the wall time of the tripwire step. Verify: the file holds the before numbers.

## 2. Factory defaults (design D1)

- [ ] 2.1 Write a test in `tests/unit/` for the factory defaults. It checks that a factory-built settings object has `extraction_mode="disabled"` and `classify_max_attempts=1`. It also checks that a dotted override keeps the other metadata defaults, and that a whole `MetadataBlock` stays as given. Verify: the first assertion fails on the current factory.
- [ ] 2.2 Add the metadata entry to `factory_block_defaults` in `tests/conftest.py`. Verify: the test from 2.1 passes.
- [ ] 2.3 Change the direct `EffectiveSettings(...)` calls in the probe-hit tests to the factory or to an explicit disabled block: `test_retrieval.py:780`, `test_ingestion.py:67` and the two `TestAzureDocumentBranch` tests in `test_core_coverage_v2.py`. Verify: each of these tests finishes in under 5 s with `--durations`.
- [ ] 2.4 Run the fast suite. List every test that now fails because it depended on the old `llamaindex` default. Give each one an explicit mode (and a mock where it needs one), or accept `disabled` when the test does not check extraction. Verify: the fast suite passes and no assertion was weakened (check the diff).
- [ ] 2.5 Update the factory description in `docs/guides/testing.md`, rule 1 in `tests/AGENTS.md` and gotcha 8a in `CLAUDE.md` with the new defaults. Gotcha 8a (commit `e4ce75e5`) says the factory does not set `extraction_mode`, so each test must pass it; after this change that is no longer true. Verify: the text names both defaults and how to override them.

## 3. Guard against unplanned LLM metadata calls (design D2)

- [ ] 3.1 Register the `metadata_llm` marker in `pyproject.toml`. Write tests for the guard: an unmarked test that dispatches `llamaindex` fails with a message naming the strategy, a marked one does not fail, and `keyword` and `disabled` do not trigger the guard. Use `pytester` or a subprocess run. Verify: the tests fail before the guard exists.
- [ ] 3.2 Add the autouse guard fixture to `tests/conftest.py`. Verify: the tests from 3.1 pass.
- [ ] 3.3 Change `test_coverage_gaps_v2.py::TestOpenRouterExtraction::test_cloud_provider_routes_to_openrouter` to patch `omrs.core.metadata.registry._cache` directly. Verify: it passes with the guard in place.
- [ ] 3.4 Add the marker to the tests that exercise LLM strategies on purpose. Use `pytestmark` for whole modules and single marks elsewhere (design D2 list). Check each one: it must have meant to call the strategy. Verify: the fast suite passes and `git grep -n metadata_llm tests` lists only those tests.
- [ ] 3.5 Do a mutation check. Remove the D1 default from the factory for one run, and confirm that the guard fails the tests listed in 2.3 and 2.4. Restore the default. Verify: record the failing test names in `timing.md`.
- [ ] 3.6 Document the guard and the marker in `docs/guides/testing.md` and `tests/AGENTS.md`. Verify: the text says when to use the marker.

## 4. OCR timeout test (design D3)

- [ ] 4.1 Add an assertion to `test_post_dispatch_timeout_is_a_structured_error` that the error names a 1-second wait. Verify: it fails today (the message says 120.0 seconds).
- [ ] 4.2 Set `ocr_worker_seconds_per_page=0.0` in that test's settings. Verify: the test passes in under 10 s with `--durations`.

## 5. Tripwire reads the fast-suite report (design D4)

- [ ] 5.1 Write tests for the report reader in the tripwire module or in a helper next to it. Cover the passed count from a sample report, a report with a failure, a report with an error, a missing file, and a report older than a source file. Use small XML files in `tmp_path`. Verify: the tests fail before the reader exists.
- [ ] 5.2 Implement the reader. Make `_base_suite_counts` use it when `OMRS_TRIPWIRE_JUNIT` is set, and keep the inner run when it is not set. Verify: the tests from 5.1 pass, and `uv run pytest tests/test_clean_base_tripwire.py` with no variable still passes.
- [ ] 5.3 Re-pin `_BASE_EXECUTED` for the new tests from groups 2 to 5, with a dated comment. Verify: the tripwire passes in both modes (variable set and not set).
- [ ] 5.4 Mutation check: mark one fast test `skip`, run the fast suite with a report, then run the tripwire with the report. Verify: the tripwire fails with an executed-count drift. Revert the skip.
- [ ] 5.5 Update `scripts/local_ci.sh`: the fast-suite step writes the report to a `mktemp` path, the tripwire step reads it, and the file is removed on exit. Verify: `./scripts/local_ci.sh` passes, and the tripwire step takes under 30 s.
- [ ] 5.6 Update `.github/workflows/ci.yml`: the `test` job and the base entry of the `floors` job write the report to `$RUNNER_TEMP` and pass `OMRS_TRIPWIRE_JUNIT` to the tripwire step. Extra entries of `floors` stay as they are. Verify: `actionlint` passes if installed, else review the YAML by hand; the CI run on the pull request is green.
- [ ] 5.7 Update the tripwire text in `docs/guides/testing.md`, the Quick Reference and "Parallel runs" paragraph in `CLAUDE.md`, and the tripwire docstrings. Verify: no text still says the tripwire step runs a second copy of the suite in CI or in `local_ci.sh` (`git grep -n "second copy\|inner suite"`).

## 6. Integration

- [ ] 6.1 Repeat the timing run from 1.2. Add the after numbers to `timing.md` next to the before numbers. Verify: the fast suite and the tripwire step are both faster. Report the real numbers, even if they are below the estimate in the proposal.
- [ ] 6.2 Run `./scripts/local_ci.sh` and `openspec validate speed-up-fast-test-suite --strict`. Verify: both pass.
