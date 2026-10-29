# Proposal: Trim CI to the jobs that each catch something unique

## Why

A normal pull request starts 23 GitHub Actions jobs: 22 run and `Retrieval quality (Tier 2)` shows as skipped (run 40874653858). Several of them repeat work that another job already does:

- `Floor resolution (llamacpp)` and `Floor resolution (openrouter)` install empty extras (`pyproject.toml`: `llamacpp = []`, `openrouter = []`). Each one installs the same packages as the base `Floor resolution` job and runs the same fast suite for about 6 minutes.
- `Chroma extra tests` (11 to 16 minutes) runs the fast suite with `chroma` and `hybrid`. `Coverage (Codecov)` already installs both extras and runs the same suite. The only check unique to the Chroma job is the one that fails when a test skips with the "chroma extra not installed" reason.
- The 7 other floor jobs re-run the fast suite at the lowest declared versions of one extra each, on every push. The floors of an extra change only when `pyproject.toml` or `uv.lock` changes. The two floor incidents on record did not need the per-extra entries. In TDR-038 the fault was in a base dependency, so the base entry failed too. In TDR-040 one or two random entries crashed per run because of a LanceDB exit bug. The base entry was among them in two runs, and the reruns caught nothing new.
- `Leiden extra` runs on four Python versions. The Leiden packages ship abi3 wheels, so the lowest and the highest supported versions cover the range.
- `Coverage (Codecov)` is the slowest job (20 to 27 minutes) because it still runs the suite serially. The other suite jobs went parallel in PR #120.

Fewer, shorter jobs give quicker pull-request feedback and fewer random reruns.

## What Changes

1. **Remove the two empty-extra floor entries.** Delete `llamacpp` and `openrouter` from the `floors` matrix.
2. **Fold the Chroma job into Coverage.** Delete the `chroma-extra` job. The Coverage job reads its own JUnit report and fails when any test skipped with the "chroma extra not installed" reason. The `chroma` entry of the floors matrix gets the same check, so Chroma at its floors keeps a no-skip guard.
3. **Run the extra floor entries only when needed.** A new small job decides the floors matrix. On a pull request that does not change `pyproject.toml`, `uv.lock` or `.github/workflows/ci.yml`, the matrix holds only the base entry. On any other pull request, on every push to an integration branch, on the nightly schedule and on a manual run, the matrix holds the base entry and all 7 extras. The base entry, with its clean-base tripwire and its Leiden-free check, keeps running on every pull request. GitHub runs the schedule only from the workflow file on the default branch, `main`. That file has no `schedule` trigger today, so the nightly floors run starts only when this workflow reaches `main`.
4. **Run Leiden on Python 3.11 and 3.14 only.** These are the lowest and the highest supported versions.
5. **Run Coverage in parallel.** Add `-n auto --maxprocesses=8` to the Coverage job, after checking that the parallel total matches the serial total.

Documentation follows the change: a new ADR (ADR-107) records the decision; ADR-042 and TDR-033 get dated addenda; `AGENTS.md`, `tests/AGENTS.md`, `src/omrs/core/vectordb/AGENTS.md`, `docs/guides/testing.md` and the `scripts/local_ci.sh` header name the new jobs. Test skip reasons and comments that point to "the chroma-extra CI job" will point to the Coverage job instead.

A normal pull request then starts 12 GitHub jobs instead of 23 (11 run, Tier 2 shows as skipped). A pull request that changes dependencies or the workflow starts 19.

No product code changes. No change is **BREAKING**.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `dependency-floor-integrity`: the floors requirement now says which floor entries run on which events. The Chroma requirement names the Coverage job as the separate complete job that runs every Chroma-gated case, and it adds the no-skip check to the Chroma floor entry.
- `retrieval-quality-regression-gate`: the nightly-schedule scenario lets the floors job run on the schedule. Today it says floors jobs do not run because of the schedule.

## Impact

- `.github/workflows/ci.yml`: the `floors`, `community-leiden-extra` and `codecov` jobs change, a new floors-scope job is added, and the `chroma-extra` job is removed.
- Test files that name "the chroma-extra CI job" in a skip reason or comment: only the text changes. The tripwire's static check looks for the "chroma extra not installed" substring, which stays, and the pinned counts do not change.
- Documentation: a new ADR-107 (decision; `add-model-search-and-download` already claims ADR-106), addenda to ADR-042 and TDR-033, `docs/adr/ADR_README.md`, `AGENTS.md`, `tests/AGENTS.md`, `src/omrs/core/vectordb/AGENTS.md`, `docs/guides/testing.md`, `scripts/local_ci.sh` (header comment only).
- Branch protection: `main` and `v3` have no required status checks, so the job renames and removals block nothing.
- Trade-off: a code change that breaks the floors of an optional extra, without any change to dependency files, shows up on the push after merge, not on the pull request. Design D3 records why this is acceptable.
