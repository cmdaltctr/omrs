# TDR-040: pyarrow 25.0.0 crashed LanceDB writers on the floor jobs, so raise it to 25.0.1

- **Date:** 2026-10-25
- **Status:** Accepted
- **Deciders:** Maintainer
- **Tags:** dependencies | floors | pyarrow | lancedb | ci

## Context

On 2026-10-25 one "Floor resolution" job failed in each of three CI runs. Each time it was a different job:

| Run | Commit | Failed job |
|---|---|---|
| 40220165990 | PR #127 head | Floor resolution (web) |
| 40222466315 | `00576460` on v3 | Floor resolution (community-leiden) |
| 40222490235 | PR #128 head | Floor resolution (pdf-pypdfium2) |

Each failure was in `tests/test_sparse_cache_freshness.py`. The test starts a writer process that writes to a LanceDB table. The writer died with signal 11 (SIGSEGV) and wrote nothing to stderr:

```text
AssertionError: Writer subprocess phase 'upsert' failed:
assert -11 == 0
```

The normal test jobs passed in all three runs. A re-run of the failed job in run 40220165990 passed.

### Root Cause Analysis

The floor jobs install each direct dependency at its lowest declared version (`--resolution lowest-direct`, ADR-042). `pyproject.toml` declared `pyarrow>=25`, so the floor jobs installed pyarrow 25.0.0. The lock file has 25.0.1, so the normal test jobs used 25.0.1. All other packages had the same versions in the floor jobs and the lock.

pyarrow 25.0.0 bundles a mimalloc release with a fault (apache/arrow GH-50471). The process crashes inside `mi_thread_init` when this sequence occurs:

1. A thread imports pyarrow for the first time.
2. That thread exits.
3. Another thread then makes its first Arrow allocation.

LanceDB writes from worker threads, so a writer process can meet this sequence. pyarrow 25.0.1 bundles mimalloc 3.4.1, which fixes the fault (Arrow 25.0.1 release notes, GH-50428).

We checked the cause in three ways:

- **Packages.** The failed floor job in run 40222490235 installed the same 200 package versions as the passing floor job in run 40142057528 from the day before. The runner image was the same (`ubuntu-24.04`, `20261021.618`).
- **Test count.** The failing job ran 6,963 tests. The passing job ran 6,619. The merged experiment changes added test files. With `-n auto --dist loadfile`, other test files then share a worker with the freshness test and run at other times. The crash is timing-dependent, so it showed only after this change.
- **Reproduction.** A short script imports pyarrow on a thread that exits, then allocates on a second thread. On macOS with pyarrow 25.0.0 the script crashed with exit code 139 (SIGSEGV). With 25.0.1 it completed. With 25.0.0 and `ARROW_DEFAULT_MEMORY_POOL=system` it completed.

## Decision

Raise the floor to the first release with the fixed mimalloc. The comment beside the requirement records the reason:

```toml
# 25.0.1 bundles a fixed mimalloc. 25.0.0 can crash (SIGSEGV) when a
# thread that first imported pyarrow exits and another thread then
# allocates (apache/arrow GH-50471); LanceDB writers hit it on the
# floors CI jobs (run 40222490235, TDR-040).
"pyarrow>=25.0.1",
```

`uv.lock` changes only the declared minimum. The locked version stays 25.0.1. No code changed.

## Consequences

### Positive

- The floor jobs use the same allocator fix as the lock. The random LanceDB writer crash stops.
- A user who installs at the floor does not get the crash in ingestion or in the watcher.

### Negative

- Environments pinned to pyarrow 25.0.0 must upgrade.

### Neutral

- The floor and the lock are now the same version.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Re-run failed floor jobs until they pass | The crash stays. It fails a random floor job on later pull requests. |
| Set `ARROW_DEFAULT_MEMORY_POOL=system` in the floor jobs | The declared minimum would still be a release that crashes. Users at the floor would still meet the fault. |
| Skip `test_sparse_cache_freshness.py` on the floor jobs | Hides a real crash. Any LanceDB write at the floor can meet it. |

## How to Recognise / Handle This Again

1. **Symptom:** a floor job fails with a negative return code from a child process (`-11` is SIGSEGV), and the child's stderr is empty. The failing job changes between runs. The normal test jobs pass.
2. **Compare packages:** download the failed and a passing floor job log with `gh run view <run> --job <job> --log`. Compare the `+ name==version` install lines. Compare each floor version with `uv.lock`.
3. **Check the release notes:** for each package where the floor and the lock differ, read the notes of the releases in between. Look for crash fixes in native code.
4. **Reproduce:** run a minimal script in a throwaway environment, for example `uv run --no-project --with "<package>==<floor>" python -I script.py`. Then run it with the next release.
5. **Fix:** raise the floor in `pyproject.toml` with a comment that names the reason and the CI run. Run `uv lock`. Check `uv run pytest tests/test_dependency_floors.py`.

## Revisit Triggers

- The pyarrow floor moves to a new major release.
- `lancedb` or `pylance` changes its pyarrow requirement.
- ADR-042's floor policy changes.

## References

- apache/arrow GH-50471 (crash in `mi_thread_init` on pyarrow 25.0.0) and GH-50428 (mimalloc bump)
- Apache Arrow 25.0.1 release notes (10 August 2026)
- Failed CI runs: 40220165990, 40222466315, 40222490235
- `tests/test_sparse_cache_freshness.py` (`_run_writer_subprocess`)
- `tests/test_dependency_floors.py`
- ADR-042 (dependency floors)
- TDR-038 (the same kind of fix for `llama-index-llms-ollama`)
