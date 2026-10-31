# Experiment 41: OCR runtimes, GGUF against MLX

- **Folder**: `41-ocr-runtimes-2026-10-30`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Date run**: 2026-10-31 (all four scored arms and the three 16-bit diagnostics)
- **Operator**: Dr Muhammad Aizat Bin Md Hawari (approvals, decisions). Claude Code ran the experiment and did the C5 review on the operator's instruction (see Limits, item 1).
- **Plan**: [protocol.md](protocol.md) · [plan.json](plan.json) (frozen, SHA-256 `8bef2738…ccd66`, no amendments)
- **Source of every number**: `output/summary.json`, written by `summarise.py`

## Answer

- **Question**: Can a llama.cpp GGUF arm replace the shipped OCR backend for dots.mocr or PaddleOCR-VL without losing quality?
- **Answer**: No. D4 (dots.mocr GGUF Q8_0) keeps the quality of the shipped backend but is only 1.29 times faster, and the gate asks for 2 times. P4 (PaddleOCR-VL GGUF Q8_0) is 12 times faster but its output holds invented text on 10 of 25 review pages, which fails gate C5.
- **Decision**: Both engines keep their shipped backend. No follow-up change for a llama.cpp path. MLX arms cannot lead to a decision.
- **How sure**: Sure about D4 (it fails the speed gate by a wide margin). Fairly sure about P4 (the 16-bit file fails in the same way, so the fault is in the model and not in the 8-bit step). The C5 review was done by an AI, not by the operator (Limits, item 1).
- **Next step**: Decide whether to run a separate experiment on PaddleOCR-VL's invented text on Bengali and Arabic pages (see "What it means for you").

## What we tested

Both OCR engines run today through their shipped backends (dots.mocr on PyTorch, PaddleOCR-VL on the CPU). We asked whether a llama.cpp GGUF file at 8-bit (Q8_0) could replace each one. MLX 8-bit arms also ran, as comparison arms. An MLX arm cannot decide a runtime because MLX only runs on Apple silicon.

| Arm | Engine | Runtime | Role |
| --- | --- | --- | --- |
| D0, P0 | dots.mocr, PaddleOCR-VL | shipped backend (Experiment 37 results) | baseline |
| D4 | dots.mocr | llama.cpp GGUF Q8_0 | decides |
| P4 | PaddleOCR-VL | llama.cpp GGUF Q8_0 | decides |
| D2 | dots.mocr | MLX 8-bit | comparison |
| P2 | PaddleOCR-VL | MLX 8-bit | comparison |
| D3, P3, P1 | dots.mocr, PaddleOCR-VL | GGUF 16-bit, GGUF 16-bit, MLX 16-bit | diagnostic, run only because an 8-bit arm failed C5 |

All arms ran on the same 257 pages as Experiment 37 (E-maths 40, E-scan 28, E-script 189), one arm at a time, on one Apple M-series Mac with 48 GB. llama.cpp was build 11941 for every GGUF arm. Both GGUF engines loaded and produced text on the smoke pages (plan.json, OI-2). The dots.mocr GGUF matched an independent community Q8_0 file exactly (OI-9).

### The gates, in plain English

A gate is a pass or fail test the operator wrote before any run. C1 to C5 decide. C6 and C7 only inform.

| Gate | What it asks | Limit |
| --- | --- | --- |
| C1 Speed | Is the arm at least twice as fast as the baseline on the same pages? | median seconds per page at most 0.5 times the baseline |
| C2 Timeouts | Does any page run past 300 seconds? | 0 |
| C3 Maths | Do the maths formulas render in KaTeX? | error rate at most 0.01 |
| C4 Recall | Does the arm read as many words as the baseline on the 189 script and handwriting pages? | median recall at least baseline minus 0.05 |
| C5 Invented text | Does a reviewer find text that is not on the page? | none on the review list |
| C6 Similarity | How close is the text to the baseline text (Dice score)? | information only, 0.90 or more is "close" |
| C7 Memory | How much memory did the run use? | information only |

The review list for C5 holds the 10 pages least like the baseline, every page a noise screen flagged, and 5 random pages (seed 41). A diagnostic arm is a higher-precision (16-bit) copy of the same model. It tells us whether a failure comes from the 8-bit shrinking or from the model itself. A diagnostic never changes a verdict.

## Results

### Gates for the four scored arms

| Gate | D4 (decides) | P4 (decides) | D2 (comparison) | P2 (comparison) |
| --- | --- | --- | --- | --- |
| C1 Speed (limit) | **Fail** 43.97 s (28.31) | Pass 3.21 s (20.09) | Pass 22.84 s (28.31) | Pass 2.72 s (20.09) |
| C2 Timeouts | Pass, 0 | Pass, 0 | Pass, 0 | Pass, 0 |
| C3 KaTeX error rate | Pass, 0 of 1,895 | Pass, 0.0035 of 1,724 | Pass, 0 of 1,893 | Pass, 0.0034 of 1,753 |
| C4 Recall (floor) | Pass, 0.8886 (0.8389) | Pass, 0.6303 (0.5595) | Pass, 0.8889 (0.8389) | Pass, 0.6034 (0.5595) |
| C5 Invented pages | **Fail** 2 of 17 | **Fail** 10 of 25 | Pass 0 of 17 | **Fail** 14 of 26 |
| C6 Dice vs baseline | 1.00 | 0.90 | 1.00 | 0.89 |
| C7 Peak memory | 17.3 GiB | 12.0 GiB | 11.1 GiB | 10.7 GiB |
| **Result** | **Fail** | **Fail** | not decisive | not decisive |

Baselines: D0 median 56.62 s on the 19 comparison pages (speed), recall 0.8889; P0 median 40.17 s on the 221 pages it finished, recall 0.6095. Over all 257 pages the medians were D4 20.13 s, D2 13.42 s, P4 3.36 s and P2 2.83 s.

Run counts: D4 and D2 gave text on 253 pages and were empty on 4 (rf06:11, rf06:42, rf06:60, rf07:4). The baseline D0 is also empty on those 4. P4 and P2 gave text on 255 pages and failed on the same 2 pages as P0 (io06:53, io06:65, "empty Markdown"). The shipped P0 failed on 36 pages.

### C5 and the 16-bit diagnostics

| Arm | Pages reviewed | Pages with invented text |
| --- | ---: | ---: |
| D0 (shipped dots.mocr, control) | 17 | 0 |
| D4 (GGUF Q8_0) | 17 | 2 |
| D3 (GGUF 16-bit, diagnostic) | 17 | 1 |
| P0 (shipped PaddleOCR-VL, control) | 25 | 15 |
| P4 (GGUF Q8_0) | 25 | 10 |
| P3 (GGUF 16-bit, diagnostic) | 25 | 12 |
| P2 (MLX 8-bit) | 26 | 14 |
| P1 (MLX 16-bit, diagnostic) | 26 | 15 |

The P0 and D0 rows are a control the plan did not require. I added them so the invented-text counts could be read against what ships today.

A second check does not depend on any reviewer. A script counted letters from the wrong writing system (for example Tamil or Thai letters on a Bengali page) and repeated phrases:

| Arm | Pages flagged by the script on the P4 list (25) |
| --- | ---: |
| P0 (shipped) | 6 |
| P4 (GGUF Q8_0) | 8 |
| P3 (GGUF 16-bit) | 8 (the same 8 pages as P4) |

On the D4 list (17 pages) D0, D4 and D3 each flag the same 2 pages (io03:3 and io03:4), which are Arabic newspaper pages with dense tables.

### What the invented text looks like

- **P4:** Thai letters on a Bengali page (1,059 characters on io07:8). Tamil letters on io07:18 (118) and io07:31 (99). Telugu on io07:58 and io07:6. Arabic pages io03:1 and io03:2 end in a loop, one phrase repeated 342 times on io03:2.
- **D4:** one English word inside Arabic text (io03:3) and one repeated phrase in handwriting (rf06:50). Both calls are close to the line. D3 keeps the handwriting call and drops the Arabic one.
- **P0 (shipped):** also puts Devanagari or Tamil letters on Bengali pages (158 to 552 foreign characters on io07:13, io07:18 and io07:58).

### Speed of the diagnostics

D3 took a median of 64.44 s per page, P3 3.84 s and P1 2.98 s. Each ran on its review list only, so these are not comparable with the scored arms.

### Token cap

P4 hit the 4,096-token output limit on 35 blocks across 29 pages, and P2 on 58 blocks across 51 pages. Of P4's 29 pages, 18 are pages where the shipped P0 failed outright. D4 and D2 never hit their cap. This is information only.

## Why it happened

1. **D4 is the same model as the shipped backend, only faster.** Its text matches D0 on the median page (Dice 1.00) and it passes C3 and C4. It still fails C1: 43.97 s against a limit of 28.31 s, a 1.29 times speed-up. The speed-up is real over all 257 pages (20.13 s against D0's median of 37.0 s) but the gate compares the 19 pages that ran alone.
2. **P4 is much faster partly because it gives up early on hard pages.** The shipped P0 ran to the 300 second limit on many pages and failed on 36. P4 stops at its 4,096-token cap, after a median of 13.55 s on those pages, and still writes out what it has. That is why it passes C1 by a wide margin and why it finishes 255 pages against P0's 221. The text it writes on capped pages may be a loop, and the review did not check every capped page.
3. **The invented text is a PaddleOCR-VL problem and not a runtime problem.** P4 and P3 flag the same 8 pages on the script check, and the shipped P0 flags 6 of the same pages. The 16-bit file (P3) is no better than the 8-bit file (P4). The MLX builds (P2, P1) are no better. A different runtime or precision does not fix it.
4. **P4 is not worse than what ships today.** The control puts P0 at 15 of 25 invented, against P4's 10. C5 compares each arm with a rule of "no invented text", not with the baseline, so P4 still fails.

## Limits

1. **The C5 review was done by an AI and not by the operator.** The plan names the operator as the reviewer. The operator asked Claude to do it and accepted the result on 2026-10-31. Four Sonnet reviewers judged the 56 unique pages against the page images, and a script cross-checked them. `plan.json` was not amended. Task 6.3 in `tasks.md` records this. 31 of the 85 first-pass calls and many of the 16-bit and control calls are marked low confidence, mostly Bengali, Arabic and handwriting, where the reviewers read the script less reliably.
2. **Reviewer strictness varies.** Some calls rest on one or two stray characters (for example io07:13, io07:25 and io07:42 for P4). With the script check alone, P4 still fails (8 pages), so the P4 conclusion holds either way. D4's fail is the weaker one: the script check finds no difference between D4 and D0.
3. **One reviewer pass per arm.** Nobody repeated the review. Calls on the same page differ between arms in a few borderline cases.
4. **The Experiment 37 speed baseline ran under shared load.** D0 and P0 timings come from Experiment 37 and were not re-timed. The planned T-control re-timing (20 pages alone, seed 41) was not run. Only D2 fell in the 1.5 to 3 times band, D2 is a comparison arm, and D4 would need a D0 median of 88 s or more to pass C1.
5. **The 19 pages in the D speed comparison are a small sample.** The all-page medians point the same way.
6. **The image-token flags have no effect on build 11941.** It ignores `--image-min-tokens` and `--image-max-tokens` for these two projectors. The limits come from the pinned mmproj files (plan.json, OI-10 and DR-5).
7. **Warnings from the PDF library (pypdf) may shift the noise-screen counts slightly against Experiment 37.** This was not measured.
8. **The live app and the embedding model were idle in the background** during the runs. The runs were otherwise alone on the GPU.
9. **Two pages are blank on the page** (io06:78 for D, io06:53 and io06:65 for P). They are excluded from review because they hold no text.

## What it means for you

Nothing changes. dots.mocr and PaddleOCR-VL keep their shipped backends and no default moves.

- **dots.mocr:** a llama.cpp path is a safe quality match but gives only a 1.29 times speed-up on the like-for-like pages. It is not worth a change on its own.
- **PaddleOCR-VL:** a llama.cpp path is 12 times faster but the model puts text from the wrong writing system on Bengali and Arabic pages, and it already does so today. A runtime change cannot fix it. A separate experiment should ask whether the engine should handle those scripts at all, or whether a page-level check should catch them.
- **MLX:** D2 passes every gate, but MLX cannot decide a runtime, and the project rules list MLX as not allowed (ADR-103).

## Artefacts

- [protocol.md](protocol.md), [plan.json](plan.json), [experiment.json](experiment.json)
- Scripts: [run_ocr.py](run_ocr.py), [summarise.py](summarise.py), [analysis.py](analysis.py)
- C5 verdicts: [review_verdicts.json](review_verdicts.json) (SHA-256 `7e68db96dedaf78dbc916309b38a2b039f3368e7da8a83fa2cda0f764dbae3b0`) and [review_verdicts_diagnostic.json](review_verdicts_diagnostic.json) (SHA-256 `f75e9457f616e610fd169786328271ad656e1cd98341f93009e9b21a035e7ead`)
- Data (local, not committed): `output/summary.json` (committed), `output/<arm>/` page text, `output/ocr_state_<arm>.json`, `output/katex_<arm>.json`, `output/recall_<arm>.json`, `output/similarity_<arm>_vs_<baseline>.json`, `output/review_<arm>.html`, `output/review_selection.json`
