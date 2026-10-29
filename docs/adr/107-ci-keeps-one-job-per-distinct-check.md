# ADR-107: CI Keeps One Job per Distinct Check

- **Date:** 2026-10-29
- **Status:** Proposed
- **Deciders:** Maintainer
- **Amends:** [ADR-042](042-dependency-floor-integrity.md) (which floor entries run on which events)
- **Related:** [TDR-033](../tdr/033-the-collection-name-was-the-only-project-title-so-add-an-editable-display-name.md) (Chroma round trip), [TDR-038](../tdr/038-the-ollama-floor-took-only-true-or-false-for-thinking-so-raise-it-to-0-9-1.md) and [TDR-040](../tdr/040-lancedb-writer-processes-crashed-at-interpreter-exit-on-the-floor-jobs.md) (floor incidents)
- **Change:** `openspec/changes/trim-ci-jobs/`

## Context

A normal pull request started 23 GitHub Actions jobs (run 40874653858). Several repeated work that another job already did:

- The `llamacpp` and `openrouter` floor entries install empty extras. ADR-083 moved their packages into the base install. Each entry ran the same install and suite as the base entry for about 6 minutes.
- `Chroma extra tests` (11 to 16 minutes) ran the fast suite with `chroma` and `hybrid`. `Coverage (Codecov)` installs both extras and runs the same suite. Only the check for "chroma extra not installed" skips was unique to it.
- The 7 other floor entries ran on every push, but the floors of an extra change only with `pyproject.toml` or `uv.lock`. In TDR-038 the base entry failed too. In TDR-040 random entries crashed from a LanceDB exit bug, and the reruns found nothing new.
- `Leiden extra` ran on 4 Python versions. Its packages ship abi3 wheels.
- `Coverage (Codecov)` took 20 to 27 minutes because it ran serially.

`main` and `v3` have no required status checks, so a renamed or removed job blocks nothing.

## Decision

Each CI job must catch a fault that no other job catches on the same event.

1. **No floor entry for an extra that adds nothing beyond the base.** Remove `llamacpp` and `openrouter`. `pdf-inspector` also has no entry, because it repeats a base dependency at the same floor. A new extra that adds packages gets a floor entry in the same pull request, in the `floors-scope` list.
2. **Coverage runs the Chroma cases.** Delete the `chroma-extra` job. The Coverage job and the `chroma` floor entry read their JUnit report and fail when a test skips with the "chroma extra not installed" reason. The report keeps every skip reason under xdist, the console output does not.
3. **A `Floor matrix scope` job builds the floors matrix.** A pull request that changes none of `pyproject.toml`, `uv.lock` and `.github/workflows/ci.yml` gets the base entry only. Pushes, the nightly schedule, manual runs and every other pull request get the base entry and every extra. The diff is three-dot (`base...head`), so commits that land on the base branch after the fork do not count. A git error or empty pull-request SHAs keep the full list. The floors job now also runs on the schedule.
4. **Leiden runs on Python 3.11 and 3.14,** the lowest and the highest supported versions.
5. **Coverage runs in parallel** with `-n auto --maxprocesses=8`. `--dist loadfile` comes from `pyproject.toml`, and pytest-cov combines the worker data.

A normal pull request now starts 12 jobs (11 run, Tier 2 shows as skipped). A pull request that changes a dependency file or `ci.yml` starts 19.

## Consequences

### Positive

- Quicker pull-request feedback and fewer runners per push.
- Fewer random reruns from floor jobs that repeat the base entry.
- The base floor entry, the clean-base tripwire and the Leiden-free check still run on every pull request.

### Negative

- A code change that breaks the floors of an optional extra, with no change to a dependency file, shows only on the push after merge. The fix lands in a follow-up pull request. Floors matter to users who install without the lockfile. `release.yml` runs on every push to `main` and does not wait for CI. Every push to `v3` runs every extra, so do not merge `v3` into `main` while a `v3` floor entry is red.
- No nightly floor check runs yet. GitHub runs `schedule` only from the workflow file on the default branch, and the `ci.yml` on `main` has no `schedule` trigger. The nightly run starts when this workflow reaches `main`, and then it checks `main`, not `v3`. Pushes to `v3` run every extra in the meantime. The Maintainer accepted this gap.
- Python 3.13 loses its Leiden run. abi3 wheels make a break there unlikely.

### Neutral

- The Chroma-only coverage slice that the old Chroma job printed is gone. The Coverage upload still counts the Chroma adapter.
- Skip reasons in the tests now name the Coverage CI job. The "chroma extra not installed" prefix and the tripwire pins did not change.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Keep the empty-extra entries as a guard | The spec now says an extra that adds packages gets an entry, in the same pull request that fills it. |
| Keep the Chroma job and drop Chroma from Coverage | Coverage is the only upload, so the Chroma adapter must count there for patch coverage. |
| A workflow-level `paths:` filter in a separate `floors.yml` | The base entry must still run on every pull request, so it would need a copy in `ci.yml`, and the files would drift. |
| A job-level `if:` on the floors job | GitHub evaluates a job `if:` before it expands the matrix, so it cannot read `matrix.extra`. Step-level skips still start 7 runners. |
| One combined "all extras at floors" entry | A combined resolution can lift one extra's direct dependency above its floor, so it does not test each floor. |

## Verification

- `actionlint` passes on `ci.yml`.
- The skip check exits 1 on a report from a base install of four Chroma-gated files (65 skips), and 0 on a report from an install with `chroma` and `hybrid`.
- The scope script printed the expected list for each event: pull request with and without a change to each of the three files, a base branch that gained a `pyproject.toml` change after the fork (`[""]`), push, schedule, dispatch, a git error and empty SHAs.
- First pull request run: see the pull request for this change.
- Base-only row in GitHub: checked on the first ordinary pull request after merge (to be recorded here).

## References

- `.github/workflows/ci.yml` (jobs `floors-scope`, `floors`, `community-leiden-extra`, `codecov`)
- `openspec/changes/trim-ci-jobs/` (design D1 to D6)
- `docs/guides/testing.md` ("What CI runs")
- `tests/test_clean_base_tripwire.py` (static Chroma-guard check)
