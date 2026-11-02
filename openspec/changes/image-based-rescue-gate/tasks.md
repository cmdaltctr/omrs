# Tasks: Experiment 43, image-based check on rescued PDF text

**Start gate:** no page is scored before tasks 1.1 to 1.4 are done. No page image goes to a hosted service before task 1.5 is done. Stage 2 documents are not downloaded before 1.3. Run in a sibling worktree `omrs-feat-image-based-rescue-gate`, branch `feat/image-based-rescue-gate`, forked from `v3`. Large files stay outside git.

## 1. Plan and operator decisions

- [ ] 1.1 Scaffold `experiments/43-image-rescue-gate-2026-11-02/` with `protocol.md`, `plan.json` (status `planned`) and `experiment.json`, and remove any hold on number 43. Verify: `omrs experiments check` passes and `git log` shows the commit before any `output/` or `corpus/` file exists.
- [ ] 1.2 Write the question wordings (at most three), the page text head (2,000 characters), the render start values (150 DPI, 1,568 px long side) and the gate rules into `protocol.md` and `plan.json`. Verify: both files hold every item of design D1 and D4, and the commit precedes task 2.1.
- [ ] 1.3 Operator records the decisions of design D9 in `plan.json` `decision_register` with dates: gate priority, Stage 2 download approval, dots.mocr as second reference, and approval of the hosted Jev image arm with the documents allowed to leave the machine. Verify: four dated entries exist.
- [ ] 1.4 Operator approves the Stage 2 source list and selection procedure (seeded), with the handwriting share. Verify: `sourcing.procedure` and `sourcing.seed` are set and dated in `plan.json`.
- [ ] 1.5 Record the hosted Jev facts of design D10 in `plan.json` under `hosted_control`: pinned model id `jev-1.14.0`, endpoint, opt-in header, image limits, price, the date the docs were read, and the approved document list by name. The default list holds open-licence documents only, without `rf06` and `rf07`. Verify: a check script reads `plan.json`, prints the approved list and the pinned id, and fails if `rf06` or `rf07` is on the list without a dated operator entry naming them.

## 2. Runtime checks

- [ ] 2.1 Record the Clef-Flash files and the llama.cpp build in `plan.json`: build b11941, SHA-256 of `Clef-Flash-Q8_0.gguf` (`25f801e2…`) and of `mmproj-Clef-Flash-Q8_0.gguf` (`9dd8bc27…`), revision `a5a18a6e`. Verify: a script recomputes both hashes from `~/Development/DATA/omrs/ocr-models/clef-flash/` and prints a match, and prints a mismatch for a temporary copy with one byte changed.
- [ ] 2.2 Start `llama-server` on `127.0.0.1` with both files and send the two-request smoke test (right text, wrong text, same page image) in the form `/v1/systemone` accepts. Verify: the two `P(yes)` values differ in the expected direction by the margin set in `protocol.md`. Repeat without the projector file and verify that the run stops before any scoring.
- [ ] 2.3 Time 40 fixed pages one request at a time with nothing else on the GPU, and check the image token settings (design D4). Verify: `output/speed.json` holds median, mean and 95th percentile seconds per page, the flags used, and 0 failed requests.
- [ ] 2.4 Add a record in `DATA_LOCATIONS.md` for the Clef-Flash folder with both SHA-256 values and the revision. Verify: the entry exists and a second hash run matches it.

## 3. Stage 1 labels (Experiment 38 and 42 documents)

- [ ] 3.1 Locate the frozen inputs for the 40 Experiment 38 and 68 Experiment 42 documents (page renders, Experiment 33 references, rescue text, labels). Run `freeze.py --check` of Experiments 33, 38 and 42. Verify: all three print `freeze verified`, and a missing input stops the run with a named path.
- [ ] 3.2 List the pages that need a second reference (pages labelled `ambiguous` plus every page of the handwritten documents named in `protocol.md`). Verify: `output/second_ref_pages.json` holds the list, the count per document, and a recount by a separate script matches.
- [ ] 3.3 Transcribe those pages with dots.mocr on this machine through the engine from change `dots-mocr-llamacpp-backend`, with checkpoints and `--resume`. Verify: one transcription per listed page, engine and build recorded, no network call in the run log.
- [ ] 3.4 Score the second transcription with the Experiment 33 token rule and write the Stage 1 labels. Verify: `output/labels_stage1.json` marks each relabelled and each excluded page, and the report table counts match a recount.

## 4. Stage 1 scoring and freeze

- [ ] 4.1 Write the scoring script. It sends the image and text head for each labelled page, checkpoints after each page, writes atomically, and sends one request at a time. Verify: a unit test with a fake server shows the request holds the image and the text head, and a test with a broken request fails.
- [ ] 4.2 Write `jev_hosted_images.py`, reusing the key, retry and drift pattern of the Experiment 38 `jev_hosted.py`. It sends the same PNG, text head and wording as task 4.1, pins `jev-1.14.0`, sends one request at a time, checkpoints after each page and refuses pages from documents not on the approved list. Verify: unit tests with a fake server show the request shape (`assets` map with one base64 PNG, `TypeSafe-Danger-Zone-Images: true` header, Bearer key, `noul` question), that the key appears in no output, log or error text, that a returned model id other than `jev-1.14.0` stops the run, and that a page from an unapproved document is not sent. Each test fails when its check is removed from the script.
- [ ] 4.3 Score Stage 1 pages for each wording. Verify: every page has one score per wording, the failed-request count is stated, and the run resumes after an interrupt without re-scoring.
- [ ] 4.4 Run the word check (candidate A, code unchanged) on the same pages. Verify: its scores on the Experiment 38 documents equal the committed Experiment 38 values.
- [ ] 4.5 Run the hosted control on the Stage 1 pages of approved documents, for each wording. Verify: every sent page has one score per wording and a recorded model id equal to `jev-1.14.0`, no page of an unapproved document appears in the run log, and `output/hosted_usage.json` holds input tokens per page and the total cost.
- [ ] 4.6 Pick the wording from the local Treatment scores and fit the threshold by the Experiment 38 equal-cost rule on Stage 1 healthy pages. Fit the hosted control threshold by the same rule on its approved pages with the same wording. Write the wording, both thresholds, the render settings and the Stage 2 hosted cost limit to `plan.json` under a dated amendment, then commit. Verify: the commit precedes any Stage 2 file under `corpus/`, and the wording choice does not read hosted scores.

## 5. Stage 2 corpus and labels

- [ ] 5.1 Write `prepare_corpus.py` and `sources.json` that follow the approved procedure. Download into gitignored `corpus/`. Verify: `git check-ignore` covers the corpus, renders and page text, and no document matches an Experiment 33, 38 or 42 document.
- [ ] 5.2 Render pages, make the Experiment 33 reference transcriptions (local or approved) and extract the rescue text with the shipped LiteParse and pypdf adapters. Verify: one reference and one rescue text per page, with tool versions recorded.
- [ ] 5.3 Run the second reference on handwritten and ambiguous pages and assign Stage 2 labels. Verify: `output/labels_stage2.json` holds every document, exclusions per document class are listed, and any class above 30% excluded is named in `output/set_check.json`.
- [ ] 5.4 Check every target of design D3 (at least 1,000 healthy pages, junk layers from at least six documents, no document above 15% of junk pages, minimum handwritten documents from `protocol.md`). Verify: `output/set_check.json` lists each target and its count. If a target is missed, stop and record an amendment.
- [ ] 5.5 Operator reviews the stratified label sample (size and error bound set in 1.2) against the page images. Verify: the error rate is within the bound in `output/label_check.json`. Otherwise stop and amend.
- [ ] 5.6 Write `freeze.py` for this experiment and commit the frozen hashes. Verify: `freeze.py --check` prints `freeze verified`, and fails after one label is edited in a temporary copy.

## 6. Stage 2 scoring and analysis

- [ ] 6.1 Score the control, the word check and the treatment on Stage 2 pages with the frozen wording and threshold. Verify: the threshold in the script equals `plan.json`, every page has all scores, and the failed-request count is stated.
- [ ] 6.2 Run the hosted control on the Stage 2 pages of approved documents with the frozen wording and hosted threshold. Verify: every sent page has a score and a recorded model id equal to `jev-1.14.0`, the run stopped on no model change (or the report names the new id), the failed-request count is stated, and the cost stays within the limit in `plan.json`.
- [ ] 6.3 Write `analysis.py`: junk recall and healthy flag rate with Wilson intervals, document-cluster intervals, AUC, McNemar against the word check, G1 to G3, and the three routing rules of design D6 with OCR cost in pages. Compute the hosted control on its own pages and, for comparison, on the pages it shares with the Treatment, in a separate table. Verify: tests with a small fixed table give known values, a broken rule makes a test fail, and a test shows the verdict does not change when the hosted scores change.
- [ ] 6.4 Run the analysis. Verify: `output/summary.json` and `output/report_tables.md` exist, and every number in the report comes from them.

## 7. Report and hand-off

- [ ] 7.1 Write `report.md` with the verdict, the tables, the Stage 1 fit, label exclusions, speed and memory, limits, a hosted control table (approved documents and pages, model id, cost, results on shared pages), and a statement on `rf06` and `rf07` at document level and page level. Verify: the verdict follows the gate priority recorded in 1.3, and no statement uses a number absent from `summary.json`.
- [ ] 7.2 Update `experiment.json`, the experiments index and the `rescue-quality-evaluation` notes. Verify: `omrs experiments check` passes.
- [ ] 7.3 Comment on issue #161 with the verdict and the next step. Verify: the comment exists. On a PASS, the next step is a separate OpenSpec change and an ADR. On a FAIL, the issue stays open.
- [ ] 7.4 Run `openspec validate --all --strict`, the experiment tests and the fast test suite. Verify: all pass, and no file under `src/`, `pyproject.toml` or `uv.lock` changed.

## Workflow follow-up

- Open the pull request into `v3` and do not merge until told.
- On a PASS, propose the production change (design D8) and write the ADR.
- Remove the worktree after merge. Copy `output/` and `corpus/` to `~/Development/DATA/omrs/experiments/43-image-rescue-gate-2026-11-02/` first, and record the SHA-256 values.
