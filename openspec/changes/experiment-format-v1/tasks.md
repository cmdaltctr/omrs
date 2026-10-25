# Tasks

## 1. Baseline

- [ ] 1.1 Confirm the worktree root and branch with `git rev-parse --show-toplevel` and `git branch --show-current`. Verify: both name `llamaindex-rag-mcp-feat-experiment-format-v1` and `feat/experiment-format-v1`.
- [ ] 1.2 Confirm the backup in `~/Development/DATA/omrs/backups/experiments-pre-format-v1-2026-10-25/`. Verify: `shasum -a 256 -c SHA256SUMS` passes in that folder.

## 2. Record model and schema (design D1 to D4)

- [ ] 2.1 Write tests in `tests/unit/test_experiment_records_model.py` for: a valid record; an unknown key; an unknown format version (dedicated error naming it); each of the seven status values; `SUPERSEDED` without `superseded_by`; `PASS` with `superseded_by`; empty category or size with and without a migration note; a finding with a newline; number patterns `22`, `5b`, `10.1`, empty, and a bad one. Verify: the tests fail because the package does not exist.
- [ ] 2.2 Create `src/omrs/core/experiment_records/` with `__init__.py` and `record.py` (D1 to D4). Verify: the tests from 2.1 pass.
- [ ] 2.3 Generate `schema/experiment.v1.schema.json` from the model with sorted keys. Add a test that compares the file with `model_json_schema()`. Verify: the test passes, and it fails when one key in the file is changed.
- [ ] 2.4 Add the import-linter contract `experiment-records-stay-pure` in `pyproject.toml`. It forbids `subprocess`, web frameworks, stores, `omrs.compose*`, `omrs.engine*`, `omrs.transports` and `omrs.core.experiments`. Check whether `tests/test_core_import_contracts.py` or another list must name the new package, and update it. Verify: `uv run --no-sync lint-imports` passes.

## 3. Naming, detection, reservations and run records (design D5, D7, D8)

- [ ] 3.1 Write tests for `naming.py`: the folder pattern, slug rules, number parsing, and the natural sort `5 < 5b < 6 < 10 < 10.1 < 10b`, with unnumbered names last. Then implement. Verify: the tests fail first, then pass.
- [ ] 3.2 Write tests for `scan.py` on a temporary directory: folders with a record, folders matched by name only, `_lib/`, `ARCHIVED/` and `example/` ignored, two folders with the same number, and an `output/` with nested files where only top-level names are read (assert that no nested file is opened). Then implement. Verify: the tests fail first, then pass.
- [ ] 3.3 Write tests for `reserved.py` (valid file, missing file means no reservations, unknown key, bad number), then implement. Verify: the tests fail first, then pass.
- [ ] 3.4 Write tests for `run_record.py`: appending twice keeps line one byte-identical; each line declares `omrs-run-record/1`; the start time is UTC; an empty plan hash is allowed. Then implement. Verify: the tests fail first, then pass.
- [ ] 3.5 Add `experiments/_lib/run_record.py`. It reads the git commit and dirty flag with `git` and calls the core append function. Add a test with a temporary git repository. Verify: the test passes.

## 4. Checker and index (design D6, spec "The checker reports problems")

- [ ] 4.1 Write tests for `check.py`, one per rule in the spec, with error, warning and information cases for new and converted records. Add a test that takes a hash of every file in the directory before and after a check and asserts that nothing changed. Then implement. Verify: the tests fail first, then pass.
- [ ] 4.2 Write tests for `index.py`: deterministic output; order by number, then folder name, with unnumbered experiments last; `|` escaped; text outside the markers byte-identical after a write; a write refused when a marker is missing, with the file unchanged; the stale-table check. Then implement. Verify: the tests fail first, then pass.

## 5. Templates and folder creator (design D9, spec "New experiment folders")

- [ ] 5.1 Write the templates in `src/omrs/core/experiment_records/templates/`: `protocol.md`, `report.md`, `report-quick.md`, `plan.json` (no `status` key), `experiments-agents.md` and `exp-readme.md`. Start from the six-section protocol and the report Answer box used by the `s-experiment` skill. Remove personal paths. Verify: `templates.py` loads each file through `importlib.resources`, and a test asserts that `plan.json` has no `status` key.
- [ ] 5.2 Write tests for `scaffold.py`: next number skips reservations; follow-up letters `38a` then `38b`; Standard and Quick file sets; the record is valid and `PLANNED`; refusal when the folder exists, with nothing written; a bad slug refused. Then implement. Verify: the tests fail first, then pass.
- [ ] 5.3 Build a wheel with `uv build --wheel` into the session scratchpad. List its contents. Verify: every template and the schema file are in the wheel.

## 6. CLI (design D10)

- [ ] 6.1 Write CLI tests with Typer's `CliRunner` for `check` (exit codes with and without `--strict`, `--json`), `index` (stale exit code, `--write`) and `new` (creates a folder and prints its path). Assert that the output goes to stderr. Then add `src/omrs/transports/cli/experiments.py` and register it in `transports/cli/__init__.py`. Verify: the tests fail first, then pass.
- [ ] 6.2 Document the commands in `docs/guides/cli-reference.md`. Verify: each command and option is listed.

## 7. Move the existing folders (design D11)

- [ ] 7.1 Write `openspec/changes/experiment-format-v1/migration/convert.py`. It reads `EXP_README.md` and the folders, applies the D11 mapping, and writes `experiment.json` only where none exists. It writes `migration/report.md` with every non-trivial mapping, every inferred category and size, every folder without an index row, and every `SUPERSEDED` row with its target. It stops on a `SUPERSEDED` row without a target that it can find. Verify: a dry run (`--dry-run`) lists 50 folders and writes nothing.
- [ ] 7.2 Run the script for real. Verify: `git status --short experiments/` shows only new `experiment.json` files, and `git diff --stat experiments/` shows no change to any existing file.
- [ ] 7.3 Create `experiments/reserved.json` with 35, 40 and 41 (design D7). Verify: `omrs experiments check` loads it.
- [ ] 7.4 Add the two markers around the index table in `EXP_README.md`, then run `uv run --no-sync omrs experiments index --write`. Verify: `git diff experiments/EXP_README.md` changes only lines between the markers, and every former row is still present with the same title, date and finding.
- [ ] 7.5 Run `uv run --no-sync omrs experiments check`. Fix every error by editing the new `experiment.json` files only. Verify: the check reports no errors. Record the warning and information counts in `migration/report.md`.

## 8. Folder guide, skill copy and docs

- [ ] 8.1 Write `experiments/AGENTS.md` from the `experiments-agents.md` template, and add `experiments/CLAUDE.md` as a symlink to it. Update the "How to Add an Experiment" and "Conventions" sections of `EXP_README.md` to point to the new commands and the seven status values. Add a test that resolves every link in `experiments/AGENTS.md` and asserts that each one stays inside the repository. Verify: the test passes.
- [ ] 8.2 Add `.agents/skills/s-experiment/` to the repository. Base it on the personal skill. Update it for format v1: `experiment.json`, seven status values, `plan.json` without `status`, folder names without a category, `reserved.json`, run records, and the `omrs experiments` commands. Copy the package templates byte for byte into `references/`. Verify: `grep -rIn -E "aizat|/Users/|@praxis" .agents/skills/s-experiment` finds nothing.
- [ ] 8.3 Add `tests/unit/test_experiment_skill_drift.py` with the explicit file map (design D9) and a scan for personal identifiers. Verify: the test passes, fails when one template byte changes, and fails on a planted home-folder path.
- [ ] 8.4 Write `docs/guides/experiment-records.md`: the record fields, status values, naming, reservations, run records, checker codes and commands. Link it from the documentation table in `CLAUDE.md` and add `experiments/` to the folder-guide list. Verify: links resolve.
- [ ] 8.5 Write an ADR with the `s-adr` skill: experiment records use a versioned format shipped in `omrs`, with status outside the frozen plan. Add it to the ADR index. Verify: the ADR names the alternatives in design D2, D3 and D11.

## 9. Verification

- [ ] 9.1 Update `_BASE_EXECUTED` in `tests/test_clean_base_tripwire.py`. Compare collected test IDs with the base, as the tripwire comment says. Verify: the tripwire passes.
- [ ] 9.2 Run `./scripts/local_ci.sh`. Verify: every step passes, or each `SKIPPED` step is named in the report.
- [ ] 9.3 Run `openspec validate experiment-format-v1 --strict` and `openspec validate --all --strict`. Verify: both pass.
- [ ] 9.4 Search the diff for personal identifiers: `git diff v3 -- . ':!openspec/changes/experiment-format-v1/migration' | grep -n -E "aizat|/Users/|@praxis"`. Verify: no hit, or each hit is explained.
