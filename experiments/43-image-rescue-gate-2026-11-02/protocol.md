# Experiment 43: Image-based check on rescued PDF text

- **Folder**: `43-image-rescue-gate-2026-11-02`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Operator**: OMRS maintainer, with a coding agent
- **Related**: OpenSpec change `image-based-rescue-gate`, issue #161, TDR-024, ADR-066, ADR-074, ADR-103, Experiments 33, 38, 42 and 44
- **Number**: the CLI gave 45. Number 43 was reserved in `reserved.json` for this change, so the new folder was renamed to 43 before any commit.

## 1. Question

Does an image-based check route `rf06` and `rf07` to OCR without newly routing any document labelled `usable`?

The answer decides whether a follow-up change confirms the check on new documents (PASS), or whether issue #161 stays open (FAIL).

The check gives the model the page image and the rescued text of the page. It asks one question about fidelity to the page. It never asks about readability.

## 2. Hypothesis

- **H1 (primary)**: with the local Clef-Flash Q8_0 image arm at its D2 threshold, `rf06` and `rf07` both route under the 10% rule, and no `usable` document is newly routed.
- **H0**: `rf06` or `rf07` does not route, or at least one `usable` document is newly routed.
- **Decision rule**: PASS when the local image arm meets both parts of the pass rule. FAIL otherwise. The hosted Jev image arm is a required control. Without its scores, the report gives no verdict.

## 3. What changes, what is measured, what stays fixed

| Changes (one thing) | Primary metric | Guardrail metric | Fixed |
| --- | --- | --- | --- |
| The flag rule on rescued pages: control, word check, Clef-Flash image, Jev image | `rf06` and `rf07` routed (yes or no) | `usable` documents newly routed (count) | Experiment 33 documents and labels, LiteParse text, 10% routing rule |

| Item | Value |
| --- | --- |
| Question | `Does the text match the text written or printed on the page image?` |
| Request type | `noul`, options `["no", "yes"]`. Score: P(yes) |
| Text head | First 2,000 characters of the LiteParse page text, shipped normaliser. No other cleaning |
| Render | PNG, 150 DPI with poppler `pdftoppm`; long side at most 1,568 px (Lanczos); a side under 280 px stops the run |
| Threshold | Experiment 38 equal-cost rule, per image arm, fitted on 561 healthy pages of the 38 documents that are not `rf06` or `rf07` |
| Flag | P(yes) below the threshold |

The four arms:

| Arm | Flag rule | Role |
| --- | --- | --- |
| Control | never flags (production today, TDR-024) | baseline |
| Word check | Experiment 38 candidate A score below 0.8834 (its committed threshold) | comparison |
| Clef-Flash image | P(yes) below its D2 threshold | treatment, decides the verdict |
| Jev image (hosted) | P(yes) below its own D2 threshold | required control |

The word check needs `wordfreq`, which is not installed. A download is not allowed. So the word check reuses the committed Experiment 38 scores page by page, only where the page text hash is the same. Those scores exist only on the Experiment 38 classified pages (junk and healthy).

## 4. Data

| Item | Value |
| --- | --- |
| Source | Experiment 33: 40 documents, 1,123 pages, frozen `labels.json` (22 `usable`, 18 `needs_ocr`) |
| Unit | Page, then document |
| Page classes | Experiment 38 `output/rescue_text.json`, LiteParse tier: 89 junk pages (54 in `rf06` and `rf07`), 565 healthy pages |
| Rescued documents | `tl04` to `tl08` and `rf01` to `rf08` (263 pages). Only these pages can flag, because the check sees only rescued text |
| Prior routes | Experiment 33 `arm_sampled_baseline/routing.json`. A prior route stays in every arm |
| Labels | Frozen in Experiment 33. No new labels |
| Already seen | All documents were used in Experiments 33, 38 and 42. The threshold is fitted on the same documents (limit, see section 6) |

## 5. Steps

Run each command from the experiment folder. `SRC` is a checkout that holds the Experiment 33 corpus (read only).

1. Check the inputs, extract the text, render the pages: `uv run --no-sync python prepare_inputs.py --source-exp $SRC`
2. Runtime checks and smoke test (R1 to R6): `uv run --no-sync python score_pages.py --arm clef_image --check`
3. Speed trial, 40 fit pages: `uv run --no-sync python score_pages.py --arm clef_image --phase fit --limit 40`
4. Fit pages: `uv run --no-sync python score_pages.py --arm clef_image --phase fit --resume`
5. Fit the threshold: `uv run --no-sync python analysis.py --fit clef_image`. Write the value to `plan.json` with an amendment and commit it.
6. Other pages: `uv run --no-sync python score_pages.py --arm clef_image --phase rest --resume`
7. Hosted arm: repeat steps 2 to 6 with `--arm jev_image`. The cost trial uses 5 pages (`--limit 5`).
8. Summarise: `uv run --no-sync python analysis.py`

Every long run checkpoints after each page, writes atomically and appends a line to `output/run-records.jsonl`.

## 6. Analysis

- **Stats level**: basic. Counts, not rates, because only two junk documents exist.
- **Page level, per arm**: junk pages caught (of 89, and of 54 in `rf06` and `rf07`), healthy pages flagged (of 565).
- **Document level, per arm**: documents routed under the 10% rule and under the one-page rule. For each wrongly routed `usable` document, its OCR cost in pages and in seconds (pages x 38.2 s, dots.mocr).
- **Populations**: primary routing uses all scored pages of the rescued documents. Classified routing uses only junk and healthy pages, so all four arms compare on the same pages.
- **Gates** (local image arm, primary routing, 10% rule):

| Gate | Pass when | Why it matters |
| --- | --- | --- |
| G1 | `rf06` and `rf07` both route | the documents of issue #161 reach OCR |
| G2 | no `usable` document is newly routed | good documents do not pay OCR cost |

- **Stop rules**: see `plan.json` `stopping_rules`. They include a 6-hour speed limit, a USD 10 cost limit, a model-id change, free memory under 15% and more than 10 failed pages.
- **What each outcome means**:

| Local arm | Hosted arm | Meaning |
| --- | --- | --- |
| PASS | PASS | PASS. Follow-up change and ADR confirm on new documents |
| PASS | FAIL | PASS for the local arm. The report names the documents where the arms differ |
| FAIL | PASS | FAIL. The question works on a stronger model; the local runtime or model is the limit |
| FAIL | FAIL | FAIL. The fidelity question does not separate junk layers well enough |

- **Limit**: the threshold is fitted on the same documents it is tested on. A PASS shows the idea works here. It does not show that it generalises.

## 7. Runtime

- **Purpose**: optimisation
- **Runtime under test**: no
- **Local models**: llama.cpp with public GGUF files.

| Role | Repository | File | SHA-256 | llama.cpp build | Server arguments |
| --- | --- | --- | --- | --- | --- |
| Decision (image and text) | `ggml-org/Clef-Flash-GGUF` revision `a5a18a6e13bb36573a5f11385a1e7b9a0c868e9e` | `Clef-Flash-Q8_0.gguf` | `25f801e2a27610b0ccc0cb1558d7eda3d7a304e34e2c4a04e3079357ff7d906e` | 11941 | `--mmproj`, `--host 127.0.0.1`, `-np 1`, `-c 8192`, `-b 8192`, `-ub 8192` |
| Projector | same repository and revision | `mmproj-Clef-Flash-Q8_0.gguf` | `9dd8bc279f57d33b0697d4d0fe900fe751a24c9e3d30ab90969d4714ffc0722d` | 11941 | loaded with `--mmproj` |

- **Hosted reference**: TypeSafe `jev-1.14.0` with images, header `TypeSafe-Danger-Zone-Images: true`. The returned model id is recorded for every page. The key comes from `TYPESAFE_API_KEY` and is never printed or saved.
- **Approval**: the operator approved on 2026-11-02 sending the page images and text heads of the 40 documents, including `rf06` and `rf07` (named-person records), to TypeSafe (`plan.json` `decision_register`).
- **Tolerance**: each per-page P(yes) may change by at most 0.02 and still count as the same result.
- **Live check**: the runner calls `verify_llamacpp_runtime` before the first score, hashes the projector itself and runs the smoke test. A mismatch stops the run.
