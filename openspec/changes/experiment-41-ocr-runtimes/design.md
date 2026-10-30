# Design

## Context

See proposal.md (Why). Current state that shapes the approach:

- **Baseline exists.** Experiment 37 holds per-page Markdown, per-page state and `summary.json` for dots.mocr (PyTorch MPS) and PaddleOCR-VL (CPU) on 257 pages. These gitignored files sit in the `omrs-v3` worktree.
- **Two baseline limits.** The engines ran at the same time in Experiment 37, so baseline timings carry shared load. MLX conversions are not byte copies of the PyTorch weights.
- **Published builds exist for every arm (checked 2026-10-30).** dots.mocr: mlx-community MLX bf16 and 8-bit; community GGUF bf16 and Q8_0 with mmproj, some made with the llama.cpp converter. `dots-studio/dots.mocr` and `rednote-hilab/dots.mocr` hold the same commit and weights. PaddleOCR-VL 1.6: official GGUF (one 16-bit file plus mmproj); OpenGryd MLX 16-bit and 8-bit. Commit `16656b7` said otherwise and was wrong.
- **Sources chosen.** D3 and D4 use our own conversion of the pinned dots.mocr revision, with a community bf16 file as a cross-check (OI-9). P4 quantises the official P3 file. The MLX arms use the published builds at pinned revisions.
- **No OMRS engine folder for either runtime.** The `OcrEngine` contract and `OcrRoutes` know neither GGUF nor MLX. The experiment cannot use the host path.
- **Licence.** The dots.mocr agreement covers derivative works. A GGUF conversion and an MLX conversion are both derivatives.

## Goals / Non-Goals

**Goals:**

- Give a fair comparison of llama.cpp and MLX arms against each engine's shipped backend, on the Experiment 37 pages.
- Make the llama.cpp arms the only arms that can decide a runtime.
- Keep the operator in control of gates, installs, downloads and runs.
- Reuse Experiment 37 tools so the new numbers follow the same rules.

**Non-Goals:**

- Adding an engine folder, route, setting or dependency for either runtime.
- Testing other hardware or other models.
- Changing the maths detector or the routing gates.

## Decisions

### D1. Standalone runners, not the host path

Run each new arm from a standalone script in its own environment. Each script writes the Experiment 37 output layout under the new arm names. The comparison concerns the runtime, so the scripts reuse the engine constants and post-processing.

- Alternative: build a GGUF or MLX engine folder first. Rejected. It changes shipped code before evidence exists.

### D2. Hold everything except the runtime

Keep the prompt, render size, token cap, decoding rule and `layout.py` post-processing identical to the shipped engine. Output differences then trace to the runtime, the conversion and the numerics together. The experiment says so.

### D3. llama.cpp is the decision runtime

GGUF arms run through llama.cpp build 11941, as ADR-103 requires. Each GGUF arm pins its build and file hashes in the `runtime` block before the first score. `runtime_under_test` is `true`, because the runtime is the variable.

MLX arms run through `mlx-vlm`. They are not in the `runtime` block. They cannot lead to a runtime decision.

### D4. Memory is the sum of processes

Sample the peak footprint of the client process and of any server process, and report the sum.

### D5. Similarity is a defined metric

Use the Dice coefficient over token multisets with the Experiment 33 tokeniser.

### D6. Gates belong to the operator

Gates C1 to C5 decide. C6 and C7 inform. The operator set them on 2026-10-06. Any later change is a dated amendment.

### D7. Review only where it matters

Per arm, the operator reviews the 10 lowest-similarity pages, every page the noise screen flags, and 5 random pages (seed 41).

## Risks / Trade-offs

- [An 8-bit failure cannot show whether quantisation or the runtime caused it] → The conditional 16-bit diagnostic runs on the failed gate's pages. It never changes a verdict.
- [Our dots.mocr conversion may not load or may differ from community builds at build 11941] → Smoke test and cross-check first (OI-2, OI-9). A failure stops that arm only and is a finding.
- [Baseline timings include shared load] → dots.mocr speed uses the 20 pages that ran alone (D0 56.62 s comes from 19 timed pages of one run, with no variance estimate). PaddleOCR-VL speed uses the 221 pages where P0 finished OK, with the all-257 figure beside it and the bias stated. Re-time a baseline only when a speed-up lands between 1.5 and 3 times (DR-1).
- [Conversions differ from the source weights] → Record each revision and SHA-256. Report differences as findings.
- [The licence tag on a conversion hides clauses] → DR-2 covers our GGUF conversion, the MLX 8-bit conversion and the cross-check GGUF. The operator decides before any download.
- [The install approval may not cover conversion tools] → Open item OI-8. The approval covers `mlx-vlm` and the llama.cpp conversion tools.
- [A long run blocks the machine] → Run detached, checkpoint per page and resume after a stop.

## Open Questions

- DR-2 extended on 2026-10-30 (operator decides before download).
- DR-4 decided on 2026-10-30: 8-bit arms only, with a conditional 16-bit diagnostic on a quality-gate failure.
- OI-1 to OI-11 (see `protocol.md`).
