# Tasks

Work in the sibling worktree `omrs-feat-trim-ci-jobs` on branch `feat/trim-ci-jobs`, forked from `v3`. Prepare it with `uv sync --frozen --extra web`. Run `actionlint` after every edit to `.github/workflows/ci.yml`.

## 1. Remove the empty-extra floor entries and the Chroma job (D1, D2)

- [ ] 1.1 Remove `llamacpp` and `openrouter` from the `floors` matrix, and verify `actionlint` passes and `grep -nE '^ +- (llamacpp|openrouter)$' .github/workflows/ci.yml` prints nothing.
- [ ] 1.2 Make the floors test step write a JUnit report for every entry, keep the base entry's tripwire step reading its report, and verify `actionlint` passes.
- [ ] 1.3 Add the "no chroma-extra skip" step from design D2 to the Coverage job (reads `junit.xml`) and to the `chroma` floor entry (reads `${{ runner.temp }}/fast-junit.xml`). Verify actionlint passes. Verify the check fails when it should: run four Chroma-gated files (`tests/test_compose.py tests/test_lancedb_store.py tests/test_vectordb_contract.py tests/test_hybrid_retrieval.py`) with `-n 2 --junitxml` in the base venv, run the step's shell lines on that report, and confirm exit 1 with the reasons listed. Then confirm exit 0 on a report from a scratch venv that has `--extra chroma --extra hybrid` (`UV_PROJECT_ENVIRONMENT` set to a scratchpad folder).
- [ ] 1.4 Delete the `chroma-extra` job, and verify `actionlint` passes and `grep -n 'chroma-extra:' .github/workflows/ci.yml` prints nothing.
- [ ] 1.5 Change every skip reason, comment and docstring in `tests/**/*.py` that names the chroma-extra job to name the Coverage CI job, including the tripwire docstring. Verify `git grep -n 'chroma-extra' -- 'tests/*.py'` prints nothing, `git grep -c 'chroma extra not installed' -- tests` gives the same file list as before, and `git diff -U0 tests/test_clean_base_tripwire.py | grep -E '^[-+]_BASE_'` prints nothing (pins unchanged). Task 6.1 runs the tripwire on a fresh report.
- [ ] 1.6 Update `tests/AGENTS.md` item 7 and `src/omrs/core/vectordb/AGENTS.md` item 5 to name the Coverage job, add the TDR-033 addendum (design D6), and change the excluded-jobs list in the `scripts/local_ci.sh` header (design D6). Verify `git grep -n 'chroma-extra' -- tests src scripts` prints nothing, `bash -n scripts/local_ci.sh` passes and `uv run pytest tests/test_docs_references.py -q` passes.

## 2. Scope the floors matrix (D3)

- [ ] 2.1 Add the `floors-scope` job with the rule table and the three-dot diff from design D3. Pass the pull-request SHAs through `env:`, not inline in the script. Make `floors` use `needs: floors-scope` and the generated matrix, and remove its `if:` line. Verify `actionlint` passes.
- [ ] 2.2 Check the scope script locally before pushing: run its shell body with the event variables set for each row of the D3 table (pull request with and without a `pyproject.toml` change, a pull request whose base branch gained a `pyproject.toml` change after the fork, push, schedule, dispatch, and a forced git error), and verify each prints the expected JSON list. The base-gained case must print `[""]`.
- [ ] 2.3 After the pull request opens, verify in the GitHub run that `Floor matrix scope` printed the full list (the pull request changes `ci.yml`) and that 8 `Floor resolution` entries ran, with no `llamacpp` or `openrouter` entry. A throwaway pull request into `v3` cannot show the base-only row before the merge, because its diff against `v3` also holds the `ci.yml` change. The Workflow follow-up checks that row.
- [ ] 2.4 Update `AGENTS.md` gotcha 13 with when the extra floor entries run, add the ADR-042 addendum (design D6), and verify `uv run pytest tests/test_docs_references.py -q` passes.
- [ ] 2.5 Confirm the delta for `retrieval-quality-regression-gate` in this change matches the new floors `if:`: the floors job runs on the schedule, and every other job keeps its current schedule behaviour. Verify `openspec validate trim-ci-jobs --strict` passes.

## 3. Leiden on two Python versions (D4)

- [ ] 3.1 Change the `community-leiden-extra` matrix to `["3.11", "3.14"]` and its comment to "the lowest and the highest supported CPython versions". Verify `actionlint` passes and the pull request run shows exactly `Leiden extra (Python 3.11)` and `Leiden extra (Python 3.14)`, both green.

## 4. Parallel Coverage (D5)

- [ ] 4.1 Before changing CI, record the Codecov project total for the current `v3` tip (serial run) and its commit. Record them in the pull request description.
- [ ] 4.2 Add `-n auto --maxprocesses=8` to the Coverage test step, and verify `actionlint` passes.
- [ ] 4.3 Run the Coverage command locally once in a scratch venv with the same extras as the job (`UV_PROJECT_ENVIRONMENT` in the scratchpad, `uv sync --frozen` with the job's extras). Verify it passes, writes `coverage.xml` and `junit.xml`, and that the chroma-skip check from 1.3 exits 0 on that report. Warn the user before this run and wait for a go; it uses all cores for a few minutes.
- [ ] 4.4 On the pull request, read Codecov's base and head project totals. Verify the head total is within 0.1 percentage points of the base total, and record both values and the Coverage job time in the pull request description. If the gap is larger, revert 4.2, and change design D5, the 4.5 doc edit and ADR-107 to record that Coverage stays serial and why.
- [ ] 4.5 Update the "Parallel runs" paragraph in `AGENTS.md` to say Coverage runs in parallel too, and verify `uv run pytest tests/test_docs_references.py -q` passes.

## 5. Decision record and guides (D6)

- [ ] 5.1 Write ADR-107 "CI keeps one job per distinct check" with status Proposed, covering D1 to D5, the new-extra rule and the D3 trade-off. Check first that no other change has taken 107; take the next free number if one has. Add its row to `docs/adr/ADR_README.md`. Verify `uv run pytest tests/test_docs_references.py -q` passes.
- [ ] 5.2 Add the "What CI runs" section to `docs/guides/testing.md` (each job, what only it checks, when it runs), and verify each job name in the section matches a `name:` in `ci.yml`.

## 6. Integration checks

- [ ] 6.1 Run `./scripts/local_ci.sh` and `openspec validate trim-ci-jobs --strict`, and verify both pass with no `SKIPPED` step except ones the machine cannot run.
- [ ] 6.2 Search the staged diff for personal identifiers (`git diff --cached | grep -nE "aizat|/Users/|@praxis"`), and verify nothing matches. Write the ADR `Deciders` line as `Maintainer`, as recent ADRs and TDRs do.
- [ ] 6.3 Open one pull request into `v3` and watch CI until every check ends. Verify the run lists 19 jobs (the dependency-change count in the proposal, because this pull request changes `ci.yml`), and record the job count and total time against the 23-job run before this change (run 40874653858).
- [ ] 6.4 Read the CodeRabbit comments, fix the valid ones, reply to each, and resolve every thread. Do not merge; wait for the user.

## Workflow follow-up

- After merge: on the first pull request into `v3` that changes no dependency file and not `ci.yml`, verify `Floor matrix scope` printed `[""]` and only the base `Floor resolution` entry ran. Record the run in ADR-107.
- After merge: set ADR-107 to Accepted with the merge commit, copy no gitignored data (this change makes none), remove the worktree and branch, and archive the change.
