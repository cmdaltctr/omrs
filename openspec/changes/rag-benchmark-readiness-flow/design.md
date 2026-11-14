# Design: master execution order to get OMRS ready for the full RAG benchmark

## Context

State on 2026-11-06 (verify against git and gh before acting):

| Item | Where | State |
| --- | --- | --- |
| `local-ocr-per-backend-cuts` | worktree `omrs-feat-local-ocr-per-backend-cuts` | proposal committed `314e014e`, not pushed, not built |
| `one-llamacpp-router` | worktree `omrs-feat-one-llamacpp-router` | proposal committed `19c837b8`, not pushed, not built |
| `page-routing-panel` | worktree `omrs-feat-page-routing-panel` | proposal committed `ebdd2333`, not pushed, not built |
| `pipeline-sweep-llamacpp` | worktree `omrs-v3-feat-pipeline-sweep-llamacpp` | 5 commits (`4cfcac5d`), not pushed, 222 behind `v3`; folder `43-pipeline-sweep-llamacpp-2026-11-01` clashes with the merged Experiment 43 |
| `experiment-35-full-document-rag-benchmark` | `v3` `openspec/changes/` | 3 of 42 tasks; DRAFT; publication, Confirmatory |
| Live app | `~/.omrs`, `~/.config/omrs/omrs.jsonc` | `v3` `36965b6f` installed; Llama app on 9931 serves Qwen3-Embedding-0.6B and Qwen3-0.6B (ctx 32768 pinned in `~/.config/llama/models.user.ini`); `llamacpp_chat_server` external; dots-mocr llama.cpp engine live |

## Decisions

### D1. The order

```
G0 preflight
   |
   v
1. local-ocr-per-backend-cuts  -- apply, PR, merge (G1), archive
   |
   v
2. one-llamacpp-router         -- spikes (G2), apply, PR, merge (G3), archive
   |
   +--------------------------------------+
   v                                      v
4. live switch (G5)                  3. page-routing-panel -- apply, PR, merge (G4)
   |                                    (can run beside 5)
   v
5. pipeline sweep on RunPod (G6)
   |
   v
6. Experiment 35: data, pre-freeze pod (G7a), harness (G7b),
   smoke run, freeze (G7), run, report (design D5)
   |
   v
7. Part 2 (RAGFlow on half B) and E1: protocol and RAGFlow set-up before
   the freeze, OSF deposit at G7, A3 on half A, run on half B, E1 last
```

The cuts change goes first because both other changes build on it (the panel shows its cut boxes; the router change lands after it and shares the re-index). The router goes before the panel because it is on the benchmark's critical path and both touch `workspace-settings` and `settings-file`: never two of these branches at once (rule of the archived master flow, task 4.4). The panel changes no result with defaults, so it may run beside the sweep.

### D2. No re-index

The cuts change and the router change each change the index identity. The operator decided on 2026-11-07 not to re-index: the live collections are test data. A collection used later is re-ingested when it is needed.

### D3. Gates

| Gate | Where | Operator decides |
| --- | --- | --- |
| G0 | 0.3 | Open questions of the three proposals (answer or "defaults ok") |
| G1 | 1.4 | Merge `local-ocr-per-backend-cuts` |
| G2 | 2.2 | Spike results of `one-llamacpp-router` (design path A or B) |
| G3 | 2.5 | Merge `one-llamacpp-router` |
| G4 | 3.4 | Merge `page-routing-panel` |
| G5 | 4.1 | Touch the live app |
| G6 | 5.3 | RunPod budget and start of the sweep |
| G7a | 6.2 | Pre-freeze pod session: quoted price, go |
| G7b | 6.8 | Merge the Exp 35 harness PR |
| G7 | 6.11 and 7.3 | Freeze Experiment 35, approve the run budget, and deposit the pre-registration (main file), the proposal, `protocol.md`, `plan.json` and the Part 2 protocol on OSF together |

### D4. Rules every group follows

- Read `AGENTS.md` first. One worktree per change, sibling of `omrs-v3`, forked from current `v3`.
- `uv sync --frozen --extra web`; commit and push with `uv run --no-sync git ...`.
- Tests first; confirm red; one mutation check per behaviour; never `git checkout <file>` or `git stash` to undo a mutation (copy to the scratchpad and back).
- Re-pin the tripwire only by test-ID diff.
- Bug rule (global AGENTS.md rule 6): score likelihood x impact; 4 or more fix now; 3 or below propose an issue and wait.
- `./scripts/local_ci.sh` before every PR; PR into `v3`; watch CI; CodeRabbit (CLI when the hosted review skips); never merge without the operator's word.
- Before `git worktree remove`, copy preserve-class gitignored data to `~/Development/DATA/omrs/` with SHA-256 values (Gotcha 15).
- Plain British English, short sentences, no em dashes, no personal identifiers or `/Users/` paths in anything pushed.

### D5. Experiment 35 order (operator, 2026-11-09)

Group 6 runs in seven steps, A to G:

```
A. Mac: section 1 downloads, licences, table-loss count
   |
B. Pre-freeze pod (G7a): Part C timing, 20 answers, LLM-AggreFact
   |   (Mac at the same time: GLM-5.3 split)
C. Mac: rest of section 1; write the pod numbers into Exp 35 (6.7)
   |
D. Section 2 harness, PR (G7b)
   |
E. Arm smoke run on the run machine; pod stopped after it
   |
E2. A4 pre-freeze items: FreshStack full corpus pin and timing,
   |   halves and MDE pilot on half A, P1 to P16, open items O1 to O7
   |   (with Part 2 steps 7.1, 7.2 and 7.2a)
F. Freeze (G7)
   |
G. Search stage; score half A; selection.json; OSF time-stamp of the
   hash; score half B; replicate pods; section 6 report; section 7 release
```

Reasons:

- The downloads go before the pod. The pod's Part C timing counts tokens on all three corpora, so it needs them.
- The arm smoke run goes after the harness. Every arm needs the section 2 code. Archived task 10.6 and Exp 35 task 4.1 are the same check, so one run does both.
- The smoke run uses the run machine. Corpus and indexes stay in place for section 5. A stopped pod bills only its disk while the operator decides at G7.
- `pre-exp35-harness-and-answer-fixes` was archived with group 10 open. This group owns those tasks now. The detail stays in that change's design D13.
- Step E2 (added 2026-11-14, amendment A4) holds the pre-freeze items of `preregistration.md` section 23. The pilot and every pre-freeze sample drawn after the halves exist come from half A, so the halves are written first; earlier samples are listed with their halves (P12). Step G follows the order of work of pre-registration section 14.2: no half-B score exists before the configuration hash is time-stamped on OSF.

### D6. Amendment A4: the pre-registration governs; deviation policy (2026-11-14)

A publication-grade methods review (2026-11-13) gave 30 findings, F1 to F30. The user approved every recommended fix on 2026-11-14. The file `experiments/35-full-rag-benchmark-2026-11-01/preregistration.md` governs Experiment 35 and is the main file of the OSF deposit. The proposal stays the master plan for scope, order of work, Part 2 and E1. For Part 2 and E1, pre-registration section 18 wins over the proposal on the points it fixes; the proposal governs every other fact until the Part 2 protocol is frozen, and then the Part 2 protocol governs. The step 7.2a cost decision, recorded before any half-B score, fixes the Part 2 estimand: "selected OMRS against selected RAGFlow" if the matched search runs, else "selected OMRS against default RAGFlow". `exp35-main-run-readiness` design D38 and its task group 16 build the design; group 6 (steps 6.10a to 6.10d and 6.12 to 6.14) and group 7 (steps 7.1 to 7.6, with 7.2a added) of this change order it.

- **Deviation policy.** After the freeze, every change is a dated, numbered deviation. The report lists each with its reason, its time (before or after seeing the affected data) and its effect on each claim. Each goes into `plan.json` `amendments` and is uploaded to the OSF project. A run on another llama.cpp build needs a deviation first. Part 2 states the same policy in its protocol.
- **Budget.** Experiment 35: about $730 (estimate), ceiling $975, with the results-blind drop order of pre-registration section 17: (1) Legal RAG Bench answer generation, (2) the length-controlled check, (3) the closed-book run with the RAG prompt; then stop. A run with every confirmatory item done is "complete with registered drops". Part 2 and E1 get their own estimates and ceilings at step 7.2a; E1 is not in the Experiment 35 drop order.
- **Reporting.** The Experiment 35 report holds the items of pre-registration section 21 (decisions with "not testable" marks, unjudged share, sensitivity tables, compute table with every pre-freeze pod, returned model IDs, deviation log). The Part 2 report holds its own release table and maintainer correspondence log.

## Risks

- The router spikes (systemone forwarding, reload endpoint, child processes, Linux GPU build) can change the router design. Gate G2 stops for that.
- `tripwire-retirement-and-provider-symmetry` rewrites retirement policy; the router change retires several keys. Check before group 2.
- The sweep branch is 222 commits behind and predates every change above. Expect a careful rebase and a renumbered folder.
