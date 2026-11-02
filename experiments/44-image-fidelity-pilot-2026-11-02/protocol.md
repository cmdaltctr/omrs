# Experiment 44: Image fidelity question pilot

- **Folder**: `44-image-fidelity-pilot-2026-11-02`
- **Record**: [experiment.json](experiment.json) holds category, size and status.
- **Operator**: the OMRS maintainer, with a coding agent
- **Related**: OpenSpec change `image-based-rescue-gate` (Experiment 43, issue #161), Experiments 33, 38 and 42, ADR-066, ADR-074, ADR-103, TDR-024
- **Number**: the CLI gave this pilot 44. Number 43 is reserved in `reserved.json` for the large study.

## 1. Question

Given a page image and the rescued text of that page, does the model's yes/no answer to "Does the text match the text written or printed on the page image?" separate a junk text layer from a faithful one?

The decision: Experiment 43 starts with this wording and render settings, starts only after a runtime fix, or does not start as designed.

This is a small, cheap check before Experiment 43. It fits no threshold and changes no default.

## 2. Hypothesis

- **H1 (primary)**: on the local arm, the median P(yes) for faithful text minus the median P(yes) for wrong text is at least 0.5, over all 30 pages. P(yes) is the model's probability for the answer "yes".
- **H0 for H1**: the difference is below 0.5, or negative. The model then does not use the image to judge the text.
- **H2 (primary)**: on the local arm, P(yes) ranks faithful text above the junk layer on the 7 junk pages with AUC at least 0.9. AUC is the share of (faithful, junk) pairs where faithful text gets the higher P(yes). A tie counts as half.
- **H0 for H2**: AUC is below 0.9.
- **Decision rule**: see section 6.

## 3. What changes, what is measured, what stays fixed

| Changes (one thing) | Primary metric | Guardrail metric | Fixed |
| --- | --- | --- | --- |
| The text sent with the page image: faithful, wrong or junk | G1: median P(yes) faithful minus median P(yes) wrong. G2: AUC faithful vs junk | P(yes) for faithful text on healthy pages (reported, no gate) | Model, projector, build, question, render settings, text head, pages |

Fixed request settings:

| Item | Value |
| --- | --- |
| Question | `Does the text match the text written or printed on the page image?` |
| Request type | `noul`, options `["no", "yes"]`. Score: P(yes) |
| Text head | First 2,000 characters of the text variant, after Unicode NFC. No other cleaning |
| Render | PNG, 150 DPI, long side at most 1,600 px (scale down with Lanczos, keep aspect ratio) |
| Image tokens | `--image-min-tokens 4`, `--image-max-tokens 14400` if the projector accepts them, else server defaults. The run record names what ran |

Three text variants:

| Variant | Junk pages (7) | Healthy pages (23) |
| --- | --- | --- |
| Junk | The LiteParse text layer, the text the rescue chain returns today | Not scored |
| Faithful | dots.mocr transcription from the sibling worktree `omrs-feat-dots-mocr-llamacpp-backend` (`ocr-workers/engines/dots-mocr-llamacpp/smoke_evidence/parity-pages/`) | The page's own text layer from pdftotext |
| Wrong | Faithful text of the next page in the same group that comes from another document (cyclic) | Same rule, within the healthy group |

The wrong text for junk pages comes from the other archive document. It is a hard test, because both archives look alike.

## 4. Data

| Item | Value |
| --- | --- |
| Source | Experiment 33 corpus, `experiments/33-ocr-routing-natural-positive-2026-09-17/corpus/natural/`. A copy is in `~/Development/DATA/omrs/experiments/33-ocr-routing-natural-positive-2026-09-17/` |
| Unit | Page |
| Size | 30 pages: 7 junk, 23 healthy. 67 local requests, 46 hosted requests |
| Junk pages | `rf06` pages 29, 46, 50, 86 and `rf07` pages 6, 47, 49. Experiment 33 labels them `needs_ocr`. Their text layers are junk |
| Healthy pages | For each `bd`, `mx` and `tl` document: the lowest page above 1 with label `usable`, `r_best` at least 0.95 and at least 100 reference tokens. `tl06` has none. The 23 pages are listed in `plan.json` |
| Groups | One page per healthy document. Junk pages share two documents |
| Labels | Experiment 33 frozen labels (`labels.json`, `output/page_evidence.json`). SHA-256 values are in `plan.json` `frozen` |
| Already seen | All pages appear in Experiment 33. `rf06` page 29 is the issue #161 example. This pilot fits nothing, so earlier use does not bias it |

### Hosted arm rule

`rf06` and `rf07` hold named-person records. The hosted arm sees only the 23 healthy pages, all open licence (CC BY, US government work, US patent). Its wrong texts also come only from healthy pages. A hosted run on `rf06` or `rf07` needs a dated operator amendment in `plan.json` first. Without it, the hosted arm cannot measure G2.

## 5. Steps

Run every command from the repository root. No runner exists yet. A runner, when written, follows `references/eval-runner-pattern.md` and stays inside this folder.

1. Render the 30 pages to `corpus/renders/` with the fixed settings. Record each PNG's SHA-256.
2. Build the text variants into `output/variants.json`: junk (LiteParse), faithful, wrong. Check each faithful file against its SHA-256 in `plan.json`.
3. Start `llama-server` build 11941 on `127.0.0.1` with `--mmproj`, one slot, the arguments in `plan.json`.
4. Runtime check (before any score):
   1. R1: read `GET /props`. The build must be 11941.
   2. R2: call `verify_llamacpp_runtime`. It checks the build and the SHA-256 of `Clef-Flash-Q8_0.gguf`.
   3. R3: hash `mmproj-Clef-Flash-Q8_0.gguf` and compare it with `plan.json`. The shared check reads only the `--model` file. Confirm that the server command holds `--mmproj` with that file.
   4. R4: smoke test on `rf06` page 29. Send the faithful text and the wrong text. P(yes) for faithful must exceed P(yes) for wrong by at least 0.2.
   5. R5 (hosted arm only): the same smoke test on `bd01` page 2. Read the key from `TYPESAFE_API_KEY`. Never print the key.
5. Append a run record with `record_run_start` and `runtime=found.as_run_record()`.
6. Score arm A: 67 requests, one at a time. Save each result to `output/scores_local.jsonl`. Restart with `--resume`.
7. Score arm B: 46 requests on healthy pages only. Save to `output/scores_hosted.jsonl`.
8. Summarise into `output/summary.json`. Write `report.md`.

## 6. Analysis

- **Stats level**: basic. This is a 30-page pilot. The gates use point values.
- **G1**: median P(yes | faithful) minus median P(yes | wrong), on all 30 local pages. Gate: at least 0.5. Report the 95% paired bootstrap interval of the per-page difference (`_lib/stats.py` `paired_bootstrap_ci`, seed 0).
- **G2**: AUC of P(yes | faithful) against P(yes | junk) on the 7 junk pages (49 pairs). Gate: at least 0.9. Point value only, because 7 pages give a wide interval.
- **Hosted arm**: G1 on the 23 healthy pages. It is reported beside the local value. It does not decide.
- **Exploratory**: per-page tables, P(yes) for faithful healthy text, seconds per request.

| Outcome | Status | What it means for Experiment 43 |
| --- | --- | --- |
| G1 pass, G2 pass | PASS | Start Experiment 43 with this wording and these render settings as the Stage 1 starting point |
| G1 pass, G2 fail | FAIL | The model reads the image but misses junk layers. Revise the Experiment 43 plan before it starts |
| G1 fail, hosted G1 pass | FAIL | The local image path is broken. Fix the projector, token limits or build, then run this pilot again |
| G1 fail, hosted G1 fail | FAIL | The question does not work. Experiment 43 does not start as designed |

### Stop rules

1. Stop before any score if R1, R2 or R3 fails. Record the found value. A new build or file needs an amendment.
2. Stop before any score if R4 fails. The status stays PLANNED. Experiment 43 waits until the image path works.
3. Stop the hosted arm on a 401, 403 or quota error. The local arm continues.
4. Stop if more than 3 of the 67 local requests fail after 2 retries each. The result is INCONCLUSIVE.
5. Score each page and variant once. Do not rerun to improve a value.

## 7. Runtime

- **Purpose**: optimisation
- **Runtime under test**: no
- **Local models**: llama.cpp with public GGUF files only.

| Role | Repository | File | SHA-256 | llama.cpp build | Server arguments |
| --- | --- | --- | --- | --- | --- |
| Decision (image and text) | `ggml-org/Clef-Flash-GGUF` revision `a5a18a6e13bb36573a5f11385a1e7b9a0c868e9e` | `Clef-Flash-Q8_0.gguf` | `25f801e2a27610b0ccc0cb1558d7eda3d7a304e34e2c4a04e3079357ff7d906e` | 11941 | `--mmproj`, `--host 127.0.0.1`, `--parallel 1`, `-c 8192`, `-b 8192`, `-ub 8192`, temperature 0 |
| Projector | same repository and revision | `mmproj-Clef-Flash-Q8_0.gguf` | `9dd8bc279f57d33b0697d4d0fe900fe751a24c9e3d30ab90969d4714ffc0722d` | 11941 | loaded with `--mmproj` |

The files live in `~/Development/DATA/omrs/ocr-models/clef-flash/`, outside git.

- **Hosted reference**: TypeSafe `jev-latest` with image input (`api.typesafe.ai/v1/systemone`), arm B. The response model id is recorded per page. Healthy open-licence pages only.
- **Tolerance**: G1 and G2 may change by at most 0.05, and each per-page P(yes) by at most 0.02, and still count as the same result.
- **Live check**: the runner calls `verify_llamacpp_runtime` before the first score, and hashes the projector itself (R3). A mismatch stops the run.
