# TDR-040: LanceDB writer processes crashed at interpreter exit on the floor jobs

- **Date:** 2026-10-25
- **Status:** Accepted
- **Deciders:** Maintainer
- **Tags:** lancedb | dependencies | floors | pyarrow | ci

## Context

On 2026-10-25 one "Floor resolution" job failed in each of five CI runs. Each time it was a different job:

| Run | Commit | Failed job |
|---|---|---|
| 40220165990 | PR #127 head | Floor resolution (web) |
| 40222466315 | `00576460` on v3 | Floor resolution (community-leiden) |
| 40222490235 | PR #128 head | Floor resolution (pdf-pypdfium2) |
| 40224676581 | PR #129 head | Floor resolution (chroma), Floor resolution (hybrid) |
| 40227051654, 40228699510 | PR #129 head | Floor resolution, Floor resolution (hybrid) |

Each failure was in `tests/test_sparse_cache_freshness.py`. The test starts a short-lived writer process. The writer opens a LanceDB table, writes rows and exits. It died with signal 11 (SIGSEGV):

```text
AssertionError: Writer subprocess phase 'upsert' failed:
assert -11 == 0
```

The normal test jobs passed in every run.

### Root Cause Analysis

We added two diagnostics to the writer:

1. `PYTHONFAULTHANDLER=1`. Run 40227051654 printed `Fatal Python error: Segmentation fault` with no Python frame on any thread. The crash came from a native thread.
2. A line `writer phase finished` after the write. Run 40228699510 showed this line in stdout, then the segmentation fault. The write had finished. The process crashed during interpreter shutdown.

lancedb runs a shared Tokio runtime with its own worker threads. Before lancedb 0.40.0 nothing stops these threads at exit. If a worker thread is busy when `Py_Finalize` tears down interpreter state, it can touch state that is already gone, and the process crashes. lancedb PR #4175 (merged 15 September 2026) shuts the runtime down from an `atexit` callback. The first release that contains it is lancedb 0.40.0; 0.39.0 and earlier do not (checked against the release tags). lance issue #4152 describes the same pattern and gives `os._exit(0)` after the work as the workaround for scripts.

The project declares `lancedb>=0.37` and locks 0.37.1, so both the floor jobs and the normal jobs use 0.37.1. The crash depends on timing. The floor jobs resolve other dependencies to newer releases, and the merged experiment changes added test files. With `-n auto --dist loadfile` that changed which files run on a worker at the same time. We did not reproduce the crash on macOS: 40 runs of the writer tests and 3 runs of the full fast suite at the floors passed.

### A first wrong cause: pyarrow 25.0.0

Only pyarrow differed between the floor install (25.0.0) and the lock (25.0.1) among the LanceDB packages. pyarrow 25.0.0 has a known crash in its bundled mimalloc (apache/arrow GH-50471): the process crashes in `mi_thread_init` when a thread that first imported pyarrow exits and another thread then allocates. pyarrow 25.0.1 bundles mimalloc 3.4.1, which fixes it. A short script reproduced this crash on macOS: exit code 139 on pyarrow 25.0.0, and a clean exit on 25.0.1.

We raised the pyarrow floor to 25.0.1. The writer crash still happened with pyarrow 25.0.1 (run 40224676581). So the pyarrow fault was real but was not the cause of this crash.

## Decision

1. **Test child processes that write to LanceDB skip interpreter finalisation.** One helper, `tests/_lance_child.py` (`run_lance_child`), runs them. It appends a step to the child script: print `lance child finished`, flush stderr and call `os._exit(0)`. The step runs only when the script body has finished, so a child that fails earlier still exits non-zero and the test still fails. Three tests use it: `test_sparse_cache_freshness.py`, `test_lance_dataset_epoch.py` and `test_bm25_validity_token.py`. All three write from a child process. The epoch test had the same crash on 2026-10-19 (run 39231091643, PR #120, the change that made the floor jobs run tests in parallel). A re-run passed, and it was taken for a one-off. `tests/test_lance_child_helper.py` checks the helper. One case runs a child that crashes in an `atexit` handler: it fails without the helper and passes with it.
2. **The helper runs each child with `PYTHONFAULTHANDLER=1`, and its assertion shows stdout and stderr.** A later crash then shows whether it happened before or after the work, and on which thread.
3. **The pyarrow floor is 25.0.1**, because 25.0.0 has a reproduced crash:

   ```toml
   # 25.0.1 bundles a fixed mimalloc. 25.0.0 crashes (SIGSEGV) when a
   # thread that first imported pyarrow exits and another thread then
   # allocates (apache/arrow GH-50471, reproduced locally; TDR-040).
   "pyarrow>=25.0.1",
   ```

4. **The real fix is lancedb 0.40.0, in its own OpenSpec change.** The upgrade changes how `lancedb.expr.lit` writes some filter values, and the filter safety check in `core/vectordb/lancedb/literal.py` refuses the new forms:

   | Value | lancedb 0.37.1 | lancedb 0.40.0 |
   |---|---|---|
   | `float("inf")`, `-inf`, `nan` | `inf`, `-inf`, `NaN` | `arrow_cast('inf', 'Float64')` and so on |
   | `Decimal("3.14")` | `3.14` | `arrow_cast('3.14', 'Decimal128(3, 2)')` |
   | naive `datetime` | converted to UTC | kept as written |

   The naive `datetime` change can change which rows a filter matches. It needs a decision, so it does not belong in a CI fix.

## Consequences

### Positive

- The floor jobs no longer fail at random on this test.
- A later writer crash shows where it happened.
- A user who installs at the pyarrow floor does not get the GH-50471 crash.

### Negative

- Production processes still use lancedb 0.37.1. A short CLI run such as `omrs ingest` can crash at exit after a successful write until the lancedb upgrade lands. The write is not lost, but the exit code is wrong.
- The tests no longer cover interpreter shutdown of a LanceDB child process.

### Neutral

- The pyarrow floor and the lock are now the same version.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Upgrade to lancedb 0.40.0 in this fix | It changes filter literal forms, and the naive `datetime` change needs a decision. It gets its own OpenSpec change. |
| Retry the writer tests on the floor jobs | Hides the crash. A retry also passes a crash that happens before the write. |
| Set `ARROW_DEFAULT_MEMORY_POOL=system` in the floor jobs | It addresses the pyarrow fault, which is not the cause. |
| Skip `test_sparse_cache_freshness.py` on the floor jobs | Loses the cross-process freshness checks on the floors. |

## How to Recognise / Handle This Again

1. **Symptom:** a child process that uses lancedb exits with `-11` (SIGSEGV) or `-6` (SIGABRT). Its stderr is empty. The failing CI job changes between runs.
2. **Get the stack:** run the child with `PYTHONFAULTHANDLER=1` and show its stderr. No Python frame on any thread means a native thread crashed.
3. **Find the moment:** print a marker after the work and show stdout. A marker followed by the crash means the crash happened at interpreter shutdown.
4. **Check lancedb:** before 0.40.0 its Tokio runtime is not shut down at exit. In a short-lived script, end with `sys.stdout.flush()`, `sys.stderr.flush()` and `os._exit(0)` after the work commits, or use lancedb 0.40.0 or later.
5. **Confirm before you record a cause:** a fix that is not confirmed on CI is a guess. The pyarrow floor raise in this record looked right and was wrong for this crash.

## Revisit Triggers

- The lancedb 0.40 upgrade lands. Then remove the `os._exit(0)` step from `tests/_lance_child.py` and check that the floor jobs stay green.
- A writer crash happens before the `writer phase finished` line.
- ADR-042's floor policy changes.

## References

- lancedb PR #4175 (shut down the shared Tokio runtime on interpreter exit; first released in lancedb 0.40.0)
- lance issue #4152 (Tokio task wakes during shutdown; `os._exit(0)` workaround)
- apache/arrow GH-50471 and GH-50428 (pyarrow 25.0.0 mimalloc crash; fixed in 25.0.1)
- CI runs: 40220165990, 40222466315, 40222490235, 40224676581, 40227051654, 40228699510
- `tests/_lance_child.py` (`run_lance_child`) and `tests/test_lance_child_helper.py`
- `tests/test_sparse_cache_freshness.py`, `tests/test_lance_dataset_epoch.py`, `tests/test_bm25_validity_token.py`
- `src/omrs/core/vectordb/lancedb/literal.py` (`_is_faithful_literal`)
- ADR-042 (dependency floors), ADR-046 (LanceDB backend)
- TDR-038 (a floor raise for `llama-index-llms-ollama`)
