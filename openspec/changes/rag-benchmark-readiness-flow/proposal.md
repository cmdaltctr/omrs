# Proposal: master execution order to get OMRS ready for the full RAG benchmark

## Why

The doc-reading master flow is archived (`2026-11-06-doc-reading-master-flow`). The next goal is the full RAG benchmark, Experiment 35, run on RunPod. Four pieces of written work stand between OMRS and that run, and they interlock:

- `local-ocr-per-backend-cuts` (branch `feat/local-ocr-per-backend-cuts`, proposal committed `314e014e`). Per-backend local OCR confidence cuts in Settings and Studio, defaults PP-OCRv6 0.92 and Indra 0.94, no language filter on Indra, cuts enter the PDF-only identity. Forces one re-index.
- `one-llamacpp-router` (branch `feat/one-llamacpp-router`, proposal committed `19c837b8`). One OMRS-run llama.cpp router for embeddings, classification, local Chat and decision models; dots-mocr stays separate; Qwen3-Embedding-4B and Qwen3-4B by default; no Ollama in defaults, tests or docs; repo `.env` aligned with `omrs.jsonc`; pinned b11941 builds for macOS, Linux CPU and Linux CUDA, so it runs on RunPod. Forces one re-index (1024 to 2560 dimensions).
- `page-routing-panel` (branch `feat/page-routing-panel`, proposal committed `ebdd2333`). One Page routing panel in Settings and the Studio Read step, a Skip blank pages switch, and the routing guide `docs/guides/page-routing.md`. User interface only for the benchmark; it changes no result with defaults.
- `pipeline-sweep-llamacpp` (branch `feat/pipeline-sweep-llamacpp`, 5 commits, not pushed, 222 commits behind `v3` on 2026-11-06). The sweep Experiment 35 needs before it freezes. Its folder is numbered 43, which the merged Experiment 43 already uses, and its design uses the Llama app's `llama serve`, which OMRS refuses.

Without one recorded order, two branches can touch the same specs at once, the live library can re-index twice, and the sweep can run against a pipeline that is about to change.

## What Changes

- A task order only (tasks.md groups 0 to 8) with gates. No code and no capability deltas.
- The order (operator decisions 2026-11-06): cuts, then router, then one live switch (no re-index: the live collections are test data, operator 2026-11-07), then the pipeline sweep on RunPod, then Experiment 35. The page routing panel follows the router and can run beside the sweep, because it touches no runtime and no result.
- Amendment A4 (2026-11-14): `experiments/35-full-rag-benchmark-2026-11-01/preregistration.md` governs Experiment 35. Group 6 gains the pre-freeze items of its section 23 (the FreshStack full-corpus pin and timing, the halves and the MDE pilot on half A, P1 to P16, and the user's open items O1 to O6) and follows its order of work (score half A, time-stamp the selection hash on OSF, then score half B). Group 7 lists what the Part 2 protocol must hold and adds step 7.2a, the matched RAGFlow search decision (design D6).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None.

## Impact

- No code. Each group names the change or experiment whose own tasks carry the detail.
- Live state: group 4 changes the live app (`~/.omrs`, `~/.config/omrs/omrs.jsonc`, the Llama app) and re-indexes every collection once. It needs the operator's word (gate G5).
- Cost: group 5 runs on RunPod and needs the operator's word on budget (gate G6). Group 6 spends money at the pre-freeze pod and GLM-5.3 run (gate G7a, about 2 to 4 hours of pod plus about $11) and at the smoke and section 5 runs (gate G7). Group 6 adds the FreshStack full-corpus builds and the MDE pilot (estimate about $730 in all, ceiling $975, with a results-blind drop order). Group 7 adds the Part 2 RAGFlow run on half B and the descriptive E1 run, each with its own estimate and ceiling; E1 is dropped first when the budget is short.
- Parked, not in this flow: `paddleocr-vl-llamacpp-backend`, `tripwire-retirement-and-provider-symmetry` (watch its overlap with the router's key retirements), issue #161 old-print follow-up, an Indra-on-Latin follow-up, issues #173 and #174.
