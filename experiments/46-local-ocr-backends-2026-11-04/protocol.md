# Experiment 46: Local OCR backends for non-Latin scripts

- **Folder**: `46-local-ocr-backends-2026-11-04`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Operator**: OMRS maintainer, with a coding agent
- **Related**: OpenSpec change `local-ocr-backends` (design D5, D6, D8, D9), Experiments 33, 37, 39, 45, ADR-069, ADR-071
- **Number**: 46. Numbers 40 and 43 are in `reserved.json`. Number 45 exists.
- **Status of this file**: written before any arm runs. No output file exists when the orchestrator commits it.

## 1. Question

Does a local OCR backend that supports Arabic, Bengali and Devanagari read the 129 non-Latin pages well enough to keep many of them local, without making Latin pages worse, and does its confidence separate good pages from bad pages?

The result decides whether a follow-up change adds a second backend to the registry from change `local-ocr-backends`, and which one.

## 2. Hypothesis

- **H1 (primary)**: at least one candidate arm passes all four gates (G1 to G4) for at least one script. It reads that script at a median token recall of 0.70 or more, keeps at least 0.30 of that script's pages local with a leave-one-document-out cut, reads Latin pages no worse than PP-OCRv6 Small, and takes 5.0 s per page or less on CPU.
- **H0 (null)**: no candidate arm passes all four gates for any script.
- **Decision rule (fixed, see section 6)**: if H1 holds, open a follow-up change that adds that backend, with the cut this experiment picks. Otherwise keep `pp-ocrv6-small` as the only backend and keep `always` for non-Latin collections.

H2 and H3 are secondary and do not enter the rule:

- **H2 (secondary)**: the page confidence of at least one arm ranks pages by recall (AUC 0.80 or more for "recall at least 0.8").
- **H3 (secondary)**: a candidate that fails G3 (Latin) still passes G1, G2 and G4 for a script. That result says a script chooser would let the backend serve that script. No chooser exists today (Experiment 45).

## 3. What changes, what is measured, what stays fixed

| Changes (one thing) | Primary metric | Guardrail metric | Fixed |
| --- | --- | --- | --- |
| Local OCR backend: PP-OCRv6 Small (control, stored) against B Indra OCR and D Apple Vision | Token recall of the page text against the Experiment 33 reference transcription, median per script | Latin recall against PP-OCRv6 (paired), seconds per page, share of bad pages that the cut keeps | The 229 pages, the page images, the tokeniser, the recall function, the machine, one request at a time |

## 4. Data

| Item | Value |
| --- | --- |
| Source | Experiment 33 (reference transcriptions, labels, page images, stored PP-OCRv6 output) and Experiment 37 (dots.mocr text) |
| Unit | Page |
| Size | 229 pages: 129 non-Latin and 100 Latin |
| Groups | Nine documents: `io01`, `io02`, `io03`, `io07` (non-Latin); `io04`, `io05`, `io06`, `rf06`, `rf07` (Latin sample) |
| Labels | The Experiment 33 reference transcription (see the warning below) |
| Already seen | The 129 non-Latin pages: PP-OCRv6 recall 0.000 and dots.mocr recall (Experiments 33, 37, 45). The Latin pages: PP-OCRv6 recall and confidence (Experiments 33, 39). The agent that wrote this plan also tabulated PP-OCRv6 stored recall and confidence by document group once, before writing the rule. It used no number from that tabulation to set a threshold. Gate G3 is relative to PP-OCRv6, not absolute. |

**Warning about the reference.** The reference transcriptions are not human transcripts. Experiment 33 made them with a vision model (`google/gemini-3.8-flash`, temperature 0, through OpenRouter) and split them into body text and other text. The operator labelled a few pages for presence of text, not for the words. So the primary metric measures agreement with a vision model. The model can be wrong on Arabic and Bengali. A backend that reads a page better than the reference scores lower. Two measures reduce the risk: recall against dots.mocr text (secondary) and an operator spot-check (section 5, step 7). Neither makes the reference a human transcript.

**Non-Latin pages (129).** The same set as Experiment 45: `io01` Devanagari 48, `io02` Arabic 16, `io03` Arabic 5, `io07` Bengali 60. Script totals: Devanagari 48, Bengali 60, Arabic 21.

**Latin sample (100).** Drawn with seed 46 from pages that have a stored PP-OCRv6 row, a split reference transcription and at least one reference token. Strata:

| Stratum | Documents | Pages drawn |
| --- | --- | ---: |
| Print | `io04`, `io05` | 30 |
| Old print | `io06` | 35 |
| Handwriting | `rf06`, `rf07` | 35 |

If a stratum has fewer eligible pages than its draw, the runner stops and the plan needs an amendment before any run.

**Page images.** The arms read the PNG files in the Experiment 33 data store (`output/.pages/<document>/p<NNN>.png`, 150 dpi, 1600 px on the long side). PP-OCRv6 Small, the control, read pages that pdf-inspector rendered itself. The two renders differ. This is a limit (section 8). The runner checks that every PNG exists. If a PNG is missing, it renders that page from `corpus/natural/<document>.pdf` with pypdfium2 at the same size and records the page in `output/render-log.json`. Rendering is not OCR.

## 5. Steps

Run every command from the repository root. Warn the operator before steps 3 and 4: they start heavy loops and an earlier loop crashed Chrome.

Script limit for this Standard experiment: three Python files, `run_arm.py`, `summarise.py` and `analysis.py`.

1. **Preconditions.** `uv run --no-sync python experiments/46-local-ocr-backends-2026-11-04/run_arm.py check`. It checks the frozen hashes, the 129-page class against the stored rows, the PNG files, the reference transcriptions and the tokeniser import. It stops on any difference.
2. **Sample.** `... run_arm.py sample`. It writes `pages.json` (229 pages) from the seed and the rule in section 4. The orchestrator records the SHA-256 of `pages.json` in `plan.json` `frozen` before step 3. This is a fill-in, not an amendment, because it happens before any run.
3. **Approvals and environments.** Each arm gets its own scratch environment outside the repository. The operator approves each download first (section 7). The operator reads the Indra licence in full before the Indra arm.
4. **Run one arm at a time, one page at a time.** `<arm python> experiments/46-local-ocr-backends-2026-11-04/run_arm.py --arm <b|d> --resume`. Each page appends one row to `output/arm_<id>.jsonl` (text, line confidences, page confidence, seconds, error). The first 3 pages of each arm are warm-up and are not timed. Model load time is recorded once, apart from the page times.
5. **Control.** Arm A reads the stored PP-OCRv6 text (`output/.local_ocr_text/<document>/p<NNN>.md`) and stored confidence. It runs no OCR. Its seconds are the stored `doc_seconds_share`. Those seconds are a document average that includes model load, so they are reported only and enter no gate.
6. **Summarise.** `uv run --no-sync python experiments/46-local-ocr-backends-2026-11-04/summarise.py`. It computes recall (tokeniser and `recall` imported from Experiment 33 `build_labels`), the leave-one-document-out cuts, the four gates for each arm and script, and writes `output/summary.json`.
7. **Spot-check (exploratory).** For the best arm of each script, the operator reads up to 10 pages where recall against the reference is below 0.5 and recall against dots.mocr is 0.8 or more. The reference is suspect on those pages. The operator notes which text is right. The note enters no gate.
8. **Report.** Write `analysis.py` and `report.md` from `output/summary.json`.

## 6. Analysis

- **Stats level**: basic. Counts, medians and shares. No p-values. Pages in one document are not independent, and the corpus has nine documents, so a page-level interval would look tighter than the evidence. Per-document values are in the tables.
- **Recall**: multiset token recall, as in Experiment 33 (`build_labels.tokens` and `recall`, imported). The reference is the split body text when it exists, else the first transcription. A page with no output scores 0.
- **Page confidence**: the character-weighted mean of line confidences (design D5). Apple Vision uses its line scores. Indra uses `Line.conf`. Two alternatives are reported as exploratory: the minimum over lines of 10 characters or more, and the share of characters on lines at 0.8 or above.
- **Cut selection**: leave one document out. For each held-out document, take the other eight documents (all pages), and pick the lowest cut on the grid 0.50, 0.55, ..., 0.95, 0.99 for which the pages at or above the cut have a share with recall below 0.5 of at most 0.05. If no cut qualifies, the arm has no cut for that fold and keeps no page. Apply the chosen cut to the held-out document. Pool the nine held-out results. The cut for a future registration is the median of the nine chosen cuts, rounded to 0.05, and is reported, not gated.
- **Good page**: recall 0.8 or more. **Bad page**: recall below 0.5. These are the Experiment 39 definitions.

### Gates

Fixed before any run. An arm is a candidate for script S when G1, G2, G3 and G4 all hold for S.

| Gate | Pass when | Why it matters |
| --- | --- | --- |
| G1 Read quality | Median recall on the pages of script S is 0.70 or more | The backend must read S at all. Experiment 37 gave dots.mocr medians of 0.873 to 0.985 on these scripts with this reference, so 0.70 is about 0.8 of the engine's lowest script median. The local tier needs to be close to the engine, not equal |
| G2 Confidence | With the leave-one-document-out cuts, over the pages of the scripts that pass G1: at least 0.60 of the good pages stay local, at most 0.05 of the kept pages are bad, and at least 0.30 of all those pages stay local | 0.05 is the Experiment 39 G2 bound. 0.60 means the cut wastes the engine on at most 0.40 of the good pages. 0.30 of the 129 pages is about 39 pages. At 37.0 s per engine page (Experiment 37) that saves about 24 minutes per 129 pages against `always`. Below that, a second backend, its licence and its cut cost more than they save |
| G3 Latin non-regression | On the 100 Latin pages, the median of the paired difference (arm recall minus PP-OCRv6 recall) is -0.02 or higher, and no stratum has a median difference below -0.05 | Scans give no script verdict before OCR (Experiment 45). A backend that reads every flagged page must not make Latin pages worse. Strata have 30 to 35 pages, so their margin is wider |
| G4 Speed | Median seconds per page is 5.0 or less on CPU on this machine, one request at a time, warm-up excluded | The engine takes 37.0 s per page (Experiment 37). A local tier at about one seventh of that still pays for itself. PP-OCRv6 takes about 0.7 s per page (Experiment 45 (d)) |

Arm-specific rules fixed now:

- **D Apple Vision** gets an oracle language: `ar-SA` for Arabic, `hi-IN` for Devanagari, `en-US` for Latin. Bengali is not supported, so D does not run on Bengali pages. D may use the Neural Engine, so G4 for D does not claim "CPU only". It claims the measured time. D cannot run in CI. A pass for D can only cover Arabic and Devanagari, and it needs a script chooser, which does not exist.
- **B Indra** gets no oracle. It picks the script per line and runs on all 229 pages.

### Outcomes

- **PASS**: at least one arm is a candidate (G1 to G4) for at least one script. Open a follow-up change that adds that backend with the picked cut, and a Settings row.
- **FAIL**: no arm passes G1, G2 and G4 for any script. Keep `pp-ocrv6-small` only.
- **INCONCLUSIVE**: an arm passes G1, G2 and G4 for a script and fails only G3 (H3). Record that a script chooser would unlock it. Open a task for the chooser. Adopt nothing now.
- **Stop rule**: an arm stops early if its first 20 timed pages have a median above 15 s. It is then recorded as failing G4. No other early stop.

## 7. Runtime

- **Purpose**: optimisation.
- **Runtime under test**: yes. The runtimes compared are ONNX Runtime (B) and Apple Vision (D). Experiment 41 set the precedent for a runtime-comparison experiment. The llama.cpp rule for language and embedding models does not apply, because no arm is a language model.
- **Local models**: none through llama.cpp. Each arm records its runtime, its version and the SHA-256 of each weights file in `plan.json` `arms` before the first run of that arm.
- **Hosted references**: the Experiment 33 reference transcription (`google/gemini-3.8-flash`, already made; no new call). The dots.mocr text from Experiment 37 (stored; no new call).
- **Tolerance**: a score for one page may differ by 0.01 recall between two runs of the same arm (tokeniser and OCR are deterministic, so a larger difference means the environment changed). The arm stops and the operator decides.
- **Machine**: this Mac only. The run record stores chip, memory and OS version.
- **Downloads. Each needs the operator's approval before it starts.**

| Arm | Package or file | Size | Licence | Note |
| --- | --- | --- | --- | --- |
| B Indra OCR 1.1.2 | `indra-ocr` from PyPI, weights from `datalab-to/indra-ocr` | about 76 MB (vendor figure; check at download) | Modified OpenRAIL-M. Limits on commercial and competing use. **The operator reads the full licence before any Indra run.** | ONNX Runtime, no PyTorch. Very new (v1.0 in October 2026). Vendor benchmarks only |
| D Apple Vision | `ocrmac` 1.0.1 (MIT) with PyObjC, or a small Swift script | OS-provided model; a few MB of Python packages | OS licence | macOS only. `ar-SA`, `hi-IN`, `mr-IN` found on this Mac. No Bengali |

Each arm installs into its own scratch folder outside the repository. Nothing touches the repository `.venv`, `uv.lock` or `pyproject.toml`.

## 8. Limits

These are known before the run. The report repeats them.

1. Four non-Latin documents in three scripts. One document holds each of Bengali and Devanagari. Leave-one-document-out for those two scripts takes the cut from other scripts and Latin pages.
2. Scanned pages only. There is no born-digital non-Latin PDF.
3. One machine, one operating system. Speeds do not transfer to CI or to other hardware.
4. The reference is a vision model, not a person (section 4).
5. The control read pages rendered by pdf-inspector. The candidates read the Experiment 33 PNG files. Render differences can move recall.
6. The control's seconds are a document average. They are not comparable with the timed arms and enter no gate.
7. Oracle language choice for D flatters it.
8. The decision rule numbers are judgement. They are written down so the run cannot move them.

## 9. Operator decisions (made 2026-11-04, before any run)

1. **Latin margin.** Keep G3 as written: median paired difference at least -0.02, no stratum below -0.05. Reason: 0.02 is about the noise of the Gemini reference, and the stratum floor still catches damage to one page type.
2. **Retype of `ocr_local_min_confidence`.** Deferred. It moves to the follow-up change that adds the first second backend, because only then does a second cut exist. The experiment does not depend on it.
3. **Merge the seam if no arm passes.** No. On FAIL, only this experiment's report merges, and the code part of `local-ocr-backends` is descoped. On PASS, the seam is built in the same change.
4. **Order.** The experiment runs first, from its own scripts. The code groups start only after a PASS.

## 10. Considered and dropped

RapidOCR and Tesseract were considered as arms and dropped by the operator on 2026-11-04. The experiment has three arms: A (control), B and D.
