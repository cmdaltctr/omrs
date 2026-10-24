# Design

## Context

See proposal.md (Why) for the measurements. These facts about the current harness shape the approach:

- `_isolate_env` (autouse, `tests/conftest.py`) sets `METADATA__EXTRACTION_MODE=disabled`, `METADATA__CLASSIFY_MAX_ATTEMPTS=1` and `METADATA__CLASSIFY_TIMEOUT=5.0` in the environment. The conftest default `EffectiveSettings` also sets `extraction_mode="disabled"`.
- The `effective_settings()` factory builds `EffectiveSettings` from class defaults. Its only block default is the empty tokenizer identity. So a factory-built `MetadataBlock` has `extraction_mode="llamaindex"` and 3 attempts, and the environment values do not reach it. A direct `EffectiveSettings(...)` call has the same problem.
- Every extraction call goes through `omrs.core.metadata.extractor`, which looks up a strategy with `_metadata_get(name)`. The name is bound from `registry.get` at import time. LLM-backed strategies degrade silently on a connection error, so the slow tests still pass.
- The OCR timeout is `max(ocr_worker_request_timeout, pages × ocr_worker_seconds_per_page)` (`integrations/ocr_worker/routes.py`). The class default for `ocr_worker_seconds_per_page` is 120.
- With pytest-xdist, `--junitxml` writes one merged report. A probe run on 2026-10-24 gave 8,045 test cases and 7,897 passed in the report, which matched the run summary line. The deselected count is not in the report. Today it comes from a separate `--collect-only` run that takes about 4 s.

## Goals / Non-Goals

**Goals:**

- Remove the unplanned waits without lowering what any test checks.
- Make it hard for a new test to bring the waits back without anyone noticing.
- Keep the tripwire's executed-count and deselected-count checks as strict as they are now.

**Non-Goals:**

- No change to `src/omrs/`. The silent fallback is correct product behaviour. Only the tests should not depend on it.
- No change to `--dist loadfile` and no file splitting. When the 30 s tests are gone, the longest file (`test_ingestion_stage3.py`, 194 s now) should drop to a few seconds. Check this with the timing run in the tasks.
- No change to the tests that wait on purpose (watcher shutdown, process launcher ready-timeout).

## Decisions

### D1. Defaults go in the factory, not in each test

Add `"metadata": {"extraction_mode": "disabled", "classify_max_attempts": 1}` to `factory_block_defaults`. The merge rule stays as it is: dotted and flat overrides win over the defaults, and a whole block that the caller passes wins verbatim.

Alternatives:
- Read the factory defaults from the environment that `_isolate_env` sets. Rejected: it couples two fixtures through process state, and the run order of fixtures would matter.
- Change the class default in `MetadataBlock`. Rejected: that changes product behaviour.

Tests that build `EffectiveSettings(...)` directly and ingest move to the factory. Probe hits: `test_retrieval.py:780`, `test_ingestion.py:67`, `test_core_coverage_v2.py` (2 tests). A test that needs a bare `EffectiveSettings` for another reason passes `metadata=MetadataBlock(extraction_mode="disabled")` instead.

### D2. The guard wraps the dispatch lookup in `extractor`

An autouse fixture uses `monkeypatch.setattr` to replace `omrs.core.metadata.extractor._metadata_get` with a wrapper. For any name other than `disabled` and `keyword`, the wrapper calls `pytest.fail(...)` with the strategy name and the two fixes. The `metadata_llm` marker (registered in `pyproject.toml`) turns the guard off for that test. A module can set it with `pytestmark`.

This is the module that does the lookup, so the patch takes effect (tests/AGENTS.md rule 2). `monkeypatch` restores the original after each test.

Alternatives:
- Block outgoing network connections. Rejected: many tests run fake HTTP servers on localhost, and the failure would not name the cause.
- Seed the registry `_cache` with guard callables. Rejected: an unmarked test that patches a strategy module attribute would then see the guard and not its mock, and the error would be confusing.

One test reaches the registry cache through `ext._metadata_get.__globals__["_cache"]` (`test_coverage_gaps_v2.py:94`). A wrapper has different globals, so this test changes to patch `omrs.core.metadata.registry._cache` directly. The probe run confirmed that this test is the only one that breaks.

The marker goes on modules that test LLM strategies on purpose. Probe hits with fast run times: `test_metadata_extractor.py`, `test_metadata_store_ownership.py`, `test_metadata_degradation.py`, `unit/test_provider_config.py`, `unit/test_ollama_context_window_calls.py`, `unit/test_verification_gaps_pipeline_graphs.py` (2 cases). Mark single tests where only a few cases in a module need it. Do not mark a module only because the guard fails in it. First check whether the test meant to call an LLM strategy.

### D3. The OCR test sets the per-page timeout to zero

`_ocr_settings(..., ocr_worker_request_timeout=1.0, ocr_worker_seconds_per_page=0.0)`. Then the effective timeout is the 1 s floor. The test also asserts that the error names a 1-second wait, so the 120 s wait cannot come back unseen. The per-page rule keeps its own tests in `test_ocr_routes.py`.

### D4. The tripwire reads the fast-suite report from an environment variable

The tripwire reads `OMRS_TRIPWIRE_JUNIT`. Use an environment variable, not a pytest command-line option: an option needs a `pytest_addoption` hook in `conftest.py`, and the tripwire module is the only consumer.

- Variable set: parse the report with `xml.etree.ElementTree`. Passed = test cases with no `skipped`, `failure` or `error` child. Fail if the file is missing, if a failure or error is present, or if any `*.py` file under `src/` or `tests/` has an mtime newer than the report.
- Variable not set: run the inner suite as today.
- The deselected count always comes from the `--collect-only` run. It takes about 4 s and the report does not contain it.

The fast-suite step writes the report with `--junitxml=<path>`. `scripts/local_ci.sh` writes it to a `mktemp` path and removes the file on exit. CI writes it to `$RUNNER_TEMP`. Both export the variable to the tripwire step. A `floors` matrix entry that ignores the tripwire does not write a report.

Why the freshness check: a stale report from an earlier run could hide a test that stopped running. The check compares file times only. It costs nothing and catches the common case, a report left over from before an edit.

Alternatives:
- Remove the tripwire's inner run and keep only static checks. Rejected: the executed-count pin is what catches a test that silently stops running.
- Run the tripwire inside the main suite as a final hook. Rejected: under xdist no single worker sees the whole result. A session-finish hook on the controller could work, but it adds a plugin for one check.

## Risks / Trade-offs

- [A test depended on the factory's old `llamaindex` default and checked the fallback result] → The guard fails such a test. The author then decides between setting the mode explicitly with a mock and a marker, or accepting `disabled`. Run the full suite after D1 and before D2 to find these tests.
- [The guard rejects a legitimate future use] → The failure message names the marker, so the fix takes one line.
- [The report and the tripwire run in different environments, for example a different extra] → Both steps run in the same job and venv. The tripwire still applies its environment adjustments (fastapi, tokenizer cache, ground truth) to the pin.
- [mtime is not reliable after a fresh checkout] → In CI the report is always newer than the checkout, because the same job writes it. Locally the report is written after any edit that the run covers.
- [Measured gains are lower than expected] → The tasks include a timing run before and after. Report the real numbers.

## Migration Plan

Merge as one change. Rollback: revert the merge commit. The tripwire falls back to its own inner run when the variable is unset, so a partial revert of the CI files still gives a working pipeline.
