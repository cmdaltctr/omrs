# Ordered local OCR list: simulation on Experiment 46 data (exploratory)

Date: 2026-11-04. Exploratory design evidence. It is not a gate result and it changes nothing in Experiment 46.

## Question

Can a local OCR backend keep only the pages whose output is in a script it reads well, and pass every other page to the next backend in an ordered list?

## Inputs

- `experiments/46-local-ocr-backends-2026-11-04/output/arm_b.jsonl` (Indra OCR 1.1.2 text, 229 pages).
- `experiments/46-local-ocr-backends-2026-11-04/output/summary.json` (`arms.B.rows` with the leave-one-document-out `kept` flag; `control_A.rows` with the stored PP-OCRv6 confidence and recall).

## Method

1. Classify the script of each Indra output by Unicode letter names (Arabic, Devanagari, Bengali, Latin, other). A verdict needs 40 letters and a share of 0.5, the floor and share of the shipped detector (`script_routing.py`, version 1).
2. Simulate the list `[indra (keeps arabic, devanagari), pp-ocrv6-small (cut 0.9)]`. Indra keeps a page when its cut keeps it and the output script is in its list. Otherwise PP-OCRv6 keeps the page when its stored confidence is 0.9 or more. Otherwise the page goes to the OCR engine.

## Results

Output script against the true script of the page: 229 of 229 correct (Arabic 21, Bengali 60, Devanagari 48, Latin 100).

| Script | Kept by Indra | Kept by PP-OCRv6 | To the engine | Kept pages with recall below 0.5 |
| --- | ---: | ---: | ---: | ---: |
| Arabic (21) | 14 | 0 | 7 | 0 |
| Devanagari (48) | 44 | 0 | 4 | 0 |
| Bengali (60) | 0 | 0 | 60 | 0 |
| Latin (100) | 0 | 56 | 44 | 3 |

The Latin row equals today's behaviour (arm A: 56 kept, 3 bad). The Bengali row equals today's behaviour (all to the engine).

## Limits

1. In-sample: the cut and the script list come from the same 229 pages.
2. The Indra `kept` flag uses the leave-one-document-out cuts, not one fixed cut of 0.90.
3. Nine documents. One document each for Bengali and Devanagari.
