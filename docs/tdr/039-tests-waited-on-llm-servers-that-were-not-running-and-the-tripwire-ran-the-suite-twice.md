# TDR-039: Tests waited on LLM servers that were not running, and the tripwire ran the suite twice

- **Date:** 2026-10-25
- **Status:** Accepted (PR #126 merged; CI tripwire step 712 s to 20 s on Ubuntu)
- **Deciders:** Maintainer
- **Tags:** testing | ci | xdist | tripwire | metadata | ocr
- **Related:** [TDR-034](034-the-clean-base-tripwire-ran-a-serial-suite-so-run-it-in-parallel-and-stop-pinning-skips.md), OpenSpec change `openspec/changes/archive/2026-10-25-speed-up-fast-test-suite/`

## Context

The fast suite took 231 s on a 15-core Mac and 767 s on the CI Ubuntu runner.
The clean-base tripwire step took another 217 s locally and 712 s in CI. A timed
run showed that 20 tests used about 610 s of the 956 s total test time. The
product code was not slow.

### Root Cause Analysis

1. **Unplanned LLM metadata calls.** The `effective_settings()` test factory
   started from the `MetadataBlock` class defaults: `extraction_mode="llamaindex"`
   and 3 classification attempts. 19 tests that ingest through the factory
   called LlamaIndex (about 12 s of OpenAI client retries), then llama.cpp on
   `localhost:8081` 3 times with back-off. Neither server ran. Ingestion then fell
   back to non-LLM metadata with no error, so the tests passed. Each ingest cost
   about 15 s, and most of these tests ingest twice.
2. **OCR per-page allowance.** The worker timeout is
   `max(ocr_worker_request_timeout, pages × ocr_worker_seconds_per_page)`. The
   post-dispatch timeout test set the 1 s floor only. The 120 s per-page default
   won, so the test waited 120 s.
3. **Second suite run.** The tripwire ran the whole fast suite again in a
   subprocess only to count passed tests.

## Decision

1. The test factory sets `"metadata": {"extraction_mode": "disabled",
   "classify_max_attempts": 1}` in `factory_block_defaults`. A test that passes
   its own metadata block keeps it unchanged.
2. An autouse fixture `_guard_unplanned_metadata_llm` in `tests/conftest.py`
   wraps `omrs.core.metadata.extractor._metadata_get`. Any strategy other than
   `disabled` or `keyword` calls `pytest.fail` before a network call. The message
   names the strategy and both fixes. Tests that mock an LLM strategy on purpose
   carry `@pytest.mark.metadata_llm`.
3. The OCR test sets `ocr_worker_seconds_per_page=0.0` and asserts
   `"within 1.0 seconds"`.
4. The fast-suite step writes `--junitxml`. The tripwire reads the passed count
   from that file when `OMRS_TRIPWIRE_JUNIT` is set (`tests/_tripwire_report.py`).
   It refuses a missing report, a report with failures or errors, and a report
   older than any `*.py` under `src/` or `tests/`. Without the variable it runs
   the suite itself, as TDR-034 describes. The deselected count still comes from
   `--collect-only`.
5. `scripts/local_ci.sh`, the CI `test` job and the `floors` base entry pass the
   report from the fast-suite step to the tripwire step.

## Consequences

### Positive

- Mac: fast suite 231 s to 55 s, tripwire 217 s to 8 s, `local_ci.sh` 8 to 9 min
  to about 100 s.
- CI Ubuntu: fast suite 767 s to 398 s, tripwire 712 s to 20 s.
- A new test that reaches an LLM metadata strategy by accident fails in about
  0.06 s with a clear message. Before, it passed slowly.

### Negative

- Tests that need real LLM extraction must opt in with the marker.
- The report mode trusts a file. The staleness check uses modification times,
  so a file copied with an old time could hide a change.

### Neutral

- Own-run mode (no report) still takes about 63 s locally.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Keep gotcha 8a and pass `extraction_mode="disabled"` in each test | It depends on memory. New tests kept making the same mistake. |
| Change the product default to `disabled` | Product behaviour is correct. The problem is in the test settings only. |
| Lower the network timeouts in tests | Tests still wait, and the silent fallback still hides the call. |
| Merge the tripwire into the fast-suite step | The tripwire must not run inside the parallel run it counts (TDR-034). |

## How to Recognise / Handle This Again

1. Symptom: a test fails with `Unplanned LLM metadata strategy '<name>'`. Pass
   `effective_settings(extraction_mode="disabled")`, or mark the test
   `@pytest.mark.metadata_llm` if it mocks the strategy.
2. Symptom: one test takes 12 s or more. Run
   `uv run pytest -n auto -m "not slow" --durations=25`. Look for a timeout that
   another setting overrides, such as a per-page or per-item allowance.
3. Symptom: the tripwire says the report is stale. Run the fast suite again with
   `--junitxml`, then run the tripwire. Do not edit files between the two steps.
4. Symptom: "base executed count drifted". Update `_BASE_EXECUTED` and its
   comment, as TDR-034 describes.

## Revisit Triggers

- A new LLM-backed metadata strategy that is not in the registry dispatch path.
- pytest or pytest-xdist changes the JUnit format under parallel runs.
- CI starts to cache or restore files with old modification times.

## References

- `tests/conftest.py` (`factory_block_defaults`, `_guard_unplanned_metadata_llm`)
- `tests/_tripwire_report.py`, `tests/test_clean_base_tripwire.py` (`_base_suite_counts`)
- `tests/test_ocr_error_boundary.py`, `scripts/local_ci.sh`, `.github/workflows/ci.yml`
- `docs/guides/testing.md`, `tests/AGENTS.md`, `AGENTS.md` gotcha 8a
- Timings: `openspec/changes/archive/2026-10-25-speed-up-fast-test-suite/timing.md`
- PR #126
