# Proposal: Experiment 47, confirm the shipped document router on new documents

## Why

PR #169 shipped document routers, off by default (ADR-110). The Settings page offers one template: local Clef-Flash Q8_0 with the page image, the question "Does the text match the text written or printed on the page image?", 2,000 characters and threshold 0.172. That threshold was fitted in Experiment 43 on the same 40 documents it was tested on. The app states a cost of about 3% of good pages sent to OCR and about 3.6 s per judged page. Neither number has been checked on documents the threshold has never seen. Gate G7 of the `doc-reading-master-flow` change asks for that check.

The Experiment 43 harness also has 11 open review points (issue #171). They must be fixed in the harness before this run.

## What Changes

- Add Experiment 47 (`experiments/47-router-confirmation-2026-11-05/`), Confirmatory, with `protocol.md` and `plan.json` committed before any page is scored.
- Run the shipped router code path, not a copy: the page scan, the page-rule pipeline, the `document_router` rule, the shipped `PageJudge`, adapter and page renderer, with an injected `EffectiveSettings` that holds the shipped template.
- Freeze the threshold at 0.172 from Experiment 43 (amendment A1), with the source file hash. No refit.
- Read a gitignored `corpus/` folder and a committed `corpus_manifest.json` (id, source address, licence, SHA-256, page range, JUNK or GOOD group). Refuse any document used in Experiments 33, 38, 42, 43 or 44.
- Label pages on the machine and freeze the labels before any router score: a local OCR reference, the Experiment 33 token rule, the frozen 0.50 and 0.80 class thresholds, and a label review (by the coding agent, amendment A1).
- Arms: control (no router), the shipped local router (treatment, decides), and the hosted Jev router as a reference (approved 2026-11-05) that never decides.
- Fix the 11 points of issue #171 in the new harness, each with a test. Add generic helpers to `experiments/_lib/run_safety.py` (lock before read, child server stopped on failed start, verdict withheld on an incomplete population, memory check that fails closed). No existing `_lib` function changes.
- Hypotheses, gates and stop rules approved by the operator on 2026-11-05: gate option B (design D5), the 19-document corpus, the local whole-page labels with the review done by the coding agent (amendment A1), and the hosted Jev reference arm, compared page by page with the local arm.
- No production code changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `rescue-quality-evaluation`: adds the rules for a router confirmation run (shipped code path, local labels frozen first, fail-closed runner, verdict withheld on an incomplete population, clean-checkout reproduction, cleanup procedure). Under gate option B it restates the confirmation pass rule against the stated cost. It makes the hosted image control optional in a confirmation run.

## Impact

- **Code:** experiment scripts under `experiments/47-router-confirmation-2026-11-05/` and one new module `experiments/_lib/run_safety.py` with its tests. No change under `src/`, `web/`, `pyproject.toml` or `uv.lock`.
- **Dependencies:** none.
- **Downloads:** the corpus PDFs, after operator approval of the manifest. The Experiment 43 model, projector and llama.cpp b11941 build are reused if their hashes match.
- **Cloud:** none by default. The hosted reference arm sends page images and text heads to TypeSafe only after a dated approval.
- **Data:** PDFs in gitignored `corpus/`; page text, images, references, logs and locks in `output/.private/` (gitignored by its own `.gitignore`). Committed files hold hashes, counts, scores and labels only.
- **Related records:** ADR-110, Experiment 43 (`plan.json` thresholds, amendment A1), Experiment 42 design D4 (labelling plan), issue #171, `doc-reading-master-flow` gate G7.
