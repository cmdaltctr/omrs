# Experiment 41: OCR runtimes, GGUF against MLX

- **Folder**: `41-ocr-runtimes-2026-10-30`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Date run**: not run yet
- **Operator**: Dr Muhammad Aizat Bin Md Hawari
- **Plan**: [protocol.md](protocol.md) · [plan.json](plan.json)
- **Source of every number**: `output/summary.json` (not written yet)

## Answer

- **Question**: Which OCR runtime (llama.cpp GGUF, MLX or the shipped backend) can serve each engine without losing output quality?
- **Answer**: Not answered. The plan is written. No run has started.
- **Decision**: None yet. Each engine keeps its shipped backend until its llama.cpp arm (D4 or P4) passes C1 to C5.
- **How sure**: Not applicable. No data.
- **Next step**: The operator approves the install, download, licence and budget gates in `plan.json`.

## What we tested

Nothing yet. The plan compares two scored 8-bit arms per engine (one MLX, one GGUF) with each engine's shipped backend, on the Experiment 37 page lists (257 pages). Conditional 16-bit diagnostic arms run only when an 8-bit arm fails C3, C4 or C5, and they never change a verdict.

## Results

Not run.

## Why it happened

Not run.

## Limits

1. dots.mocr may not convert or load in llama.cpp build 11941. Check the result of the conversion first.
2. The PaddleOCR-VL 1.6 MLX arm uses a published build (`OpenGryd/PaddleOCR-VL-1.6-MLX-8bit` at `dba7c66b`). Its quantisation differs from the GGUF Q8_0 arm, so the two are not precision-matched (protocol, Comparisons).
3. The Experiment 37 speed baseline ran under shared load (protocol, Why this experiment exists).

## What it means for you

Nothing changes yet. The shipped backends stay on. MLX cannot decide a runtime, so a llama.cpp arm must pass before any engine change.

## Artefacts

- [protocol.md](protocol.md), [plan.json](plan.json), [experiment.json](experiment.json)
