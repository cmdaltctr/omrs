# Proposal

## Why

The fast suite takes about 3 min 40 s in parallel, and `./scripts/local_ci.sh` takes 8 to 9 min. A timed run on 2026-10-24 showed that 20 of about 7,900 tests use 610 s of the 956 s total test time. The product code is not slow. These tests wait for network calls and timeouts that they never meant to make, and the clean-base tripwire then runs the whole suite a second time.

## What Changes

- The `effective_settings()` test factory disables LLM metadata extraction by default and allows one classification attempt. This matches what `_isolate_env` already sets for the environment. Measured cost today: 19 tests in 9 files try a real LlamaIndex call and a real llama.cpp call on `localhost:8081`, then retry with back-off and fall back. This costs about 15 s per ingest and about 490 s in total.
- Tests that build `EffectiveSettings(...)` directly and then ingest use the factory instead, or disable extraction explicitly.
- A new autouse guard in `tests/conftest.py` fails any test that dispatches an LLM-backed metadata strategy (anything except `disabled` and `keyword`) unless the test carries a new `metadata_llm` marker. The test files that exercise these strategies on purpose (with mocks) get the marker. A test that forgets to disable extraction then fails loudly, so it cannot slowly fall back.
- `test_ocr_error_boundary.py::test_post_dispatch_timeout_is_a_structured_error` sets `ocr_worker_seconds_per_page=0`. Today it sets only the 1 s floor, and the per-page rule `max(floor, pages × 120 s)` makes it wait 120 s. The test also asserts the timeout that the error message names.
- The clean-base tripwire reads the passed count from a JUnit report that the fast-suite step writes. It does not run the suite again. `scripts/local_ci.sh` and the CI `test` and `floors` jobs pass the report path to the tripwire step. When no report path is given, the tripwire runs the suite itself, as it does today, so a developer can still run the file alone.
- The tripwire refuses a report that has failures or errors, and a report that is older than the newest file under `src/` or `tests/`.
- The testing guide, `CLAUDE.md` and `tests/AGENTS.md` describe the new tripwire step, the factory defaults and the marker.

Out of scope: `tests/test_watcher.py::TestShutdownTimeout::test_stop_timeout_on_hung_ingestion` (30 s) and other single tests between 5 s and 10 s. They wait on purpose for a timeout. A later change can look at them.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `internal-maintainability`: adds requirements on test settings defaults, the guard against unplanned LLM metadata calls, timeout tests that finish at their configured timeout, and a clean-base tripwire that reuses the fast-suite report.

## Impact

- Test harness only: `tests/conftest.py`, `pyproject.toml` (marker registration), `tests/test_clean_base_tripwire.py`, and the 9 test files with unplanned LLM calls plus about 7 files that need the marker.
- `tests/test_ocr_error_boundary.py`.
- `scripts/local_ci.sh` and `.github/workflows/ci.yml` (`test` job and the base entry of the `floors` job).
- Docs: `docs/guides/testing.md`, `CLAUDE.md`, `tests/AGENTS.md`.
- No change to `src/omrs/`. No new dependency: JUnit XML output is built into pytest and the standard library parses it.
- The change moves no existing test in or out of the fast suite. Only the new regression tests raise `_BASE_EXECUTED`.
- Expected result, to confirm by measurement: the fast suite drops to about 1 min, and the tripwire step drops from about 3 min to under 30 s.
