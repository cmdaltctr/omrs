# Testing

## Running tests

```bash
# The fast suite. Run this routinely.
uv run pytest -m "not slow" -v

# With coverage
uv run pytest -m "not slow" --cov=omrs --cov-report=term-missing

# The slow end-to-end test (starts a real server over stdio)
uv run pytest -m slow -v

# One file
uv run pytest tests/test_reranker.py -v
```

### Run in parallel

```bash
# Quick feedback. Skips the tripwire (see below).
uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q
```

On a 15-core Mac this takes about 1 minute. The project sets `--dist loadfile`, so each
test file stays on one worker, in file order. Do not override it with
`--dist load`: some tests depend on logging state set up by an earlier test in
the same file, and they fail when xdist splits a file across workers.

The clean-base tripwire (`tests/test_clean_base_tripwire.py`) pins the exact
passed count and the deselected count of the fast suite. It gets the passed
count in one of two ways:

1. **From a report.** Set `OMRS_TRIPWIRE_JUNIT` to the JUnit report of a
   fast-suite run in the same environment. The tripwire reads the count and
   does not run the suite again. It takes a few seconds.
2. **From its own run.** With no variable, the tripwire runs the fast suite in
   a subprocess, in parallel when pytest-xdist is installed.

The tripwire refuses a report that records a failure or an error, a missing
report, and a report older than any `*.py` file under `src/` or `tests/`.

```bash
uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q --junitxml=/tmp/fast.xml
OMRS_TRIPWIRE_JUNIT=/tmp/fast.xml uv run pytest tests/test_clean_base_tripwire.py -q
```

The deselected count always comes from a collection-only run, because the
report does not hold it. The skipped count is not pinned, because a parallel
run reports one fewer skip than a serial run. The static Chroma file checks
stay.

Before you push, run `./scripts/local_ci.sh`. It runs the main suite in
parallel and writes the report. Then it runs the tripwire on that report, then
the frontend gates. The CI `test` job and the base entry of the `floors` job
do the same.

The fast suite also runs in series, without `-n`, but more slowly. It uses mock embeddings and an
in-memory database, so it needs no Ollama, no llama.cpp, no network, and
downloads nothing.

There is also an architecture check that is not part of pytest:

```bash
uv run lint-imports
```

That verifies the module boundaries. It must pass before you commit.

### What CI runs

All jobs live in `.github/workflows/ci.yml`. Each job checks something that no other job checks on the same event (ADR-107).

| Job | What only this job checks | When it runs |
|-----|---------------------------|--------------|
| `test (ubuntu-latest)`, `test (macos-latest)` | The fast suite on the base install with the `web` extra, the clean-base tripwire, the torch-free install, import-linter, the OpenAPI contract. The macOS entry also runs the slow suite with LiteParse. | Push, pull request, manual run |
| `Retrieval quality (Tier 1)` | The deterministic retrieval-quality gate. | Push, pull request |
| `Retrieval quality (Tier 2)` | The retrieval-quality gate with a real Ollama model. | Nightly schedule, manual run |
| `Floor matrix scope` | Decides which `Floor resolution` entries run. | Every event |
| `Floor resolution` (base entry) | The fast suite, the clean-base tripwire and the Leiden-free check at the lowest declared versions of the base install. | Every event |
| `Floor resolution (<extra>)` | The fast suite at the lowest declared versions of one optional extra. The `chroma` entry fails when a test skips for a missing chroma extra. | Push, nightly, manual run, and a pull request that changes `pyproject.toml`, `uv.lock` or `ci.yml` |
| `Leiden extra (Python 3.11)`, `Leiden extra (Python 3.14)` | The community strategy contracts with the `community-leiden` extra. | Push, pull request, manual run |
| `Torch backend tests` | The torch backend and the cross-backend contract tests. | Push, pull request, manual run |
| `Frontend (web)` | The frontend lint, typecheck, unit tests and build. | Push, pull request, manual run |
| `Lint (Ruff)` | Ruff check and format. Pyright is advisory. | Push, pull request, manual run |
| `Coverage (Codecov)` | The fast suite with most extras, in parallel, and the coverage upload. It fails when a test skips for a missing chroma extra, so it runs every Chroma-gated case. | Push, pull request, manual run |

GitHub runs the nightly schedule and the manual run only from the workflow file on `main`. They start when this workflow reaches `main`.

---

## The one thing to know: inject, don't patch

This is the biggest change from older versions of this codebase, and knowing it
will save you an afternoon.

**There is no settings singleton.** You cannot patch `config.settings`, because
it does not exist. Core functions receive a frozen `EffectiveSettings` object as
an argument.

So instead of patching a global, build settings and pass them in:

```python
def test_top_k_is_honoured(effective_settings):
    settings = effective_settings(top_k=20)
    results = search("query", effective_settings=settings)
    assert len(results) <= 20
```

`effective_settings` is a factory fixture in `conftest.py`. It accepts flat or
dotted names:

```python
effective_settings(top_k=20)  # routed to retrieval.top_k
effective_settings(**{"retrieval.top_k": 20})  # the same thing
effective_settings(chroma_persist_dir="/tmp/x")  # a top-level field
```

An unknown name raises `TypeError` rather than being ignored. That is
deliberate: silently dropped overrides were making tests pass for the wrong
reason.

### When the code reads the default instead

Some code reads the composition root's default rather than taking a parameter —
the vector store, the PDF factory, the Magika wrapper. For those, install a
default:

```python
from omrs.core.settings import EffectiveSettings, set_default_effective_settings

set_default_effective_settings(EffectiveSettings(chroma_scan_page_size=1))
```

`conftest.py` installs one before every test and clears it afterwards, so
nothing leaks between tests.

---

## Patch the module that owns the function

If a function moved, its patch target moved too. Patching the module that
re-exports it does nothing at all.

| Function                                             | Lives in                       |
| ---------------------------------------------------- | ------------------------------ |
| `_is_magika_available`                               | `omrs.integrations.magika`  |
| `_get_git_commit_hash`, `_load_cache`, `_save_cache` | `omrs.core.codebase.cache`  |
| `format_codebase_map`                                | `omrs.core.codebase.format` |
| `Observer`                                           | `omrs.daemon.runner`        |
| `search`, `_list_documents`                          | `omrs.transports.mcp`       |

---

## Gotchas

**Reset the reranker model cache.** Tests touching the reranker must call
`reset_model_cache()` in setup and teardown. The model is cached process-wide,
so a leftover instance leaks into the next test.

**Pin the PDF reader.** Tests need `pdf_reader="pypdf"`. The packaged default
is `pdf_inspector`, and `auto` probes for LiteParse. Each reader emits
different document boundaries, so only `pypdf` keeps tests deterministic. The
conftest default already sets this.

**Metadata extraction is off in tests.** The conftest default and the
`effective_settings` factory both set `extraction_mode="disabled"`. The factory
also sets `classify_max_attempts=1`. The real default is `llamaindex`. It would
make every ingestion test call a live LLM, retry, and then fall back without a
sign, at a cost of about 15 s for each ingest.

To test a strategy, pass it: `effective_settings(**{"metadata.extraction_mode":
"keyword"})`, or a whole `metadata=MetadataBlock(...)`. The factory keeps a
whole block as given.

**LLM metadata calls need the `metadata_llm` marker.** An autouse guard in
`conftest.py` fails any test that dispatches a metadata strategy other than
`disabled` or `keyword`. The failure names the strategy and happens before any
network call. Use the marker only for a test that calls an LLM strategy on
purpose, with the LLM mocked:

```python
@pytest.mark.metadata_llm
async def test_ollama_reply_is_parsed(...): ...
```

Use `pytestmark = pytest.mark.metadata_llm` when most tests in a module need
it. If the guard fails a test that does not mean to call an LLM, fix its
settings. Do not add the marker.

**Database state can leak.** The conftest fixture clears collections between
tests. Build your own client and bypass it, and the cleanup is yours.

**Do not write timing assertions.** `assert elapsed < 0.5` measures how busy the
machine is, not whether the code is correct. Assert the property instead — for
instance, that a concurrent search finishes _while an ingest is still
deliberately paused on an Event_. If the loop were blocked it could not finish
at all. See `tests/test_async_ingest_responsiveness.py`, where converting the
stopwatch assertions exposed two tests that had been passing while measuring
nothing.

---

## Coverage floors

Enforced per tier, not as one flat number.

| Tier          | Floor | What it covers                                                                                                                                           |
| ------------- | ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Core + MCP    | 95%   | `core/ingestion`, `core/retrieval`, `core/metadata`, `core/chunking`, `core/vectordb`, `core/profiles`, `core/settings.py`, `config/`, `transports/mcp/` |
| Orchestration | 85%   | `daemon/`, `transports/cli/`                                                                                                                             |
| Overall       | 90%   | everything                                                                                                                                               |

```bash
uv run pytest -m "not slow" --cov=omrs
```

Nothing is excluded. The old exclusion list covered compatibility shims, which
no longer exist.

---

## Tests that guard the architecture

These fail when a structural rule is broken. If one fails, the fix is usually in
the source, not the test.

| Test                                       | What it catches                                                                  |
| ------------------------------------------ | -------------------------------------------------------------------------------- |
| `test_no_global_settings_reads.py`         | A `core/` module importing the settings singleton                                |
| `test_file_size_ceiling.py`                | Any file over 500 lines                                                          |
| `test_no_module_level_strategy_imports.py` | A dispatcher importing a strategy directly instead of going through the registry |
| `test_registry_contract.py`                | A registry that eagerly imports its strategies, or a broken import string        |
| `test_contract_coverage.py`                | A package covered by no import-linter contract                                   |
| `test_config_no_legacy_surface.py`         | The v1 config surface creeping back                                              |

One more that surprises people: `lint-imports` fails when a _suppression_
becomes unnecessary. Fix a boundary violation, forget to delete its exception,
and the build tells you. That is how every temporary exception from the v2 work
got removed. See [ADR-037](../adr/037-architecture-v2-conformance.md).

---

## Cloud storage tests

Three test files cover the cloud backend and experiment storage. All run in
the fast suite.

- `tests/test_chroma_cloud.py` — mode and credential validation, the
  factory's constructor arguments, secret redaction, embedding-identity
  enforcement, local/cloud parity, and the chromadb import boundary.
- `tests/test_chroma_cloud_smoke.py` — fake cloud-operation failures that
  verify the manual smoke script redacts secrets from operation and cleanup logs.
- `tests/test_experiment_storage.py` — deterministic collection naming,
  the experiment storage config, and a runner migration guard that scans
  the six calibration harnesses for direct chromadb usage.

All cloud tests use fakes. No test contacts Chroma Cloud. The opt-in smoke
check (`scripts/chroma_cloud_smoke.py`) is manual-only and never runs in CI.

---

## Writing a new test

- Put it in `tests/`, named `test_*.py`.
- Use the `effective_settings` fixture rather than patching anything.
- Mark it `@pytest.mark.slow` if it needs a real model, a network call, or more
  than a second or two.
- Async tests need no decorator; `asyncio_mode` is set in `pyproject.toml`.

Before committing:

```bash
uv run pytest -m "not slow" --cov=omrs
uv run lint-imports
```
