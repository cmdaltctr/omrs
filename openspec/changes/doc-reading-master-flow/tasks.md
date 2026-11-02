# Tasks

The order below is the contract. Do not reorder groups. Stop at every gate (design D5). Each group names the change whose own tasks carry the detail. Rules live in the repo `AGENTS.md` and the handoff `2026-11-02-doc-reading-and-dots-mocr-handoff.md` section 1.

## 0. Live page mode (operator, by hand)

- [ ] 0.1 (Operator) Add `"ocr_routing_unit": "page"` to `~/.config/omrs/omrs.jsonc` (or set it in Settings > Document reading) and add `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` (absolute paths, design D3) to the live app's environment, then restart. The agent never edits the live config; it may write the exact steps out on request.
- [ ] 0.2 (Operator) Ingest `rf06` into a test collection, search "Antonia Cruz", and check the log for "Local OCR tier unavailable". GATE G0: the operator reports the result. If the warning shows, the library paths are wrong; fix them before anything else.

## 1. Redo dots-mocr task 3.4 with page mode (worktree `omrs-feat-dots-mocr-llamacpp-backend`)

- [ ] 1.1 Read that change's `tasks.md` (task 3.4), `design.md` D9, and `ocr-workers/engines/dots-mocr-llamacpp/SMOKE_RESULTS.md`. Confirm `git rev-parse --show-toplevel` and `git branch --show-current` before any command. Prepare with `uv sync --frozen --extra web`.
- [ ] 1.2 Build the scratch environment: scratch `OMRS_CONFIG_DIR`, `OMRS_STATE_DIR`, `LANCEDB_URI`; `ocr_routing_unit=page`; engine `dots-mocr-llamacpp`; set `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH`; after the first pages, grep the log for "Local OCR tier unavailable".
- [ ] 1.3 GATE G1: warn the operator: about 1 to 1.5 hours of GPU. Blank pages add time because the blank-skip change is not merged yet; say so.
- [ ] 1.4 Ingest `eq01`, `io06`, `rf06` with the CLI. Pass: a search finds a known phrase from an OCR page of each PDF, including "Antonia Cruz Gonzalez" and "Sevilla 17 de Agosto" from `rf06` page 29; KaTeX 0.16.22 renders `eq01` formulas with 0 errors.
- [ ] 1.5 Record the run in `SMOKE_RESULTS.md` (amend the task 3.4 row), tick 3.4 only if all pass, and report the three search results to the operator.

## 2. Finish the dots-mocr change (same worktree)

- [ ] 2.1 GATE G2: the operator gives "3.7 confirmed" with a date. Without it, stop.
- [ ] 2.2 Do group 4 exactly as already decided (change `tasks.md` 4.1 to 4.4): delete the PyTorch engine `ocr-workers/engines/dots-mocr`; rename `dots-mocr-llamacpp` to `dots-mocr` keeping `backend_id` `dots_mocr_llamacpp`; update tests, docs and the tripwire (pin moves from 9859); add a `model` name to the engine request as a separate small commit, test first; write the ADR "dots.mocr runs on llama.cpp" after the cut-over with a dated note on ADR-072, recording Ollama 7 of 10, MLX 3 of 10, llama.cpp 22 of 22 identical pages.
- [ ] 2.3 STOP before task 4.5. GATE G3: the operator approves touching the live workers folder `~/.omrs/ocr-workers` and restarting the app.
- [ ] 2.4 Group 5: ask before `./scripts/local_ci.sh`; run `openspec validate --all --strict`; open a PR into `v3`; never merge unasked. GATE G4: the operator says merge.
- [ ] 2.5 After merge: refresh `v3` (`git -C omrs-v3 pull --ff-only` if the merge happened on the remote, else merge locally as the operator directs). The llama.cpp engine now sits on `v3`. Later groups fork fresh from this `v3`.

## 3. Apply `skip-blank-pages-before-worker` (new worktree `omrs-feat-skip-blank-pages` from fresh `v3`)

- [ ] 3.1 Fork the worktree from `v3` after group 2 merged. Apply the change (`/opsx:apply skip-blank-pages-before-worker`), following its tasks 1 to 3 (blank test module, fifth count, index identity), tests first.
- [ ] 3.2 Its task 4.1 names engine `dots-mocr-llamacpp`; after the group 2 rename the engine is `dots-mocr`. Run 4.1 with the renamed engine and note the rename in the verification note. Recreate the 10-page `rf06` extract if the scratch copy is gone (original pages in design D4). Verify: 4 pages count `ocr_pages_blank`, 0 worker calls on them, the other 6 pages Dice 1.0 against the earlier run, engine seconds saved stated.
- [ ] 3.3 Task 4.2: run the blank test on all 40 Experiment 33 documents (design expects 37 of 701 flagged pages skipped; no page with 3 or more reference characters skipped).
- [ ] 3.4 Ask before `./scripts/local_ci.sh`; run `openspec validate skip-blank-pages-before-worker --strict`; open a PR into `v3`. GATE G5: the operator says merge.

## 4. Routing re-test on new documents (pre-registered)

- [ ] 4.1 GATE G6: the operator supplies or approves the new-document set. New means: not used in Experiments 33, 41 or 43 and not part of the blank-threshold fit.
- [ ] 4.2 Reserve the next free experiment number (45 unless taken; check `experiments/` folders and `reserved.json`). With the `s-experiment` skill, write `protocol.md` and `plan.json`, commit both before any run. Design: page mode, no judge model, the 10% rule plays no part. Measures per document: every junk-text page reaches OCR; no usable page wrongly OCR'd; the counts `native`, `local`, `worker`, `blank`, `unresolved`; one search check per document against a phrase the operator or the document itself names.
- [ ] 4.3 Run it, write `report.md`, record the verdict in `experiment.json`. Fit no threshold on these documents.

## 5. Default flip (gate; only on a yes)

- [ ] 5.1 GATE G7: put the group 4 evidence to the operator and ask: "Remove the `document` unit and the 10% rule from the code (new small change `page-routing-default`), yes or no?"
- [ ] 5.2 If yes: write the proposal first, get approval, then apply it in its own worktree. Contents: default `page`; delete `ocr_required_by_gate` and `ocr_fallback_page_fraction`; an old `document` value in a config is refused with a message naming `page` (the gotcha-11 pattern); when the local OCR model or runtime is missing, flagged pages go straight to the worker engine, never back to native junk text; state the index identity effect (one re-index, accepted); no other settings.
- [ ] 5.3 If no: stop. Page mode stays a manual setting. Say so and move to group 6.

## 6. Close the image-based rescue gate (worktree `omrs-feat-image-based-rescue-gate`)

- [ ] 6.1 Open a PR for `feat/image-based-rescue-gate` into `v3` (Experiment 43's scripts and report). No merge unasked.
- [ ] 6.2 GATE G8 (first half): post the drafted comment on issue #161 (text in the handoff, section 4)? Only on a yes.
- [ ] 6.3 After the operator merges the PR, archive the change `image-based-rescue-gate`.
- [ ] 6.4 GATE G8 (second half): ask whether to run the judge follow-up on new documents (the confirmation experiment named in `document-reading-routers`). Do not start proposals A, B or C without the operator's word.

## 7. `paddleocr-vl-llamacpp-backend` (parked until group 2 merged)

- [ ] 7.1 Only after group 2 merged: follow `openspec/changes/paddleocr-vl-llamacpp-backend/tasks.md` in its own worktree, with its own gates (upload approval with the file size stated, the 25 C5 pages review, download approval). PR into `v3`, no merge unasked.

## Not in this flow (leave parked)

`ordered-reader-and-ocr-lists`, `non-latin-script-routing`, `document-reading-routers`; Experiment 44; Experiments 35 and 35a (RunPod CUDA: external server through `OCR_RUNTIME_URL`, `parity_check.py` first); the Ollama and MLX `model`-field runs beyond the small commit in group 2. Do not start any of these unless the operator asks.

## Completion

This change is complete when groups 0 to 7 are done or the operator redirects the flow. It archives with no spec sync (nothing to sync).
