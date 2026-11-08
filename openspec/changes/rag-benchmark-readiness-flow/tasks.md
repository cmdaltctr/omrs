# Tasks

The order is the operator's (2026-11-06, design D1). Do not reorder groups. Stop at every gate (design D3). Each group names the change whose own `tasks.md` carries the detail. Rules: design D4.

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

- [ ] 6.1 Update `experiment-35-full-document-rag-benchmark` for the router, Qwen3-Embedding-4B and the sweep's findings.
- [ ] 6.2 GATE G7: the operator approves the freeze and the run. Freeze `protocol.md` and `plan.json`, then run per its own tasks.

## 7. Close

- [ ] 7.1 Archive this change once groups 0 to 6 are done or explicitly parked by the operator.
