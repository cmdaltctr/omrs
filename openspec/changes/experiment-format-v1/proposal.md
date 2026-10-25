# Proposal

## Why

OMRS has 54 experiment folders, but no written format that a program can read. Only the personal `s-experiment` skill describes the folder layout, and most folders do not follow it. A read-only check on 2026-10-25 found these problems:

- Status is in up to four places (`plan.json`, `protocol.md`, `report.md` or `results.md`, `EXP_README.md`), and the values often disagree. Experiment 25 says `PLANNED` in its plan and `PASS` in the index.
- Status uses values that have no defined meaning: `COMPLETE`, `PARTIAL`, `REBUILT`, `FROZEN`, and free sentences.
- `EXP_README.md` indexes 45 rows for 51 numbered folders. Experiment 6c has no row.
- Two numbers are used twice (`19`, `9a`), and reserved numbers (35, 40, 41) are known only from OpenSpec, NiftyPM and a branch.
- File dates cannot show that a plan came before its run, because copies reset them.

The web workspace will show and create experiments in a later change. It needs a stable, versioned format first. If we wait, the app must support the old mix of layouts for longer.

## What Changes

- A versioned experiment format, `omrs-experiment/1`, ships inside the `omrs` package. It has a typed record model, a generated JSON Schema, templates, a checker, an index renderer and a folder creator.
- Every experiment folder gets one new file, `experiment.json`. It holds the facts that change after planning or that the index needs: number, title, date, category, size, status, `superseded_by`, a one-line finding, optional references, and a `migration` note for converted folders. `plan.json` stays frozen. No code writes to it.
- Status has seven values: `PLANNED`, `ACTIVE`, `PASS`, `FAIL`, `INCONCLUSIVE`, `MEASURED`, `SUPERSEDED`. `SUPERSEDED` needs `superseded_by`.
- New folder names keep the current style `<number>-<slug>-<YYYY-MM-DD>`. The folder name is the experiment identity. The number is a label and can repeat in old folders.
- `experiments/reserved.json` lists numbers that are reserved but have no folder yet. The folder creator does not use a reserved number.
- Each run appends one line to `output/run-records.jsonl` with its start time, git commit, dirty-tree flag and the SHA-256 of `plan.json`. The checker uses it to find a plan that changed after a run.
- The index table in `EXP_README.md` is generated from the `experiment.json` files, between two marker lines. The rest of the file stays as written.
- A new CLI group: `omrs experiments check`, `omrs experiments index` and `omrs experiments new`.
- One-time move of the existing folders: back up the tracked files (done on 2026-10-25, recorded in `DATA/omrs/DATA_LOCATIONS.md`), add `experiment.json` to each folder, seed `reserved.json`, and put the index table between markers. No existing file inside an experiment folder changes. The move script stays in this change folder and does not ship.
- `experiments/AGENTS.md` (with a `CLAUDE.md` link) gives the rules for this folder. It does not link outside the repository.
- The repository gets its own copy of the `s-experiment` skill in `.agents/skills/s-experiment/`, updated for format v1, with no personal paths. A test checks that the skill's templates match the package templates.

Out of scope: web workspace screens, notebooks, and storage in `workspace.db`. A later change (experiments in the web workspace) builds on this format.

## Capabilities

### New Capabilities

- `experiment-records`: the versioned experiment record format, folder detection and naming, reserved numbers, run records, the checker, the generated index, the folder creator and its CLI.

### Modified Capabilities

None. `experiment-validity-gates` keeps its requirements. Run records add to its runtime manifest and replace nothing in it.

## Impact

- New package `src/omrs/core/experiment_records/` (pure Python, pydantic only) with package data: `schema/experiment.v1.schema.json` and `templates/`.
- New CLI module `src/omrs/transports/cli/experiments.py`, registered in `transports/cli/__init__.py`.
- `pyproject.toml`: import-linter contract for the new package.
- New helper `experiments/_lib/run_record.py`.
- `experiments/`: one new `experiment.json` per experiment folder, `reserved.json`, markers and a regenerated index table in `EXP_README.md`, `AGENTS.md` and `CLAUDE.md`.
- `.agents/skills/s-experiment/` (new, repository copy).
- Docs: a new guide `docs/guides/experiment-records.md`, a new ADR, root `AGENTS.md` folder-guide list.
- Tests: new unit tests, the skill drift test, and the clean-base tripwire pin.
- No new dependency. No change to stored data, the web app, the MCP server or `workspace.db`.
