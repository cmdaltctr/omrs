# Experiment 46: Local OCR backends for non-Latin scripts

- **Folder**: `46-local-ocr-backends-2026-11-04`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Date run**: 2026-11-04
- **Operator**: OMRS maintainer, with a coding agent
- **Plan**: [protocol.md](protocol.md) · [plan.json](plan.json)
- **Source of every number**: `output/summary.json`, with the tables in `output/report_tables.md`. Raw rows are in `output/arm_b.jsonl` and `output/arm_d.jsonl`.

## Answer

- **Question**: Does a local OCR backend that supports Arabic, Bengali and Devanagari read the 129 non-Latin pages well enough to keep many of them local, without making Latin pages worse, and does its confidence separate good pages from bad pages?
- **Answer**: Yes for one backend and two scripts. Indra (arm B) passes all four gates for Arabic and Devanagari. It keeps 58 of 69 pages local and none of the kept pages is bad (`output/summary.json`, arm B `g2_counts`). Apple Vision (arm D) fails G2. It reads well, but its confidence keeps only 4 of the 69 pages.
- **Decision**: The planned rule gives PASS. Open a follow-up change that adds Indra to the local OCR registry with a cut of 0.90. Do not let Indra serve Bengali. It reads Bengali at a median recall of 0.59 and its cut still keeps 53 of the 60 pages.
- **How sure**: Medium. The gates hold with room to spare, except Arabic recall (0.75 against a gate of 0.70). The evidence is four non-Latin documents. The reference text is a vision model, not a person.
- **Next step**: Propose the follow-up change. It needs an answer to one open question: how Indra is kept away from Bengali pages, because a scan gives no script verdict before OCR (Experiment 45).

## What we tested

We compared two candidate local OCR engines with the current one (PP-OCRv6 Small, the control). The candidates were Indra OCR 1.1.2 (arm B) and Apple Vision through `ocrmac` (arm D). The result decides whether a second backend joins the registry in change `local-ocr-backends`, and which one.

The data is 229 scanned pages from Experiment 33: 129 non-Latin pages (Devanagari 48, Bengali 60, Arabic 21) and 100 Latin pages drawn with seed 46 (print 30, old print 35, handwriting 35). Apple Vision cannot read Bengali, so it ran on 169 pages.

## Results

Indra reads Arabic and Devanagari well, and its confidence ranks pages well. Apple Vision reads as well or better, but its confidence does not separate good pages from bad ones.

Median token recall by script (G1 needs 0.70 or more). Source: `output/summary.json`, `median_recall_by_script`.

| Script | Pages | A PP-OCRv6 (control) | B Indra | D Apple Vision |
| --- | ---: | ---: | ---: | ---: |
| Arabic | 21 | 0.000 | 0.752 (pass) | 0.866 (pass) |
| Bengali | 60 | 0.000 | 0.590 (FAIL) | not run |
| Devanagari | 48 | 0.000 | 0.986 (pass) | 1.000 (pass) |

The gates for each arm and script. The cut for each held-out document comes from the other documents only (leave-one-document-out). G2 covers the pages of the scripts that pass G1.

| Arm | Script | G1 read | G2 confidence | G3 Latin | G4 speed |
| --- | --- | :---: | :---: | :---: | :---: |
| B | Arabic | pass | pass | pass | pass |
| B | Bengali | FAIL | FAIL | pass | pass |
| B | Devanagari | pass | pass | pass | pass |
| D | Arabic | pass | FAIL | pass | pass |
| D | Devanagari | pass | FAIL | pass | pass |

The numbers behind G2, G3 and G4:

| Arm | Good pages kept (0.60 or more) | Kept pages that are bad (0.05 or less) | All pages kept (0.30 or more) | Latin difference to PP-OCRv6, median (-0.02 or more) | Lowest Latin stratum (-0.05 or more) | Seconds per page (5.0 or less) |
| --- | --- | --- | --- | --- | --- | --- |
| B | 49 of 53 | 0 of 58 | 58 of 69 | +0.115 | print 0.000 | 0.096 |
| D | 1 of 63 | 0 of 4 | 4 of 69 | +0.068 | print -0.001 | 0.154 |

Indra keeps 84% of the Arabic and Devanagari pages and none of the kept pages falls below 0.5 recall. At 37.0 s per engine page (Experiment 37), 58 kept pages avoid about 36 minutes of engine time. Apple Vision keeps 6% of them. For its Devanagari fold, no cut on the grid kept the bad pages at 5% or less, so that fold keeps no page (`loo_cuts`, `io01: None`).

Both arms read Latin pages better than PP-OCRv6, so G3 passes with a wide margin:

| Median Latin recall | Print (30) | Old print (35) | Handwriting (35) |
| --- | ---: | ---: | ---: |
| A PP-OCRv6 | 0.974 | 0.607 | 0.275 |
| B Indra | 0.976 | 0.793 | 0.428 |
| D Apple Vision | 0.982 | 0.694 | 0.413 |

### Hypotheses

| Hypothesis | Null | Result | Plain meaning |
| --- | --- | --- | --- |
| H1 (primary) | No candidate arm passes G1 to G4 for any script. | Supported. Arm B passes all four gates for Arabic and Devanagari. | One local engine reads two of the three scripts well enough to keep most pages local. |
| H2 (secondary) | No arm reaches AUC 0.80 for "recall 0.8 or more". | Supported. AUC is 0.973 for B and 0.844 for D (`auc_recall_ge_0_8.conf`). | A higher confidence means a better page. B ranks pages almost perfectly. |
| H3 (secondary) | No arm fails only G3. | Not met. No arm fails only G3. | Latin pages do not hold either arm back. Both pass G3. |

### Amendments and deviations

No amendment to `plan.json`. Four points to know:

1. **Fill-ins before the first run.** The three tree hashes, the `pages.json` hash, each arm's version and weights hash, and the approval date were written into `plan.json` before any arm ran. The plan marked each one "fill before first run".
2. **Three tie-break rules.** The plan did not say what to do in three cases. They were written into the `summarise.py` docstring before any run: a cut must keep at least one page to qualify; a page with no confidence is never kept; G2 is computed once over the pages of all scripts that pass G1.
3. **Reported values added after the run.** `summarise.py` was edited after the run to also write the G3 values and the control's per-page rows. No rule changed. A re-run gave identical outcome, gates and per-page rows.
4. **Dirty-tree flag.** The run record for arm D shows `git_dirty: true`. Arm B's untracked `output/` folder caused it. Both runs used commit `127561f7` and the same `plan.json` hash (`output/run-records.jsonl`).

### Exploratory findings

These are exploratory. They cannot change the answer. Source: `output/report_tables.md`, section (f).

1. **Indra's cut on pages the gates do not cover.** The cut keeps 53 of 60 Bengali pages, and 9 of those have recall below 0.5. It keeps 48 of 100 Latin pages, and 6 of those are bad. That is 17% and 12.5% bad pages among the kept ones. The 0.05 bound applies only to Arabic and Devanagari in the plan.
2. **No suspect-reference pages.** The plan asked the operator to read pages where recall is below 0.5 against the reference but 0.8 or more against dots.mocr. No page meets that rule for any script (`output/report_tables.md`, section (g)). The spot-check was not done. It had nothing to read.
3. **One weak Arabic document.** `io03` (5 pages) has median recall 0.21 with Indra. The cut keeps none of its pages. `io02` (16 pages) has median recall 0.78 and 14 pages are kept.

## Why it happened

1. **Indra's confidence tracks its recall.** AUC 0.973 means that, for a random good page and a random bad page, the good page has the higher confidence 97% of the time. A cut near 0.90 therefore keeps good pages and drops bad ones.
2. **Apple Vision's confidence ranks pages less well.** Its AUC is 0.844. The cut chosen from the other documents kept almost nothing in the Arabic folds (4 of 21 pages) and found no safe value in the Devanagari fold. The data does not show why. We did not look at which bad pages scored high.
3. **Indra reads Bengali badly.** Its recall against the reference (0.59) and against dots.mocr (0.60) agree, and dots.mocr reads the same pages at 0.89 against the reference (Experiment 37). So this looks like a real reading weakness. The cause is unexplained.
4. **Both arms beat PP-OCRv6 on Latin.** The gain is largest on old print and handwriting. This was not a goal of the experiment.

## Limits

1. Four non-Latin documents in three scripts. Bengali and Devanagari have one document each. Arabic has two, and one of them reads poorly.
2. Arabic recall for Indra is 0.75 against a gate of 0.70. A small change in the sample could move it.
3. Scanned pages only. There is no born-digital non-Latin PDF.
4. One machine (Apple M5 Pro, 64 GB, macOS 27.2) and one operating system. Speeds do not transfer to CI or other hardware. Apple Vision may use the Neural Engine, so its time is "as measured", not "CPU only".
5. The reference is a vision model (`google/gemini-3.8-flash`), not a person. Recall measures agreement with it.
6. The control read pages rendered by pdf-inspector. The candidates read the Experiment 33 PNG files. Render differences can move recall. The control's seconds are a document average and enter no gate.
7. Apple Vision got an oracle language for each page. That flatters it, and it still failed.
8. The gate numbers are judgement, written down before the run. The licence of the Indra weights (modified OpenRAIL-M) still needs the operator's decision in the follow-up. PyPI lists the code as Apache-2.0.

## What it means for you

Indra can take over most Arabic and Devanagari scan pages locally and save about 36 minutes of engine time per 58 pages. It must not serve Bengali, and the follow-up change has to say how it is kept away from those pages. Apple Vision is out: it fails G2 and runs only on macOS.

## Artefacts

| File | Contents |
| --- | --- |
| `output/summary.json` | Aggregated metrics, cuts, gates and the outcome |
| `output/report_tables.md` | Every table in this report, from `analysis.py` |
| `output/arm_b.jsonl`, `output/arm_d.jsonl` | One row per page: text, lines, confidence, seconds |
| `output/arm_b.load.json`, `output/arm_d.load.json` | Model load time: 0.365 s (B), 0.175 s (D) |
| `output/run-records.jsonl` | One line per run start: time, git commit, plan SHA-256 |
| `pages.json` | The 229 pages (seed 46) |
| `run_arm.py`, `summarise.py`, `analysis.py` | Check, sample and arm run; scoring; tables |
