# Tasks: Experiment 47, document router confirmation

**Start gate:** section 3 onwards starts only after every task in section 2 is done. No router scores a page before section 5. Work in the sibling worktree on branch `feat/experiment-47-router-confirmation`.

## 1. Plan and harness (pre-registration)

- [x] 1.1 Create the folder with `omrs experiments new router-confirmation` (number 47, Confirmatory, optimisation). Verify: `experiment.json` says `PLANNED`.
- [x] 1.2 Write `protocol.md` and `plan.json` with DRAFT hypotheses, gates, stop rules and set-check minimums, and the frozen threshold 0.172 with its Experiment 43 source hash. Verify: `omrs experiments check` reports no error.
- [x] 1.3 Write the harness on the shipped router path (`prepare_inputs.py`, `label_pages.py`, `score_router.py`, `analysis.py`, `exp47_io.py`). Verify: the tests call `run_rules` and `build_page_judge` with a mock transport; no `src/` change.
- [x] 1.4 Fix the 11 points of issue #171, each with a test that fails without the fix and a mutation check. Verify: `uv run --no-sync pytest experiments/47-router-confirmation-2026-11-05 experiments/_lib -q` passes.
- [x] 1.5 Validate this change. Verify: `openspec validate experiment-47-router-confirmation --strict` and `openspec validate --all --strict` pass.
- [x] 1.6 Commit `protocol.md`, `plan.json`, the harness and this change before any download or score. Verify: `git log` shows the commit before any `corpus/` or `output/` file exists.

## 2. Operator decisions

- [x] 2.1 OD1: choose gate option A or B (design D5). Approve the hypotheses, gates, stop rules and set-check minimums. Verify: a dated `decision_register` entry; with option A, drop the MODIFIED pass-rule block and change the plan gates first.
- [x] 2.2 OD2: approve the shortlist and fill `corpus_manifest.json`. Verify: `uv run --no-sync python prepare_inputs.py --validate` prints "manifest valid".
- [x] 2.3 OD3: approve the labelling method and the review rule (design D4). Verify: a dated entry.
- [x] 2.4 OD4: decide on the hosted reference arm (design D7). Verify: a dated entry with scope `hosted_reference_arm`, or the entry stays `NOT REQUESTED`.
- [x] 2.5 Commit the approved `plan.json`. No run exists yet, so this is not an amendment. Verify: `git status` shows `plan.json` clean.

## 3. Inputs and labels (local only)

- [x] 3.1 Download each PDF into `corpus/`. Run `prepare_inputs.py`. Verify: `output/inputs.json` holds every document; `git check-ignore` covers `output/.private/` and `corpus/`.
- [x] 3.2 Make local references with `label_pages.py references --resume`. Verify: `output/reference_state.json` has one `ok` entry per page, or each failure is named.
- [x] 3.3 Make labels with `label_pages.py labels`. Verify: `output/labels.json` and `output/set_check.json` exist; the set check passes, or stop and amend.
- [x] 3.4 Label review in `output/label_review.json` by the coding agent (amendment A1, 2026-11-05: the operator does not review labels by eye). Verify: every verdict set; 3 or fewer disagreements, or stop and amend.
- [x] 3.5 Commit the labels, the review and the set check. Verify: committed before any `scores_*.json` exists.

## 4. Runtime check

- [x] 4.1 Run `score_router.py --arm clef_router --check`. Verify: `output/runtime_check_clef_router.json` passes R1 to R6.

## 5. Scoring

- [x] 5.1 Speed trial: `score_router.py --arm clef_router --limit 2`. Verify: no stop rule fired.
- [x] 5.2 All pages: `score_router.py --arm clef_router --resume`. Verify: every document in `scores_clef_router.json`, no failures left.
- [x] 5.3 Hosted reference, only with OD4 approval: tasks 4.1, 5.1 and 5.2 with `--arm jev_router`.

## 6. Analysis and report

- [x] 6.1 Run `analysis.py`. Verify: `output/summary.json` has a verdict, or names each gap.
- [x] 6.2 Write `report.md` from the template; set `status` and `finding` in `experiment.json`. Verify: `omrs experiments check` and `omrs experiments index --write`.
- [x] 6.3 Follow the cleanup procedure (protocol section 8). Verify: the copy receipt holds a SHA-256 per file.
- [ ] 6.4 Record the G7 result in `doc-reading-master-flow`. Close issue #171 with a link to this change.
