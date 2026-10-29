# Design: Trim CI to the jobs that each catch something unique

## Context

See proposal.md (Why) for the motivation. The facts that shape the design:

- All jobs live in one workflow, `.github/workflows/ci.yml`. It runs on `push` to `main`, `v3`, `v4` and `integration/core-web`, on `pull_request` to those branches, on `workflow_dispatch`, and on a nightly `schedule` (`23 3 * * *`). Today every job except `Retrieval quality (Tier 2)` skips the schedule event.
- GitHub runs a `schedule` workflow only from the workflow file on the default branch, which is `main`. The `ci.yml` on `main` (last changed 2026-08-28) has only `push` and `pull_request` triggers, so no nightly run happens today. The run history shows no `schedule` or `workflow_dispatch` runs. The nightly run starts when this workflow reaches `main`, and it then checks `main`, not `v3`. A manual run has the same limit: GitHub offers `workflow_dispatch` only for a workflow file on the default branch, and `main`'s file does not declare it.
- `main` and `v3` have no branch protection and no required checks. A renamed or removed job blocks nothing.
- The last four green pull-request runs took: Coverage 20 to 27 min, Chroma extra 11 to 16 min, test (ubuntu) 9 to 10 min, test (macos) 5 to 10 min, each floor entry 5 to 9 min, Frontend 5 min, the rest 1 min or less.
- `pyproject.toml` declares `llamacpp = []` and `openrouter = []`. Their packages moved into the base install (ADR-083).
- The JUnit report of a parallel run (`pytest -n`) keeps each skip reason in `<skipped message="...">`, including module-level `importorskip` skips. A local run of four Chroma-gated files without the extra gave 65 skips in the report, each with the "chroma extra not installed" reason. A check on the report therefore works under xdist. Reading the console output does not work reliably (the tripwire docstring records that `importorskip` output differs between invocation contexts).
- The clean-base tripwire pins executed and deselected counts. Its static guard looks for the substring "chroma extra not installed" in the Chroma-gated test files. Skip-reason text after that substring is free to change.

## Goals / Non-Goals

**Goals:**

- Each remaining job catches a fault that no other job catches on the same event.
- The base install keeps its floor check, tripwire and Leiden-free check on every pull request.
- Every Chroma-gated case keeps running in a complete job that fails loudly on a Chroma skip.

**Non-Goals:**

- Changing what the `test` job, the tripwire, the retrieval-quality tiers, the torch job, the frontend job or the lint job check.
- Making Pyright blocking, or changing Codecov thresholds.
- Removing the stale `harden-pipeline-correctness-before-calibration` branch from the pull-request triggers. It is unrelated and costs nothing.
- Branch protection. Adding required checks is a separate decision.

## Decisions

### D1. Delete the empty-extra floor entries

Remove `llamacpp` and `openrouter` from `floors.matrix.extra`. `uv sync --resolution lowest-direct --extra llamacpp` installs exactly what the base entry installs, so the two entries can never fail differently from the base. The Coverage job keeps `--extra llamacpp --extra openrouter` in its install line. Its comment says the extras stay so the old command keeps working, and the flags cost nothing.

Alternative considered: keep them as a guard in case the extras gain packages again. Rejected: the spec now says an extra with packages gets an entry. A future change that fills an extra adds the entry in the same pull request.

### D2. Fold the Chroma job into Coverage, with a report-based check

Delete the `chroma-extra` job. Coverage already installs `chroma` and `hybrid` from the lockfile and runs the same `-m "not slow"` suite with the tripwire left out.

Add one step to Coverage after the test step:

```yaml
- name: Assert no test skipped for a missing chroma extra
  if: ${{ !cancelled() }}
  run: |
    if grep -q 'chroma extra not installed' junit.xml; then
      echo "::error::Tests skipped with the chroma-extra reason even though the extra is installed"
      grep -o 'message="[^"]*chroma extra not installed[^"]*"' junit.xml | sort | uniq -c
      exit 1
    fi
```

The `floors` job gets the same step with `if: ${{ !cancelled() && matrix.extra == 'chroma' }}`. It reads the floors report, `${{ runner.temp }}/fast-junit.xml`, not `junit.xml`. For this the floors test step writes that report for every entry, not only the base entry. The base entry keeps reading its report in the tripwire step.

The report is the input, not the console log, because the report keeps every reason under xdist (Context).

The old job also printed a Chroma-only coverage slice (`--cov=omrs.core.vectordb.chroma`, term output, no upload). Coverage measures all of `omrs` and uploads it, so the Chroma adapter still counts towards patch coverage. The slice is dropped.

Alternative considered: keep the Chroma job and remove Chroma from Coverage. Rejected: Coverage is the only coverage upload, and the Chroma adapter must count towards patch coverage of vector-store diffs (the existing comment in the Coverage job).

### D3. A floors-scope job builds the floors matrix

Add a job `floors-scope` (display name `Floor matrix scope`) that runs on every event and has one output, `extras`, a JSON list. The `floors` job declares `needs: floors-scope` and uses `matrix.extra: ${{ fromJSON(needs.floors-scope.outputs.extras) }}`. Its `if: github.event_name != 'schedule'` line is removed, so the job also runs on the schedule and checks every floor on `main` once the nightly run exists (Context).

The scope rule:

| Event | Matrix |
|---|---|
| `pull_request`, no change to `pyproject.toml`, `uv.lock` or `.github/workflows/ci.yml` | `[""]` (base only) |
| `pull_request` that changes any of them | base and the 7 extras |
| `push` | base and the 7 extras |
| `schedule`, `workflow_dispatch` | base and the 7 extras |

The full list is `["", "hybrid", "pdf-pypdfium2", "community-leiden", "azure", "anthropic", "chroma", "web"]`, written once in the scope job. The pull-request check runs `git diff --name-only "$BASE_SHA...$HEAD_SHA"` on a checkout with `fetch-depth: 0`. `BASE_SHA` and `HEAD_SHA` come from `github.event.pull_request.base.sha` and `github.event.pull_request.head.sha` through `env:`. The three-dot form compares the head with the merge base, so commits that landed on the base branch after the fork do not count as changes of the pull request. If the diff fails, the job falls back to the full list, so a broken check runs more floors, never fewer.

Why a generated matrix: GitHub evaluates a job-level `if:` before it expands the matrix, so `if:` cannot read `matrix.extra`. The other ways out are two near-copies of the floors job (one base, one extras), or step-level skips that still start 7 runners. A generated matrix keeps one job definition and starts no idle runners.

Why push events run every extra: a push to `v3` happens once per merge. Pull requests get several pushes each while they are reviewed. Running the extras after the merge, on the real branch, catches a code change that breaks an extra's floor within one merge, at the cost of one matrix per merge rather than one per review push. Once it exists, the nightly run covers `main`, and also catches a new transitive release, because `lowest-direct` resolves only direct dependencies to their floors and takes the newest transitive ones.

Alternative considered: GitHub's workflow-level `paths:` filter in a separate `floors.yml`. Rejected: the base entry must still run on every pull request, so it would need its own copy in `ci.yml`, and the two files would drift.

Alternative considered: one combined "all extras at floors" entry on every pull request. Rejected: a combined resolution can lift one extra's direct dependency above its floor to satisfy another extra, so it does not test each floor. It also adds a 6-minute job back to every pull request.

### D4. Leiden on the lowest and the highest supported Python

Change `community-leiden-extra.matrix.python` from `["3.11", "3.12", "3.13", "3.14"]` to `["3.11", "3.14"]`. `requires-python = ">=3.11"`, and the job comment already says both packages ship abi3 wheels. With abi3 wheels the same binary serves every version from its minimum up, so the lowest version proves the wheel loads and the highest proves the newest interpreter accepts it. The comment changes from "every supported CPython version" to "the lowest and the highest supported CPython versions".

### D5. Coverage runs in parallel

Add `-n auto --maxprocesses=8` to the Coverage test step. `--dist loadfile` comes from `pyproject.toml`. pytest-cov combines the worker data itself under xdist; `[tool.coverage.run]` sets only `source`, so no setting conflicts.

Evidence that the same install combination is safe in parallel: the `test` job runs the fast suite in parallel with the `web` extra, and the floors entries run it in parallel with `chroma`, `hybrid` and `community-leiden` at their floors.

Acceptance check: Codecov's project total for the pull request head (parallel run) must match its total for the `v3` base commit (serial run) to within 0.1 percentage points. Codecov reports one total that counts lines and branches together, and the pull-request comparison shows both values. The test-file edits in this change touch only text, so the source under measurement is the same. A larger gap means a worker's data was lost; the change then keeps Coverage serial and records the gap.

### D6. Documentation

- **ADR-107** (new, Proposed; `add-model-search-and-download` already claims ADR-106): "CI keeps one job per distinct check". It records D1 to D5, the rule that a new optional extra with packages gets a floor entry, and the trade-off in D3.
- **ADR-042**: a dated addendum. Its 2026-08-15 update says the floors matrix exercises `llamacpp` and `openrouter`. The addendum says those entries are gone because the extras are empty, and that the extra entries now run by the D3 rule.
- **TDR-033**: a dated addendum. It points to the chroma-extra job for the Chroma display-name round trip. The addendum points to the Coverage job.
- **`docs/adr/ADR_README.md`**: a row for ADR-107.
- **`AGENTS.md`** (and the `CLAUDE.md` link to it): the "Parallel runs" paragraph says the other CI jobs stay serial; it changes to say Coverage runs in parallel too. Gotcha 13 adds when the extra floor entries run.
- **`tests/AGENTS.md`** item 7 and **`src/omrs/core/vectordb/AGENTS.md`** item 5: "CI runs them in the Coverage job".
- **`openspec/specs/retrieval-quality-regression-gate/spec.md`** (through this change's delta): the nightly-schedule scenario no longer lists the floors job among the jobs that do not run on the schedule.
- **`docs/guides/testing.md`**: the paragraph that names the `test` job and the floors base entry stays. A short "What CI runs" section lists each job, what it alone checks, and when it runs.
- **`scripts/local_ci.sh`**: the header comment lists "extras matrices (community-leiden, torch, chroma installs)" as excluded. It changes to "extras jobs (community-leiden, torch) and the Coverage job's chroma check".
- **Test files**: every skip reason, comment and docstring under `tests/` that names the chroma-extra job names the Coverage job instead (for example `tests/test_ingestion.py`, `tests/test_retrieval.py` and `tests/unit/test_folder_layout.py`, which have no skip reason). The "chroma extra not installed" prefix stays. The tripwire docstring changes the same way.

ADR and TDR bodies are records. Only addenda are added; their original text stays.

## Risks / Trade-offs

- [A code change breaks an optional extra's floor and the pull request does not touch dependency files] → The push after the merge runs every extra and fails on `v3`. The fix lands as a follow-up pull request. Floors matter to users who install without the lockfile, and a release goes out only from `main`, so no release ships the fault unnoticed.
- [The nightly run checks `main`, not `v3`] → Pushes to `v3` already run every extra (D3), so `v3` does not depend on the nightly run.
- [The floors-scope diff check has a bug and returns base only] → It falls back to the full list on any git error. Task 2.2 tests every row of the rule locally. This pull request shows the full-list row in GitHub. The base-only row can show in GitHub only after the merge, because any pull request into `v3` before then also changes `ci.yml`. The first ordinary pull request after the merge checks it (Workflow follow-up in tasks.md).
- [A Python version between 3.11 and 3.14 breaks the Leiden wheels] → abi3 makes that unlikely. Coverage runs the full suite on 3.12 with `community-leiden` installed, so 3.12 stays covered as well. Only 3.13 loses its Leiden run.
- [The parallel Coverage total drifts from the serial total] → D5's acceptance check catches it before merge.
- [Fewer jobs hide a flaky test that only one job used to hit] → The parallel suite still runs in `test` (two systems), the base floor entry and Coverage on every pull request.

## Migration Plan

One pull request to `v3` from `feat/trim-ci-jobs`. Because it changes `.github/workflows/ci.yml`, its own CI run takes the full floors matrix, so the pull request exercises every remaining job once. Rollback is a revert of the merge commit. No data, settings or package metadata change.
