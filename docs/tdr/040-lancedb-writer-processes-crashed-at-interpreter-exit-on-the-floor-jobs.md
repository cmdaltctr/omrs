# TDR-040: pyarrow 25.0.0 crashes when threads start and stop, so raise the floor to 25.0.1

- **Date:** 2026-10-25
- **Status:** Accepted
- **Deciders:** Maintainer
- **Tags:** dependencies | floors | pyarrow | ci

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

The normal test jobs passed in all three runs.

The floor jobs install each direct dependency at its lowest declared version (`--resolution lowest-direct`, ADR-042). `pyproject.toml` declared `pyarrow>=25`, so the floor jobs installed pyarrow 25.0.0. The lock file has 25.0.1. pyarrow 25.0.0 has a known crash in its bundled mimalloc (apache/arrow GH-50471). The process crashes inside `mi_thread_init` when this sequence occurs:

1. A thread imports pyarrow for the first time.
2. That thread exits.
3. Another thread then makes its first Arrow allocation.

pyarrow 25.0.1 bundles mimalloc 3.4.1, which fixes the fault (Arrow 25.0.1 release notes, GH-50428).

### What we checked

- **Reproduction of the pyarrow fault.** A short script imports pyarrow on a thread that exits, then allocates on a second thread. On macOS with pyarrow 25.0.0 the script crashed with exit code 139 (SIGSEGV). With 25.0.1 it completed. With 25.0.0 and `ARROW_DEFAULT_MEMORY_POOL=system` it completed.
- **The CI crash is a different fault.** With the floor raised to 25.0.1 (PR #129, run 40224676581), the same writer crash happened in two floor jobs: "Floor resolution (chroma)" and "Floor resolution (hybrid)". Both installed pyarrow 25.0.1 and ran on `ubuntu-24.04` image `20261021.618`. So the pyarrow fault does not explain the CI crash.

The cause of the CI crash is still open. About 120 of the 200 packages that the floor jobs install differ from the lock, so a version comparison does not name one package. The writer now runs with `PYTHONFAULTHANDLER=1`, so the next crash prints each thread's Python stack in the test failure.

## Decision

Raise the pyarrow floor to 25.0.1, because 25.0.0 has a reproduced crash. The comment beside the requirement records the reason:

```toml
# 25.0.1 bundles a fixed mimalloc. 25.0.0 crashes (SIGSEGV) when a
# thread that first imported pyarrow exits and another thread then
# allocates (apache/arrow GH-50471, reproduced locally; TDR-040).
"pyarrow>=25.0.1",
```

`uv.lock` changes only the declared minimum. The locked version stays 25.0.1. No product code changed.

Turn on faulthandler for the writer process in `tests/test_sparse_cache_freshness.py`. A child process that crashes with SIGSEGV then prints its Python stack to stderr, and the test's assertion message shows that stderr.

## Consequences

### Positive

- A user who installs at the floor does not get the GH-50471 crash.
- The next writer crash on CI names the Python call that died.

### Negative

- Environments pinned to pyarrow 25.0.0 must upgrade.
- The writer crash on the floor jobs is not fixed by this record. Floor jobs can still fail at random until its cause is found.

### Neutral

- The pyarrow floor and the lock are now the same version.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Keep `pyarrow>=25` | The declared minimum would be a release with a reproduced crash. |
| Set `ARROW_DEFAULT_MEMORY_POOL=system` in the floor jobs | It hides the pyarrow fault only on CI. Users at the floor would still meet it. It did not apply to the writer crash, which also happens on 25.0.1. |
| Retry the writer tests on the floor jobs | Hides a real crash before its cause is known. |

## How to Recognise / Handle This Again

1. **Symptom:** a floor job fails with a negative return code from a child process (`-11` is SIGSEGV). The failing job changes between runs. The normal test jobs pass.
2. **Get a stack:** run the child with `PYTHONFAULTHANDLER=1` and show its stderr in the assertion.
3. **Compare packages:** download a failed and a passing floor job log with `gh run view <run> --job <job> --log`. Compare the `+ name==version` install lines with each other and with `uv.lock`.
4. **Check native crash fixes:** for packages with native code where the floor and the lock differ, read the release notes in between.
5. **Reproduce before you fix:** run a minimal script in a throwaway environment, for example `uv run --no-project --with "<package>==<floor>" python -I script.py`. Then confirm the fix on CI before you record it as the cause.

## Revisit Triggers

- The faulthandler stack from a later writer crash names the failing call. Record that cause in a new TDR.
- The pyarrow floor moves to a new major release.
- ADR-042's floor policy changes.

## References

- apache/arrow GH-50471 (crash in `mi_thread_init` on pyarrow 25.0.0) and GH-50428 (mimalloc bump)
- Apache Arrow 25.0.1 release notes (10 August 2026)
- CI runs with the writer crash: 40220165990, 40222466315, 40222490235, 40224676581
- `tests/test_sparse_cache_freshness.py` (`_run_writer_subprocess`)
- `tests/test_dependency_floors.py`
- ADR-042 (dependency floors)
- TDR-038 (a floor raise for `llama-index-llms-ollama`)
