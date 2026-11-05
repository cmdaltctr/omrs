# Experiment 47: Document router confirmation on new documents

- **Folder**: `47-router-confirmation-2026-11-05`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Operator**: OMRS maintainer, with a coding agent
- **Related**: OpenSpec change `experiment-47-router-confirmation`, gate G7 of the `doc-reading-master-flow` change, issue #171, ADR-110, Experiments 33, 38, 42 and 43

> **Approved 2026-11-05.** The operator approved the hypotheses, gates (option B), stop rules, set-check minimums, corpus, labelling method and hosted reference arm on 2026-11-05. `plan.json` `decision_register` holds each dated approval. Amendment A1 (same date, before any router score): the coding agent does the label review, not the operator.

## 1. Question

On documents that no earlier experiment has seen, does the shipped document router send pages with a junk text layer to OCR and keep its stated cost on good pages?

The answer decides whether the guides can call the router confirmed on new documents (PASS). A FAIL keeps the router off by default and names the failed gate. Nothing in production changes here.

The stated cost comes from Experiment 43: about 3% of good pages sent to OCR by mistake (15 of 565, 2.7%) and about 3.6 s per judged page. The router works in page mode: a rejected page goes to OCR alone.

## 2. Hypothesis

- **H1 (primary)**: on pages the scan did not flag, the shipped router rejects at least 70% of junk pages and at most 5% of healthy pages.
- **H0**: it rejects fewer than 70% of the unflagged junk pages, or more than 5% of the unflagged healthy pages.
- **H2 (secondary)**: no JUNK-group document with an unflagged junk page is missed entirely, and the mean time per judged page is at most 5.0 s.
- **Decision rule**: PASS when the treatment arm passes G1 and G2 and every population is complete. FAIL when G1 or G2 fails. No verdict when a population is incomplete. G3 and G4 are reported as known costs. The control arm and the hosted reference never change the verdict.

## 3. What changes, what is measured, what stays fixed

| Changes (one thing) | Primary metrics | Guardrail metric | Fixed |
| --- | --- | --- | --- |
| No router (control) against the shipped router (treatment) | Junk pages rejected (of unflagged junk pages); healthy pages rejected (of unflagged healthy pages) | Seconds per judged page | Shipped code at the planning commit, template recipe, threshold 0.172, model file and build, labels |

The run calls the shipped code path. Nothing in the harness decides a page:

| Part | Shipped code |
| --- | --- |
| Page scan (the text the router reads) | `integrations/pdf/page_routing.page_evidence` (pdf-inspector page Markdown) |
| Page rules, in order | `integrations/pdf/page_rules/pipeline.run_rules` (blank, maths, non_latin, then `document_router` at order 40) |
| Judge: prompt, text head, request, threshold, checks | `compose_decision.build_page_judge` (`PageJudge`) and the `llamacpp` adapter |
| Page image | `integrations/pdf/page_images.render_page` (150 DPI, long side at most 1,568 px) |
| Settings | an injected `EffectiveSettings` with one decision model entry and the router template |

`exp47_io.RecordingJudge` passes each call to the shipped judge and writes down the answer. The template is the one the Settings page offers: question "Does the text match the text written or printed on the page image?", page image on, 2,000 characters, threshold 0.172. `score_router.py` checks it against `web/src/settings/routerWords.ts` before any request.

| Arm | What it is | Role |
| --- | --- | --- |
| Control | No router: the shipped default | baseline |
| `clef_router` | Local Clef-Flash Q8_0 with its projector, llama.cpp b11941, threshold 0.172 | treatment, decides the verdict |
| `jev_router` | Hosted TypeSafe `jev-1.14.0`, page image on, threshold 0.21 | reference, approved 2026-11-05 (scope `hosted_reference_arm`); compared page by page with `clef_router`; never decides |

**Threshold.** 0.172 is the shipped template value. It rounds the Experiment 43 value 0.17220524482651753 (amendment A1, fit input SHA-256 `5721f983...`). It is never refitted. Every scoring run checks it against the frozen Experiment 43 plan. The summary lists any page whose score falls between the two values.

**Differences from Experiment 43.** Experiment 43 judged LiteParse text of rescued documents with poppler renders. The shipped router judges pdf-inspector page Markdown of unflagged pages with the shipped renderer. This experiment tests the shipped path as it is, so these differences are part of what it confirms.

## 4. Data

| Item | Value |
| --- | --- |
| Source | 19 public-domain or open-licence PDFs (10 JUNK, 9 GOOD), 2 to 9 pages each, shortlisted by a separate agent and approved by the operator on 2026-11-05. Documents J1 to J4 have no rights statement and are treated as public domain by age (operator decision). J4 uses pages 9 to 16 only |
| Groups | JUNK: scans with a bad embedded text layer. GOOD: documents with a correct text layer |
| Manifest | `corpus_manifest.json` (committed): id, group, file, source address, licence, SHA-256, page range, language, title |
| Files | `corpus/` (gitignored, read only). Each PDF the manifest names is fetched from its source address and checked against its SHA-256 |
| Unit | Page (page-mode routing), then document for G3 |
| Overlap | None. `prepare_inputs.py` refuses a document whose SHA-256, file name or source address matches Experiments 33 or 42 (Experiments 38, 43 and 44 used the Experiment 33 documents) |
| Labels | Made locally and frozen before any router score (below) |

**Labels (approved 2026-11-05).** This reuses the labelling plan of the Experiment 42 design (D4), with one change for privacy.

1. A local OCR engine (dots-mocr through the shipped OCR routes) transcribes each page, one page per request, offline. No page text or image leaves the machine.
2. The Experiment 33 token rule (`build_labels.tokens` and `recall`, imported by path, SHA-256 pinned) scores the shipped page text against that reference.
3. Frozen classes (Experiments 38 and 42): `junk` below 0.50 with at least one text token, `healthy` at 0.80 or more, `grey` between (reported only), `excluded` when the reference failed, has fewer than 10 tokens, or the text layer has no tokens.
4. Change: Experiment 33 scored body text only, split from figure text by a hosted model. Here the reference is the whole-page local transcription. The operator approved this change on 2026-11-05.
5. Amendment A1 (2026-11-05, before any router score): the coding agent, not the operator, checks every junk and grey page and 15 seeded healthy pages. For each page it looks at the local page image, the page text the router reads and the dots-mocr reference. It records agree or disagree with the class in `output/label_review.json`. More than 3 class disagreements stop the run. The fix is an amendment before any score.
6. The set check needs at least 20 unflagged junk pages in 5 documents and 40 unflagged healthy pages in 8 documents. A miss makes the run INCONCLUSIVE before scoring.

## 5. Steps

Run each command from the experiment folder. Set `EXP47_LLAMA_SERVER` (the b11941 `llama-server`) and `EXP47_MODEL_DIR` (the folder with the model and projector files) for steps 4 and 5. Set `EXP47_OCR_WORKERS_DIR` for step 2.

1. Check the manifest: `uv run --no-sync python prepare_inputs.py --validate`
2. Scan and render: `uv run --no-sync python prepare_inputs.py` (after a stop, or in a fresh clone: `--resume`)
3. Local references: `uv run --no-sync python -u label_pages.py references --resume`
4. Labels: `uv run --no-sync python label_pages.py labels`. The coding agent fills `output/label_review.json` (amendment A1). Commit `labels.json`, `label_review.json` and `set_check.json`.
5. Runtime check (R1 to R6): `uv run --no-sync python score_router.py --arm clef_router --check`
6. Speed trial, 2 documents: `uv run --no-sync python score_router.py --arm clef_router --limit 2`
7. All pages: `uv run --no-sync python score_router.py --arm clef_router --resume`
8. Hosted reference (approved 2026-11-05): steps 5 to 7 with `--arm jev_router`
9. Summarise: `uv run --no-sync python analysis.py`

Each scoring run appends a line to `output/run-records.jsonl` before its first decision request, and replaces its checkpoint after every answer.

## 6. Analysis

- **Stats level**: basic. Counts and rates on a small set. `_lib/stats.py` has no interval for a single rate, and no new statistics code is written.
- **Populations**: unflagged junk pages and unflagged healthy pages. A page the scan flagged already goes to OCR. A page an earlier rule claimed (for example a maths page) goes to OCR without the router. Both leave the router populations and are reported.
- **Per arm**: junk pages rejected, healthy pages rejected, grey pages rejected, JUNK documents missed, seconds per judged page (first 2 answers left out), OCR seconds of the false rejects (pages x 38.2 s).
- **Gates (option B, approved 2026-11-05)**, treatment arm:

| Gate | Role | Pass when | Why it matters |
| --- | --- | --- | --- |
| G1 | primary | junk recall on unflagged junk pages >= 0.70 | Experiment 43 local arm: 62 of 89 junk pages (0.70) |
| G2 | primary | false-reject rate on unflagged healthy pages <= 0.05 | stated cost about 3%; 5% allows two pages in 40 |
| G3 | secondary | JUNK documents missed == 0 | each junk document reaches OCR for at least one page |
| G4 | secondary | seconds per judged page <= 5.0 | stated speed about 3.6 s |

- **Gate option (OD1, operator decision)**. On 2026-11-05 the operator chose option B: point estimates against the cost the app states. G1 and G2 decide the verdict. G3 and G4 are reported only. Option A is the pass rule the `rescue-quality-evaluation` spec holds today: junk recall at least 0.90 with the lower 95% bound at least 0.80, and a healthy flag rate at most 0.02 with the upper 95% bound at most 0.05. Option A needs an interval function in `_lib/stats.py` and a larger set (no false reject in about 73 healthy pages). The Experiment 43 numbers make a FAIL under option A likely. Option B needs the MODIFIED requirement in the OpenSpec change.
- **Per document**: the pages each document sends to OCR, their OCR seconds, and the 10% share and one-page views that the spec asks for. The router works in page mode, so these views do not decide.
- **Local against hosted**: `analysis.py` compares `clef_router` and `jev_router` page by page on the pages both scored: pages where both reject, where neither rejects, where only one rejects, the agreement rate, and a list of the pages where they differ with their class. The comparison never changes the verdict.
- **Verdict withheld**: `analysis.py` gives no verdict when a population is empty, a page has no score or a page failed.
- **Limit**: with 40 healthy pages, one page moves the rate by 2.5 points, so G2 is coarse. A PASS shows the router behaves as stated on this set. It does not give a narrow rate.

**Stop rules (approved 2026-11-05).** `plan.json` `stop_rules` holds the values. The code enforces each one (`exp47_io.StopRules`, `score_router.py`):

| Rule | Value |
| --- | --- |
| Before any request | every decision approved; threshold equals the frozen value; `plan.json` committed; labels frozen; a passing runtime check record for the same plan, inputs, labels, model and runner |
| Hosted cost | stop before the first request when the projected cost is over USD 1.00, or later when the cost so far is over it (USD 0.00022 per page, from Experiment 43) |
| Time | stop when the projected time for the pages left is over 2 hours, after 2 answers |
| Failures | stop when more than 5 answers fail in one run (INCONCLUSIVE); a resume asks only the failed pages again |
| Inputs | stop when a PDF, a page text or a page image differs from `inputs.json`, or the router status is not `ok` |
| Machine | stop when free memory is under 15% or `memory_pressure` prints no percentage; stop when another runner holds the lock |

**What each outcome means**:

- PASS: record the confirmation in the guides; a separate decision may follow on any default.
- FAIL: keep the router off by default; the report names the failed gate and pages.
- No verdict: finish the missing pages with `--resume`, then summarise again.

## 7. Runtime

- **Purpose**: optimisation
- **Runtime under test**: no
- **Local models**: llama.cpp with public GGUF files, the files and build of Experiment 43.

| Role | Repository | File | SHA-256 | llama.cpp build | Server arguments |
| --- | --- | --- | --- | --- | --- |
| Decision (image and text) | `ggml-org/Clef-Flash-GGUF` revision `a5a18a6e13bb36573a5f11385a1e7b9a0c868e9e` | `Clef-Flash-Q8_0.gguf` | `25f801e2a27610b0ccc0cb1558d7eda3d7a304e34e2c4a04e3079357ff7d906e` | 11941 | `--mmproj`, `--host 127.0.0.1`, `-np 1`, `-c 8192`, `-b 8192`, `-ub 8192` |
| Projector | same repository and revision | `mmproj-Clef-Flash-Q8_0.gguf` | `9dd8bc279f57d33b0697d4d0fe900fe751a24c9e3d30ab90969d4714ffc0722d` | 11941 | loaded with `--mmproj` |

- **Server**: `score_router.py` starts `llama-server` on 127.0.0.1:18447 and points an `external` decision model entry at it. When startup fails before `/health` answers, the runner stops the child process.
- **Runtime checks**: R1 build line, R2 `verify_llamacpp_runtime`, R3 projector hash, R4 the shipped checks (`test_decision_model`: quantisation, text probe, projector smoke test), R5 the shipped checks report `projector-not-loaded` without the projector, R6 loopback bind. The record is `output/runtime_check_<arm>.json`.
- **Hosted reference**: TypeSafe `jev-1.14.0`, key from `TYPESAFE_API_KEY` through `env://`. Approved 2026-11-05. The key is never printed or saved.
- **Tolerance**: each per-page P(yes) may change by at most 0.02 and still count as the same result.

## 8. Cleanup

Private files never leave the machine and are not committed. `output/.private/.gitignore` (`*`) keeps them out of git. After the report is final:

1. Copy the committed outputs and the private folder to `~/Development/DATA/omrs/experiments/47-router-confirmation-2026-11-05/`.
2. Record the SHA-256 of each copied file in `DATA/omrs/experiments/copy-receipt.json`. Check each copy against its hash.
3. Delete the page text: `output/.private/text/`.
4. Delete the page images: `output/.private/renders/`.
5. Delete the reference transcriptions: `output/.private/references/`.
6. Delete the server and engine logs: `output/.private/logs/`.
7. Delete the lock files: `output/.private/locks/`.
8. Keep `corpus/` until the worktree is removed, then delete it. The manifest names each source, so the PDFs can be fetched again.

Do not copy `.env`. Do not upload any of these files to a public host.
