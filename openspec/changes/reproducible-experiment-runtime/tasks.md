# Tasks

## 0. Set up

- [ ] 0.1 Create the worktree `../omrs-feat-reproducible-experiment-runtime` on branch `feat/reproducible-experiment-runtime` from `v3`, and run `uv sync --frozen --extra web` in it. Verify: `git rev-parse --show-toplevel` and `git branch --show-current` name the new worktree and branch.
- [ ] 0.2 Save the fast-suite test IDs to `openspec/changes/reproducible-experiment-runtime/evidence/test-ids-before.txt` (`uv run --no-sync pytest -m "not slow" --collect-only -q`). Verify: the file exists and is not empty.

## 1. Purpose field in the record (design D2)

- [ ] 1.1 Write tests first in `tests/unit/` for: a record with `"purpose": "publication"` loads; a record without `purpose` loads and reads as `optimisation`; `"purpose": "paper"` fails with a message that names the field and both allowed values; the shipped schema equals the generated schema. Verify: the new tests fail on the current code.
- [ ] 1.2 Add the optional `purpose` field to `src/omrs/core/experiment_records/record.py` and regenerate `schema/experiment.v1.schema.json`. Verify: the 1.1 tests pass, and `uv run --no-sync omrs experiments check` on `experiments/` reports no new finding for the 49 existing records.
- [ ] 1.3 Write tests for the folder creator: no purpose gives `"purpose": "optimisation"`; `publication` writes `"purpose": "publication"`; a `publication` follow-up of 38 creates `38a` and leaves the record of 38 byte-identical. Then add the `purpose` argument to `scaffold.py` and `--purpose {optimisation,publication}` to `omrs experiments new` in `transports/cli/experiments.py`. Verify: the tests fail first, then pass.

## 2. Runtime block and checker rules (design D3, D4)

- [ ] 2.1 Write tests for the runtime block model: a valid llama.cpp entry loads; a SHA-256 that is not 64 hex characters fails; a runtime other than `llama.cpp` fails unless `runtime_under_test` is true; with `runtime_under_test` true, an MLX entry without `version` fails; a block without `tolerance` fails. Verify: the tests fail first.
- [ ] 2.2 Add the runtime block model in a new module under `src/omrs/core/experiment_records/` (under 500 lines, `from __future__ import annotations`, Google-style docstrings). Verify: the 2.1 tests pass.
- [ ] 2.3 Write checker tests: `publication` + `Standard` gives an error that names the folder and the Confirmatory rule; Confirmatory `publication` without a `runtime` block gives an error; an unreadable `plan.json` on a `publication` record gives an error; an `optimisation` record and a record without a purpose give no runtime finding. Add the new codes to `check.py` and its docstring. Verify: the tests fail first, then pass, and a mutation check (remove each rule in turn) makes its test fail.

## 3. Live-server check (design D5)

- [ ] 3.1 Write tests for `experiments/_lib/llamacpp_runtime.py` with a fake HTTP server and small temporary files: a matching build and hash returns the found values; a wrong build raises `PreflightError` naming both builds; a wrong file hash raises naming the file and both hashes; router mode reads the model path from `/v1/models`; single-model mode reads `model_path` from `/props`; a non-loopback address is refused. Verify: the tests fail first.
- [ ] 3.2 Implement `experiments/_lib/llamacpp_runtime.py`. Verify: the 3.1 tests pass.
- [ ] 3.3 Write tests, then add an optional `runtime` key (build and `{file, sha256}` list) to the run record model in `core/experiment_records/run_record.py` and an optional `runtime` argument to `record_run_start` in `experiments/_lib/run_record.py`. Verify: old run-record lines still load, and a new line with `runtime` round-trips.
- [ ] 3.4 Run the check once against the live Llama app on `127.0.0.1:9931` with a scratch plan that pins `Qwen/Qwen3-Embedding-0.6B-GGUF` Q8_0 (`06507c7b…`) and build 11671. Then repeat with build 11510 in the plan. Verify: the first run passes and the second stops with both build numbers in the message. Save both outputs in `openspec/changes/reproducible-experiment-runtime/evidence/live-check.txt`.

## 4. Library API and web

Read `web/DESIGN.md` and load the `omrs-design` skill before this group.

- [ ] 4.1 Write API tests first: a create request with `purpose: "publication"` creates a `publication` record; no purpose creates `optimisation`; `purpose: "paper"` is refused with the allowed values named and no folder created; the list and the detail response carry `purpose`, and a record without the field returns `optimisation`. Then change `transports/api/routes/experiment_library.py`, `core/workspace/experiment_pages.py` and the OpenAPI contract. Verify: the tests fail first, then pass, and the contract test passes.
- [ ] 4.2 Write web tests first in `web/src/experiments/library/NewExperimentForm.test.tsx` and the list and page tests: the form shows `Optimisation` and `Publication` with `Optimisation` first; choosing `Publication` sets the size to `Confirmatory` and shows the one-line runtime note; the request carries the purpose; the list and page show the purpose label. Then change `NewExperimentForm.tsx`, `labels.ts` and the API client. Verify: the tests fail first, then pass, and no literal colour is added.
- [ ] 4.3 Run the four web gates in `web/`: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`. Verify: all four pass.

## 5. Rule text, templates and skill copies

- [ ] 5.1 Add the runtime rule and the purpose tier to `src/omrs/core/experiment_records/templates/experiments-agents.md`, and copy it to `experiments/AGENTS.md`. Add the `runtime` block with placeholder values to `templates/plan.json`, and a "Runtime" section to `templates/protocol.md`. Verify: `uv run --no-sync pytest tests/unit/test_experiments_guide_links.py -q` passes.
- [ ] 5.2 Copy the changed templates byte for byte to `.agents/skills/s-experiment/references/`, and add the rule to `.agents/skills/s-experiment/SKILL.md`. Verify: `uv run --no-sync pytest tests/unit/test_experiment_skill_drift.py -q` passes, including the personal-identifier scan.
- [ ] 5.3 Add a section "Local models and the experiment purpose" to `docs/guides/experiment-records.md`, written as a numbered procedure in ASD-STE100 style: choose the purpose, pin the GGUF file and build in `plan.json`, set a tolerance, call the live-server check, call `record_run_start` with the found runtime. Verify: every command and field name in the procedure exists in the code.

## 6. Decision records

- [ ] 6.1 Write `docs/adr/103-experiments-run-local-models-through-llama-cpp-gguf.md` (status Proposed) with the Ollama and llama.cpp embedding measurements, the oMLX parity table, the purpose tier and the rejected alternatives (Ollama pinned, oMLX fallback, format 2). Add its row to `docs/adr/ADR_README.md`. Verify: `uv run --no-sync pytest tests/unit -q -k "adr"` passes.
- [ ] 6.2 Mark ADR-074 decision 3 as withdrawn with a dated "Amended by ADR-103" note, and remove "or MLX 8-bit" from AGENTS.md Critical Gotcha 16. Verify: `grep -n "MLX 8-bit" AGENTS.md` shows no line that allows MLX as a runtime, and the ADR-074 index row names the amendment.

## 7. Carry-forward list (design D7)

- [ ] 7.1 Write `openspec/changes/reproducible-experiment-runtime/carry-forward.md`: one row per experiment folder with its number, title, status, the local runtime and models it used (from `plan.json`, the protocol or the report), and what a `publication` re-run needs (GGUF file available, data still in `DATA/omrs`, hosted references). Leave a "Carry forward?" column empty for the user. Verify: the row count equals the folder count from `uv run --no-sync omrs experiments check`, and each runtime entry names the file it came from.
- [ ] 7.2 Ask the user to fill the "Carry forward?" column. Verify: the user's choices are recorded in the file. No re-run starts in this change.

## 8. Integration checks

- [ ] 8.1 Re-pin the tripwire: collect the fast-suite IDs again, diff them with `evidence/test-ids-before.txt`, save `evidence/test-ids-diff.txt`, and change `_BASE_EXECUTED` (and `_WEB_EXTRA_CASES` for new tests that need fastapi) in `tests/test_clean_base_tripwire.py` by the counted difference, with a dated comment under 100 characters. Verify: `uv run --no-sync pytest tests/test_clean_base_tripwire.py -q` passes.
- [ ] 8.2 Run `./scripts/local_ci.sh`. Verify: every step passes and no step prints `SKIPPED`, or the skip is named in the PR body.
- [ ] 8.3 Browser check on a scratch server (`OMRS_CONFIG_DIR=<scratch>/config`, `--workspace <scratch>/ws`, a fixed port), never the live app on port 8765. At 1280 px and 390 px: create one `Optimisation` and one `Publication` experiment in a scratch project, and check the size switch, the runtime note and the purpose label in the list and on the page. Verify: no sideways scroll at 390 px, and results are written to `openspec/changes/reproducible-experiment-runtime/browser-check.md`. Stop only that server afterwards.
- [ ] 8.4 Run `openspec validate reproducible-experiment-runtime --strict` and `openspec validate --all --strict`. Verify: the first passes. The second passes, or every failure is a "Requirement text is very long" warning that OpenSpec 1.15.0 (installed 2026-10-27) also reports on `v3` before this change (64 items at proposal time, 0 errors); name that count in the PR body.

## 9. After merge

- [ ] 9.1 Set ADR-103 to Accepted with the PR number, and update its index row. Verify: the status and the index row agree.
- [ ] 9.2 Reinstall the live app with locked constraints (after the user agrees): build the web bundle, back up `~/.omrs/workspace/workspace.db` to a dated `.bak`, export the constraints, run `uv tool install --reinstall -c <constraints> "omrs[web,hybrid] @ <v3 checkout>"`, then `omrs web restart`. Verify: 0 differences against the export, `/v1/health` answers, and the live library shows `Optimisation` on an old experiment. Create no experiment in the live app as part of the check.
- [ ] 9.3 Outside the repository: add the rule to the personal skill `~/.agents/skills/s-experiment/SKILL.md` and its `references/template-plan.json` in its general wording (it is not a byte copy). Verify: `grep -n "llama.cpp" ~/.agents/skills/s-experiment/SKILL.md` shows the rule, and the file contains no home-folder path.
- [ ] 9.4 Archive with `openspec-archive-change`, which merges the deltas into `openspec/specs/experiment-records/`, `experiment-validity-gates/` and `workspace-experiment-library/`. Verify: `openspec validate --all --strict` passes after the archive.
