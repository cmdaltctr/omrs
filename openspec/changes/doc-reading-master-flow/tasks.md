# Tasks

The order below is the operator's confirmed order (2026-11-02). Do not reorder groups. Stop at every gate (design D5). Each group names the change whose own tasks carry the detail. Rules live in the repo `AGENTS.md` and the handoff `2026-11-02-doc-reading-and-dots-mocr-handoff.md` section 1.

## 1. Apply `skip-blank-pages-before-worker` (new worktree `omrs-feat-skip-blank-pages` from `v3`)

- [x] 1.1 Fork the worktree from `v3`, confirm `git rev-parse --show-toplevel` and `git branch --show-current`, prepare with `uv sync --frozen --extra web`, then apply the change (`/opsx:apply skip-blank-pages-before-worker`), following its tasks 1 to 3 (blank test module, fifth count, index identity), tests first.
- [x] 1.2 Its task 4.1 verifies on the PyTorch `dots-mocr` engine (on `v3`), not `dots-mocr-llamacpp` (which reaches `v3` only in group 6): record a same-engine baseline of the 10-page `rf06` extract (design D4) before the change, then verify 4 pages count `ocr_pages_blank`, 0 unresolved, no engine call for the blank pages, the other 6 pages identical to the baseline, engine seconds saved stated.
- [x] 1.3 Task 4.2: run the blank test on all 40 Experiment 33 documents (design expects 37 of 701 flagged pages skipped; no page with 3 or more reference characters skipped).
- [x] 1.4 Ask before `./scripts/local_ci.sh`; run `openspec validate skip-blank-pages-before-worker --strict`; open a PR into `v3`. GATE G1: the operator says merge.

## 2. `page-routing-default`: page mode becomes the default, document mode goes (write, then apply)

- [x] 2.1 Write the proposal (`openspec-propose`, new change `page-routing-default`), and get the operator's approval before applying. Contents: default `page`; delete `ocr_required_by_gate` and `ocr_fallback_page_fraction`; an old `document` value in a config is refused with a message naming `page` (the gotcha-11 pattern); when the local OCR model or runtime is missing, flagged pages go straight to the worker engine, never back to native junk text; state the index identity effect (one re-index, accepted); no other settings. Design D2 records the operator decision that authorises flipping before any new-document re-test.
- [x] 2.2 Apply it in its own worktree `omrs-feat-page-routing-default`, tests first: the default resolves to `page`; a `document` value is refused with the message; the gate function and the fraction setting are gone; the missing-local-OCR path sends flagged pages to the worker engine.
- [x] 2.3 Drift check: grep `docs/guides/` for `document` unit and the 10% rule, fix what the change makes wrong. Ask before `./scripts/local_ci.sh`; validate strict; PR into `v3`. GATE G2: the operator says merge.
- [ ] 2.4 (Operator) After the merge reaches the live app: add `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` (design D3) to the live app's environment. No manual routing key is needed any more; `page` is the default.

## 3. Re-run #161: redo dots-mocr task 3.4 with page mode (worktree `omrs-feat-dots-mocr-llamacpp-backend`)

- [ ] 3.1 Read that change's `tasks.md` (task 3.4), `design.md` D9, and `ocr-workers/engines/dots-mocr-llamacpp/SMOKE_RESULTS.md`. Confirm worktree and branch. `uv sync --frozen --extra web`.
- [ ] 3.2 Scratch environment: scratch `OMRS_CONFIG_DIR`, `OMRS_STATE_DIR`, `LANCEDB_URI`; `ocr_routing_unit=page` in the scratch config; engine `dots-mocr-llamacpp`; set `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH`; after the first pages, grep the log for "Local OCR tier unavailable".
- [ ] 3.3 GATE G3: warn the operator: about 1 to 1.5 hours of GPU. Blank pages add time; the blank-skip change is not in this worktree.
- [ ] 3.4 Ingest `eq01`, `io06`, `rf06` with the CLI. Pass: a search finds a known phrase from an OCR page of each PDF, including "Antonia Cruz Gonzalez" and "Sevilla 17 de Agosto" from `rf06` page 29; KaTeX 0.16.22 renders `eq01` formulas with 0 errors.
- [ ] 3.5 Record the run in `SMOKE_RESULTS.md` (amend the task 3.4 row), tick 3.4 only if all pass, and report the three search results. A pass here is the evidence group 6's gate asks for.

## 4. Proposals A, B, C (one at a time; fresh fork from `v3` after each merge)

- [ ] 4.1 `ordered-reader-and-ocr-lists` in `omrs-feat-ordered-reader-and-ocr-lists`. Apply, verify per its tasks, ask before `./scripts/local_ci.sh`, validate strict, PR into `v3`. GATE G4: the operator says merge.
- [ ] 4.2 `non-latin-script-routing` in `omrs-feat-non-latin-script-routing`, forked fresh from the merged `v3`. Same gates (G5).
- [ ] 4.3 `document-reading-routers` in `omrs-feat-document-reading-routers`, forked fresh from the merged `v3`. Its ADR-110 index line and the `cloudflare` and `ollama` kinds are as already written and answered. Same gates (G6). After its merge, GATE G7: ask whether to run the judge confirmation experiment on new documents.
- [ ] 4.4 Remember: these changes and groups 1 and 2 all touch `pdf-reader` and related specs. Never two branches at once; rebase deltas when a fork lands on a changed spec.

## 5. Close out the image-based rescue gate (no build work)

- [ ] 5.1 Open a PR for `feat/image-based-rescue-gate` into `v3` (Experiment 43's scripts and report). No merge unasked. GATE G8: the operator says merge.
- [ ] 5.2 GATE G9: post the drafted comment on issue #161 (text in the handoff, section 4)? Only on a yes.
- [ ] 5.3 After the merge, archive the change `image-based-rescue-gate`, noting in the archive that page-as-default plus C's routers supersede its design; the record stays as evidence.

## 6. Finish the dots-mocr change: task 3.7 (worktree `omrs-feat-dots-mocr-llamacpp-backend`)

- [ ] 6.1 GATE G10: the operator gives "3.7 confirmed" with a date. Group 3's pass is the evidence. Without it, stop.
- [ ] 6.2 Do group 4 exactly as already decided (change `tasks.md` 4.1 to 4.4): delete the PyTorch engine `ocr-workers/engines/dots-mocr`; rename `dots-mocr-llamacpp` to `dots-mocr` keeping `backend_id` `dots_mocr_llamacpp`; update tests, docs and the tripwire (pin moves from 9859); add a `model` name to the engine request as a separate small commit, test first; write the ADR "dots.mocr runs on llama.cpp" after the cut-over with a dated note on ADR-072, recording Ollama 7 of 10, MLX 3 of 10, llama.cpp 22 of 22 identical pages.
- [ ] 6.3 STOP before task 4.5. GATE G11: the operator approves touching the live workers folder `~/.omrs/ocr-workers` and restarting the app.
- [ ] 6.4 Group 5: rebase the branch onto the merged `v3` (it now carries groups 1, 2 and A/B/C; the engine rename may touch references those changes introduced, so re-run their tests after the rebase). Ask before `./scripts/local_ci.sh`; run `openspec validate --all --strict`; PR into `v3`. GATE G12: the operator says merge.

## Not in this flow (leave parked)

`paddleocr-vl-llamacpp-backend` (its own gate: only after group 6 merges); Experiment 44; Experiments 35 and 35a (RunPod CUDA: external server through `OCR_RUNTIME_URL`, `parity_check.py` first); the Ollama and MLX `model`-field runs beyond the small commit in group 6. Do not start any of these unless the operator asks.

## Completion

This change is complete when groups 1 to 6 are done or the operator redirects the flow. It archives with no spec sync (nothing to sync).
