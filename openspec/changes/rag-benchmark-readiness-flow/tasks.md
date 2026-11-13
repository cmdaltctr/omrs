# Tasks

The order is the operator's (2026-11-06, design D1). Do not reorder groups. Exception: steps 7.1 and 7.2 run before task 6.11 (the freeze), as group 7 states. Stop at every gate (design D3). Each group names the change whose own `tasks.md` carries the detail. Rules: design D4.

## 0. Preflight

- [x] 0.1 Read-only checks: `git -C omrs-v3 log --oneline -1` matches `origin/v3`; the three proposal commits exist on their branches (`314e014e`, `19c837b8`, `ebdd2333`); `openspec validate --all --strict` passes on `v3` and on each branch; `git worktree list` shows the four worktrees of design Context. Report any drift before acting.
  - Done 2026-11-06. `v3` at `2d3d51da`, in sync, clean. All four validate strict (98, 100, 99, 99). Drift: Experiment 42 was already archived (`461c6ed6`); cuts branch 10 behind `v3`, router and panel 3 behind.
- [x] 0.2 Read the three proposals in full (proposal, design, tasks, specs).
- [x] 0.3 GATE G0: ask the operator for the open questions of each proposal (cuts: none left; page-routing-panel: 3 with defaults; one-llamacpp-router: 4 operator questions Q1 to Q4 plus 2 that spikes 1.2 and 1.4 answer; the earlier count of 11 was wrong), or "defaults ok". Record the answers in each change's `design.md` (operator decisions, dated) with `openspec-update-change`, validate, commit on its branch.
  - Operator answers 2026-11-06. Panel: pypdfium2 gets an Install button (existing extra install job); no "Learn more" link; add an ADR. Router: Q1 `managed`; Q2 no Chat model by default (Chat must not share the classification model; user picks one); Q3 4 models and 8,192 MiB, editable in the Settings llama.cpp Router panel; Q4 CUDA 12.8 else CPU, choosable on the Integrations card. Every decision is visible in the web GUI.

## 1. Apply `local-ocr-per-backend-cuts` (worktree `omrs-feat-local-ocr-per-backend-cuts`)

- [x] 1.1 Rebase onto current `v3`. Confirm toplevel and branch. `uv sync --frozen --extra web`.
- [x] 1.2 Apply the change (`/opsx:apply local-ocr-per-backend-cuts`), its tasks in order, tests first. Subagents only on non-colliding files; commit only after every agent stops.
- [x] 1.3 `./scripts/local_ci.sh`, `openspec validate --all --strict`, browser check at 1280 px and 390 px (Settings and Studio), PR into `v3`, CI green, CodeRabbit handled.
- [x] 1.4 GATE G1: the operator says merge. Merge, archive (sync specs), remove worktree after the Gotcha 15 copy. Do not touch the live app here (group 4).

## 2. Apply `one-llamacpp-router` (worktree `omrs-feat-one-llamacpp-router`)

- [x] 2.1 Rebase onto `v3` with group 1 merged. Check `tripwire-retirement-and-provider-symmetry` for overlap with the keys this change retires; follow its policy or record the conflict.
  - Done 2026-11-06: PR #184 merged (`d382a763`), `cuts-follow-ups` archived (`591e89af`), worktree removed. Router branch rebased onto `591e89af` with no conflict. Overlap: every key the router retires is flat, so under the tripwire policy (now in `config/legacy.py`) its entries persist; no conflict.
- [x] 2.2 Run the change's spike group (systemone forwarding, `/models?reload=1`, child processes, Linux CPU and CUDA builds) in scratch only. GATE G2: report results and the design path (decision models on the router, or on their own servers); the operator confirms.
- [x] 2.3 Apply the remaining tasks in order, tests first, including the automatic model download (task 6.2a) and the `.env` / conftest alignment.
- [x] 2.4 `./scripts/local_ci.sh`, strict validation, browser check (Router panel, Model runtimes, Get a model) at 1280 px and 390 px, PR, CI, CodeRabbit.
- [x] 2.5 GATE G3: the operator says merge. Merge, archive, remove worktree after Gotcha 15. Amend the pipeline sweep's design note only as a task in group 5.

## 3. Apply `page-routing-panel` (worktree `omrs-feat-page-routing-panel`; may run beside group 5)

- [x] 3.1 Rebase onto `v3` with groups 1 and 2 merged. Task 0.3 of the change: update the cut-box wording to step 4 of the panel.
- [x] 3.2 Apply its tasks in order, tests first, including `docs/guides/page-routing.md`.
- [x] 3.3 `./scripts/local_ci.sh`, strict validation, browser check at 1280 px and 390 px (Settings and Studio), PR, CI, CodeRabbit.
- [x] 3.4 GATE G4: the operator says merge. Merge, archive, remove worktree.

## 4. Live switch (operator approval needed)

- [x] 4.1 GATE G5: the operator approves touching the live app. No re-index: the live collections are test data (operator, 2026-11-07).
- [x] 4.2 Back up `~/.omrs/lancedb`, `~/.omrs/workspace/workspace.db` and `~/.config/omrs/omrs.jsonc` (dated copies). Reinstall the live app from `v3` with lock constraints and the `local-ocr-indra` extra.
- [x] 4.3 Router setup per `one-llamacpp-router` task group 13: provision the pinned router, model list (Qwen3-Embedding-4B, Qwen3-4B, Clef-Flash if a router is wanted), one router URL in `omrs.jsonc`, remove stale keys (`embed_model`, `ollama_classify_model`, old role URLs, `llamacpp_chat_server`). Local OCR: list `[pp-ocrv6-small, indra]`, cuts default, `ocr_non_latin_routing` off, Indra weights and `INDRA_OCR_MODEL_DIR`. Remove `OCR_LOCAL_MIN_CONFIDENCE` from the environment, `.env` and the login plist first (it now stops start-up), and press "Remove it" for `ocr_local_min_confidence` in Settings (archived `local-ocr-per-backend-cuts` group 10).
- [x] 4.4 Restart, check Integrations (router and models Ready, both local OCR backends Ready with cuts 0.92 and 0.94). Verify: one small test ingest gets model-chosen categories (not keyword fallback), a search finds its known phrase, and no Ollama process is needed.
- [x] 4.5 Delete the backups once verified (operator preference), record the new live state in agent memory.

## 5. Pipeline sweep on RunPod (worktree `omrs-v3-feat-pipeline-sweep-llamacpp`)

- [x] 5.1 Rebase the branch onto `v3` (222 commits behind on 2026-11-06). Renumber its experiment folder from `43-...` to the next free number (`omrs experiments new` rule); keep its frozen plan history honest with an amendment.
- [x] 5.2 Update the change's design and protocol: OMRS-managed router (`llama-server`, pinned b11941), not the Llama app's `llama serve`; Qwen3-Embedding-4B; RunPod edition (Linux CUDA build, `omrs llamacpp install`). Record as a dated amendment before any run.
- [x] 5.3 GATE G6: the operator approves the RunPod budget (load the `runpod` skills first; state the hourly price before creating any pod).
- [x] 5.4 Run the sweep, check its exit rule, copy outputs to `~/Development/DATA/omrs/`, write the report, PR, merge on the operator's word, archive.

## 6. Experiment 35

Follow the steps in order (design D5). "Exp 35 task N" means a task in `experiment-35-full-document-rag-benchmark/tasks.md`. "Archived 10.N" means a task of group 10 in `archive/2026-11-09-pre-exp35-harness-and-answer-fixes/tasks.md`. That group was archived unfinished, so this group now owns it. Tick both places when a step is done.

### A. Mac, free: get the data

- [x] 6.0 Preflight: GitHub CI is green on the `v3` head; `openspec validate --all --strict` passes; `git worktree list` shows no stale Exp 35 worktree.
  - Done 2026-11-09. `v3` at `4324475b`, in sync, clean. CI run 42660413729 success. Validate 105 passed, 0 failed. Worktrees: `omrs` (main), `omrs-v3`, `omrs-v4`; none for Exp 35.
- [x] 6.1 Exp 35 tasks 1.1, 1.2, 1.2a, 1.3, 1.6, 1.7 and 1.8: the sweep report path, the FinanceBench, FreshStack and BioASQ downloads with hashes, the table-loss count and its OCR choice, and the licences. Store the corpora under `~/Development/DATA/omrs/` with SHA-256. Verify: each corpus loads with the count its task names. The pod in step B needs all three corpora.
  - Done 2026-11-09. All three datasets were already on disk, so nothing was downloaded; hashes, counts and licences were rechecked (protocol 4.1 to 4.3). FinanceBench table loss 0.14% with the default reader, no OCR. FreshStack: one missing gold document added as an overlay (judgement log 17 and 18). HF revisions of the FreshStack export were never recorded (inference stated in the protocol).

### B. Pre-freeze pod session (archived group 10, design D13 of that change)

- [x] 6.2 GATE G7a: archived 10.1. Load the `runpod` skills, do the live price and stock read, check the keys and the LLM-AggreFact terms, quote the hourly price, and wait for the operator's go. Done 2026-11-10: operator said go; secure RTX 4090 walsi2c5gfb8xc at $0.89/h, created 14:56 UTC.
- [x] 6.3 Archived 10.2 and 10.3: one chained pod-side script (Part C timing on the three corpora, the 20-answer measurement, the full LLM-AggreFact split on Clef-Flash and then Granite Guardian). Copy the outputs back, check the copy, and delete the pod at once. Do not end a turn while the pod runs. Status 2026-11-10 22:00 UTC: Part C and both AggreFact runs done and copied back (prefreeze-pod/, SHA256SUMS); 20-answer measure still queued. Operator overrides "delete the pod": keep it, never idle (operator, 2026-11-10). Done 2026-11-11: all pod stages ran; outputs copied with SHA-256; pod deleted 00:51 UTC (operator kept it alive until then, then asked for deletion).
- [x] 6.4 Archived 10.4, from the Mac while the pod runs: GLM-5.3 on the full split (about $11) and the 120 Experiment 20 triples at reasoning `low`. Done 2026-11-10: GLM-5.3 76.9/85.1 on 29,320 rows (Z.AI Coding Plan); 120 triples at `low` recall 1.0, false rejection 0.0. Outputs in DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/prefreeze-glm/.
- [x] 6.5 Archived 10.5: score by leaderboard rules and apply the pass rule. If a model misses it, stop and report to the operator (D10 fallback of that change for Clef-Flash). Done 2026-11-10: GLM-5.3 76.9/85.1, Granite 75.7/83.2 (reproduced), Clef-Flash 67.8/71.9 (not reproduced); operator chose GLM-5.3 main, Granite second and fallback, Clef-Flash as data, no sampling (judgement items 40, 44-47; ADR-119).

### C. Mac, free: finish the inputs

- [ ] 6.6 Exp 35 tasks 1.4, 1.5, 1.9, 1.10 and 1.11. Use the step B timings for 1.4 and 1.5. Task 1.5 names the run machine.
- [x] 6.7 Update `experiment-35-full-document-rag-benchmark` with `openspec-update-change`: the router, Qwen3-Embedding-4B, the sweep's findings, and the step B numbers (measured scores, fixed threshold, agreement margin, pinned hosts). Done 2026-11-10: design D3, D4, D7, protocol 4.4 and 4.5, ADR-119 (PR #205).
  - Note (2026-11-08, from `pre-exp35-harness-and-answer-fixes`): also carry into the 35a plan the RunPod machine recommendation (that change's design D9: RTX 4090 secure, re-read price and stock at create time; corrects protocol section 7's 6 vCPU and 41 GB), the model matrix (design D12, including the answer model in `protocol.md:35`), and the one pre-freeze pod session (design D13, which holds the D6 timing step: Part C speeds and full-corpus token counts). Pin the commit of `experiments/_lib/` that 35a uses.

### D. Harness code

- [x] 6.8 Exp 35 section 2 (tasks 2.1 to 2.10) in its own worktree, tests first, `./scripts/local_ci.sh`, PR into `v3`, CI and CodeRabbit. GATE G7b: the operator says merge. Done 2026-11-11: PR #205 merged into v3 (3b0f3026) on the operator's instruction; pod scripts in PR #206 (e2b997ac).
- [ ] 6.9 Exp 35 task 3.4: the shareable example set. Verify: the release check from task 2.10 passes on it.

### E. Smoke run on the run machine

- [ ] 6.10 One smoke run that does archived 10.6 and Exp 35 task 4.1 together: a seeded sample of the factorial setups (Exp 35 amendment A1), 5 seeded questions per dataset, twice, through the claim checkers GLM-5.3 (main) and Clef-Flash (second), and `chat`. Granite Guardian is dropped. Run it on the machine that task 1.5 names. On a pod, quote the price first, and stop the pod after the smoke run (only its disk bills) until G7. Verify: zero errors, a verdict per strategy for every claim, complete call records, an identical second run, and the budget of Exp 35 task 4A.5 (ceiling $975) not exceeded on extrapolation. History: the first smoke run, under the old six-arm design, was done 2026-11-10/11 on pod walsi2c5gfb8xc: all 6 arms, 3 datasets, 5 questions, 2 runs, all three checkers; retrieval identical in 18 of 18 pairs. Report: DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/prefreeze-report-2026-11-11.md. Pod deleted. Open: the extrapolation check needs the budget of Exp 35 task 4A.5. The FreshStack-only smoke rerun is done (2026-11-11, pod 2elh5ji2og6d74, deleted): Clef-Flash passes the guard (ADR-119 A7), and its two harness errors are fixed in PR #207. Tick this task only when the factorial smoke run above passes every Verify check, and after 4A.5 and the zero-error recheck of FreshStack questions 77536364 and 77762811 (Exp 35 task 4.1 (c)). The old six-arm smoke run does not count for the factorial setups (PR 209 review, 2026-11-13).

### F. Freeze

- [ ] 6.11 GATE G7: the operator approves the freeze and the run budget. Exp 35 tasks 4.2 and 4.3: commit `protocol.md` and `plan.json`, then remove the DRAFT status. The OSF deposit (Exp 35 task 4B.6) is shared with group 7 step 7.3: one deposit holds Exp 35, A3 and the Part 2 protocol. Do not deposit before step 7.1 is done.

### G. Run and report

- [ ] 6.12 Exp 35 search and answer stages (tasks 4A.6 to 4A.8, which replace the old section 5 text): 72 search setups per dataset, run once each, then the 15 answer setups (12 crossed plus 3 token-matched, A3), 3 runs each. The step E pod was deleted, so create nine index pods (task 4A.6) and three replicate pods (task 4A.7) on the machine type that task 1.5 names. For each pod, quote the hourly price first, restore the models, corpora and pod scripts from `DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/`, check each file against its `SHA256SUMS` before the first arm, and delete the pod when its runs and its copy are done.
- [ ] 6.13 Exp 35 section 6 (tasks 6.1 to 6.3): statistics, `report.md`, `experiment.json` status.
- [ ] 6.14 Exp 35 section 7 (tasks 7.1 to 7.5): split, copy to `DATA/omrs/`, Zenodo, identifier search. Merge and archive Exp 35 on the operator's word.

## 7. Part 2 (RAGFlow on half B) and E1

Master plan: `docs/proposals/first-publication-benchmark.md`, "Order and gates", Step 3 and Step 4. "A3" means Exp 35 protocol section 0.12. Part 2 needs its own experiment number and protocol. Steps 7.1 and 7.2 run before the freeze (6.11). Steps 7.4 to 7.6 run after Exp 35 starts.

- [ ] 7.1 Reserve the Part 2 experiment number with `omrs experiments new`. Write its protocol: hypotheses C1 and C2 (Holm per dataset across C1 and C2, then 2 of 3 core datasets; Legal exploratory; C2 exploratory if no correctness measure passes kappa 0.60), the fairness rules of the proposal Step 3, the defaults row, the human labels drawn from both systems, and a pointer to A3. Verify: `omrs experiments check` and `openspec validate --all --strict` pass.
- [ ] 7.2 Prepare RAGFlow before the freeze. Pin the release and the container digest. Connect it to the llama.cpp models through OpenAI-compatible endpoints. Time one index per dataset and record the GPU cost. Check that each FinanceBench chunk carries a page number on a seeded FinanceBench sample (the page-level gate of the Part 2 relevance unit: if RAGFlow returns no page for a chunk, the Part 2 primary unit falls back to the document for every question and both systems; the page-level result becomes a labelled sensitivity analysis). Repeat RAGFlow retrieval on a small seeded sample and report whether the ranked lists match. Send the configuration to the RAGFlow maintainers and log every reply. Verify: `protocol.md` of Part 2 holds each result. A blocker is recorded and reported, and no other model is substituted.
- [ ] 7.3 GATE G7 (shared with 6.11): OSF deposit at the Exp 35 freeze. One deposit holds the Exp 35 protocol and `plan.json`, amendment A3 and the Part 2 protocol (C1, C2). The operator does the deposit. Verify: the OSF link and the commit hash are in both protocols.
- [ ] 7.4 After the Exp 35 search stage is scored, apply A3 on half A: the embedder and reranker size from the three core datasets, then chunk size, reranker on or off and hybrid on or off. Freeze the chosen cell. Record its configuration hash on OSF before half B opens. Verify: the dated note in Exp 35 protocol section 0.12 exists before any half-B score for Part 2.
- [ ] 7.5 Run Part 2 on half B, once per system: the A3 cell and RAGFlow on the same shared models. RAGFlow evidence goes through the common OMRS answer harness (same prompt, answer model, 20,480-token budget). Run the defaults row beside it. Quote the pod price first and delete the pod when the copy is done. Verify: one table per dataset, separate from the Exp 35 tables, with paired confidence intervals.
- [ ] 7.6 E1: estimate the cost and set a ceiling for the full 511,962-document corpus. Pin the benchmark commit, the corpus revision and the leaderboard revision. Confirm the GPT-5.4 judging and submission procedure with Onyx. Run E1 only if the budget allows; E1 is the first item to drop. The answer model is GPT-5.4, as in the benchmark's own baselines, and E1 stays descriptive. Verify: the cost note and the ceiling exist before any E1 run.

## 8. Close

- [ ] 8.1 Archive this change once groups 0 to 7 are done or explicitly parked by the operator.
