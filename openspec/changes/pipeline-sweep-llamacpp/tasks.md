# Tasks

## 0. Set up

- [ ] 0.1 Create the worktree `../omrs-v3-feat-pipeline-sweep-llamacpp` on branch `feat/pipeline-sweep-llamacpp` from `v3`, and run `uv sync --frozen --extra web --extra llamacpp` in it. Verify: `git rev-parse --show-toplevel` and `git branch --show-current` name the new worktree and branch.
- [ ] 0.2 Save the fast-suite test IDs to `openspec/changes/pipeline-sweep-llamacpp/evidence/test-ids-before.txt` (`uv run --no-sync pytest -m "not slow" --collect-only -q`). Verify: the file exists and is not empty.

## 1. Router check (design D3)

- [ ] 1.1 Write a router preset file in the experiment folder with one preset per model (D2). Start `llama serve` on the scratch port with it, after telling the user. Run `verify_llamacpp_runtime` against it with a scratch plan that pins the 4B embedding and the 4B chat model. Verify: the check passes, the found runtime names both files, and one embedding and one chat request each return a result.

## 2. Experiment folder and plan (design D1, D2, D5, D8)

- [ ] 2.1 Run `uv run --no-sync omrs experiments new pipeline-sweep-llamacpp --title "Pipeline sweep on llama.cpp" --category runtime --size Standard --purpose optimisation`. Verify: the folder has the next free number, and `experiment.json` holds `"purpose": "optimisation"` and size `Standard`.
- [ ] 2.2 Copy the 6 files of Experiment 3 `corpus/` and Experiment 2 `ground-truth.json` into the new folder. Verify: `shasum -a 256` of each copy equals its source.
- [ ] 2.3 Download the FinanceBench open sample into `output/`. Apply the D1 selection rule and record the 5 PDFs, their SHA-256, page counts and question IDs. Verify: the 5 files are gitignored (`git check-ignore`), and each has 200 pages or fewer.
- [ ] 2.3a Download the `enelpol/rag-mini-bioasq` test-split corpus at a pinned revision into `~/Development/DATA/omrs/`, and record the revision and SHA-256. Locate the FreshStack corpus and record its ID-list hash. Verify: the BioASQ corpus loads about 40.2K passages, and FreshStack 10,024 documents.
- [ ] 2.4 Download the four GGUF files (D2) and record their SHA-256. Read the build from `GET /props` of the installed `llama serve`. Verify: the build is b11510 or later.
- [ ] 2.5 Write `protocol.md` (question, null, decision rule, the fixed set with hashes, the exit table of D5) and `plan.json` with the full `runtime` block: four models, no hosted reference, and tolerances for `hit_at_1` and `mrr`. Verify: `uv run --no-sync omrs experiments check` reports no error for the folder.
- [ ] 2.6 Commit `protocol.md` and `plan.json` before the first run. Verify: `git log -1 -- <folder>/plan.json` shows the commit.

## 3. Part A runner (design D4)

- [ ] 3.1 Write tests first for the runner's pure parts in the experiment folder: the input-hash check stops on a changed file and names both hashes; the FinanceBench page conversion maps `evidence_page_num` 0 to page 1; the determinism comparison reports the question, mode and both rankings on a difference. Verify: the tests fail before the code exists.
- [ ] 3.2 Write the Part A runner: hash check, live-server check of the router, `record_run_start` with `found.as_run_record()`, ingest, three search modes, answers with claim checking off and on, and one JSONL file per step in `output/`. Use a scratch `OMRS_CONFIG_DIR` inside `output/`. Verify: 3.1 tests pass, and `--limit 1` runs one document and one question with no error.
- [ ] 3.3 Write the determinism repeat as a separate process on the same index. Verify: run twice on the `--limit 1` index gives identical output.
- [ ] 3.4 Write the comparison-arm step: dense index of the 6 Experiment 3 documents with 0.6B and 8B, 17 questions, reranker off. Verify: `--limit 1` writes one row per model.

## 4. Part B timing (design D6)

- [ ] 4.0 Write tests first for Part C's comparison (design D6a): identical vectors give cosine 1.0 and no ranking change; a changed vector below 0.9999 fails the rule and names the chunk; a swapped top-10 pair fails the rule and names the question; a plan model without `parallel` fails the preset check. Then write the comparison and preset check. Verify: the tests fail before the code exists, then pass.

- [ ] 4.1 Write tests first for the extrapolation: tokens divided by tokens per second gives hours; the FinanceBench estimate uses tokens per page times total pages; a missing count raises an error that names the corpus. Verify: the tests fail before the code exists.
- [ ] 4.2 Write the timing runner: one model loaded at a time in the router, live-server check with a plan block for that model, one run record per model, one warm-up batch, then the three slices of D6 (FreshStack, BioASQ, FinanceBench chunks). Record wall time, `usage.prompt_tokens` and peak resident memory sampled every 0.5 s. Verify: a 5-document dry run writes one row per model and slice.
- [ ] 4.3 Write the token count step for FreshStack and BioASQ (chunk, then `/tokenize`, no embedding) and the FinanceBench page count. Verify: the FreshStack count covers 10,024 documents and the BioASQ count covers every passage in the test split corpus.

## 5. Run (heavy: tell the user before each server starts)

- [ ] 5.1 Run Part A. Verify: `output/run-records.jsonl` has a line with `runtime` holding one build and both model hashes, and every stage file exists.
- [ ] 5.2 Run the determinism repeat and the comparison arms. Verify: their output files exist and name the index they read.
- [ ] 5.3 Run Part B for 0.6B, 4B and 8B, one at a time. Verify: three run-record lines, one per model, and nine timing rows (three models by three slices).
- [ ] 5.4 Run the token counts and the extrapolation. Verify: one estimate per model and corpus.
- [ ] 5.5 Run Part C (design D6a): 4B exact mode, then fast mode, on the Part B slices. Verify: one output row per vector pair, the lowest and median cosine, the top-10 ranking comparison and both speeds are written to `output/`.

## 6. Report

- [ ] 6.1 Write `report.md`: Answer box, the D5 exit table with the Experiment 2 and 3 values beside each result, the determinism result, the timing and estimate table, and the known differences (LanceDB, runtime). Every number names its `output/` file. Verify: `uv run --no-sync omrs experiments check` passes.
- [ ] 6.2 Set `status` (`PASS` or `FAIL`) and `finding` in `experiment.json`, then run `uv run --no-sync omrs experiments index --write`. Verify: the index row matches the record.
- [ ] 6.3 For each failed stage, write one line in the report with the fix and whether it needs its own change. Verify: no failed stage is left without a line.
- [ ] 6.4 Tell the user that Part B gives the numbers Experiment 35 task 1.4 reuses, with the machine, GGUF hashes and build they hold (design D7). Do not edit that change. Verify: the message names the output file and the build.

## 7. Integration checks

- [ ] 7.1 Re-pin the tripwire: collect the fast-suite IDs again, diff them with `evidence/test-ids-before.txt`, save `evidence/test-ids-diff.txt`, and change `_BASE_EXECUTED` in `tests/test_clean_base_tripwire.py` by the counted difference, with a dated comment under 100 characters. Verify: `uv run --no-sync pytest tests/test_clean_base_tripwire.py -q` passes.
- [ ] 7.2 Run `./scripts/local_ci.sh`. Verify: every step passes and no step prints `SKIPPED`, or the skip is named in the PR body.
- [ ] 7.3 Run `openspec validate pipeline-sweep-llamacpp --strict` and `openspec validate --all --strict`. Verify: both pass.

## Workflow follow-up

- Before removing the worktree, copy the experiment `output/` to `~/Development/DATA/omrs/experiments/<folder>/` and record its SHA-256 (AGENTS.md Gotcha 15).
- Archive with `openspec-archive-change`. It adds `pipeline-sweep-evaluation` to `openspec/specs/` and the new requirement to `experiment-validity-gates`.
