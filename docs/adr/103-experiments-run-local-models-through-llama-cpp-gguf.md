# ADR-103: Experiments Run Local Models Through llama.cpp GGUF

- **Date:** 2026-10-27
- **Status:** Proposed
- **Deciders:** Maintainer
- **Related:** [ADR-074](074-run-local-decision-models-through-llama-cpp-q8-0-gguf.md) (this ADR withdraws its decision 3, the MLX 8-bit fallback), [ADR-097](097-experiment-records-versioned-format.md) (experiment record format; this ADR adds an optional key to format 1), [ADR-024](024-dual-deployment-modes.md) (local-first, cloud opt-in)
- **Change:** `openspec/changes/reproducible-experiment-runtime/` (design D1 to D7)

## Context

Experiments have run local models through three runtimes: Ollama, llama.cpp and MLX (a Python helper, and lately oMLX). The results are not comparable, and some cannot be reproduced off a Mac:

- MLX and oMLX run only on Apple silicon.
- Ollama 0.40 runs some model families on MLX on a Mac and on llama.cpp elsewhere. One Ollama tag can give different numbers on different machines, and Ollama does not say which engine it used.
- Ollama's own Q4_K_M files (`qwen3:0.6b`, `qwen3:4b`) match no public GGUF file. Nobody can download the exact weights outside Ollama.

Until now every experiment was an optimisation study for this project. Some results will now go into papers. A paper result must be reproducible by another group on another platform.

### Ollama and llama.cpp, same embedding file

Measured on 27 October 2026 on the maintainer's Mac (source: `openspec/changes/reproducible-experiment-runtime/design.md`, section Context). The same Qwen3 embedding GGUF ran through both runtimes on 120 texts.

| Runtime | Version | Cosine with the other runtime | Median time per text |
| --- | --- | ---: | ---: |
| Ollama | 0.40.11 | 1.0 (identical vectors) | 17.0 ms |
| llama.cpp | build 11671 | 1.0 (identical vectors) | 15.7 ms |

Moving embedding work from Ollama to llama.cpp costs no speed and changes no vector.

### oMLX parity table

oMLX is faster than llama.cpp on a Mac. These are the only oMLX numbers in the repository. No agreement figures against hosted scores exist for oMLX.

| Runtime | Model | Seconds per page | Source |
| --- | --- | ---: | --- |
| oMLX | Clef-flash | 0.45 | `openspec/changes/reproducible-experiment-runtime/design.md` (Context, measured 27 October 2026) |
| llama.cpp Q8_0 | Clef-flash, `ggml-org/Clef-Flash-GGUF` | 0.84 | `experiments/38-rescue-quality-signal-2026-09-30/report.md` and `output/clef_flash_speed.json` (via ADR-074) |

oMLX is about twice as fast, but it runs only on Apple silicon. The speed gain does not outweigh a result that other platforms cannot reproduce.

## Decision

1. **llama.cpp with a public GGUF file is the only local runtime for experiment evidence.** An experiment planned after this ADR runs every local language, embedding and decision model through `llama-server` (or `llama serve`). The GGUF file must be downloadable by anyone. A community file is allowed. Ollama, MLX and oMLX are not used for experiment evidence.
2. **Hosted models stay allowed as reference arms.** The plan names the provider and the model id of each one.
3. **Runtime comparisons are the one exception.** When the runtime is the variable under test, the plan sets `runtime_under_test` to `true`. It may then run the runtimes it compares. Each arm records its runtime, `version` and the SHA-256 of each weights file.
4. **The plan pins each local model.** `plan.json` holds a `runtime` block with `runtime_under_test`, `models[]` (`role`, `repository`, `file`, `sha256`, `runtime`, `build`, `server_args`, and `version` for another runtime), `references[]` (`role`, `provider`, `model`) and `tolerance[]`. `omrs.core.experiment_records.runtime_block.load_runtime_block` validates the block. The checker and the live check both use it.
5. **The build is exact.** The plan records one llama.cpp build number, not a minimum. A run on another build first adds a plan amendment that names the new build.
6. **The plan states a tolerance.** Each `tolerance` entry names a `metric` or an `item_score` and its `max_abs_change`: the largest change that still counts as the same result on other hardware. GPU back ends (Metal, CUDA, CPU) can differ slightly. Reproduction is judged against the tolerance, not against identical numbers.
7. **Each run checks the live server before it scores.** `experiments/_lib/llamacpp_runtime.py` `verify_llamacpp_runtime(block, base_url=...)` reads the build from `/props` and each model path from `/v1/models` (router mode) or `/props` (one model). It hashes each file and compares the values with the plan. A difference raises `PreflightError` and names the expected and found value. It talks only to `127.0.0.1` (ADR-074 decision 6). It does not cache hashes. `record_run_start(..., runtime=found.as_run_record())` stores the build and one `{file, sha256}` for each model in the run record.
8. **Every experiment has a purpose.** `experiment.json` gains an optional `purpose` key in format 1: `optimisation` or `publication`. A record without the key counts as `optimisation`. `omrs experiments new --purpose {optimisation,publication}` and the web New experiment form set it. The default is `optimisation`.
9. **The checker enforces the rules for `publication` only.** A `publication` experiment must be Confirmatory, so its protocol and plan are committed before the first run. Its `plan.json` must hold a valid `runtime` block. The checker reports `publication-not-confirmatory`, `publication-plan-unreadable`, `publication-runtime-missing` and `publication-runtime-invalid` as errors. For an `optimisation` experiment, the runtime rule is a guide rule only.
10. **Past experiments stay as they are.** No record, plan or output changes. A result that a paper needs comes from a new `publication` follow-up that runs the experiment again, for example `38a`.

This ADR withdraws ADR-074 decision 3 (MLX 8-bit as an accepted fallback). ADR-074 decisions 1, 2 and 4 to 7 still hold. AGENTS.md Critical Gotcha 16 no longer names MLX 8-bit as a runtime.

## Consequences

### Positive

- Another group can download the exact weights and the exact llama.cpp build and repeat a `publication` result on macOS, Linux or Windows.
- A wrong build or a replaced model file stops the run before any score is written.
- The run record shows which build and which file hashes produced each result.
- The purpose tells a reader which results can go into a paper.
- All existing records stay valid with no edit.

### Negative

- oMLX is about twice as fast as llama.cpp on Clef-flash on a Mac (0.45 s against 0.84 s a page). Experiments give up that speed.
- Hashing a large model file at each run start takes time: about 30 seconds for 9.7 GB.
- An `omrs` install older than this change rejects a record that has `purpose`, because format 1 rejects unknown keys. The live app must be reinstalled with the change.
- The runtime rule for `optimisation` experiments is not enforced by the checker.
- Past results that a paper needs must be run again.

### Neutral

- CI, the retrieval tripwire baselines and the live OMRS app still use Ollama. Each move is a separate change.
- Models that llama.cpp cannot run, such as the ONNX reranker and the OCR engines, are not covered. The existing runtime-manifest requirement still covers them.
- llama.cpp stays an external program called over HTTP (ADR-074 decision 7). No package is added to `pyproject.toml`.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Ollama with a pinned version and the MLX switch turned off** | The engine choice stays hidden from the plan. Ollama's own Q4_K_M files cannot be downloaded outside Ollama, so another group cannot get the exact weights. |
| **oMLX (or MLX 8-bit) as an allowed fallback** | It runs only on Apple silicon. A Mac-only fallback breaks the reason for the rule. Its speed numbers are kept above as evidence. |
| **A format 2 for `experiment.json`** | Every existing record would need a rewrite, which this change must not do. An optional key in format 1 leaves them valid. |
| **A minimum build instead of an exact build** | A later build can change output. The exact build plus a plan amendment and the tolerance keeps each change visible. |
| **Enforce the runtime rule for every experiment** | Quick experiments have no `plan.json`, old records have no purpose, and an optimisation result is not cited outside the project. |

## References

- `openspec/changes/reproducible-experiment-runtime/` (proposal, design D1 to D7, specs)
- `src/omrs/core/experiment_records/runtime_block.py` (`load_runtime_block`)
- `src/omrs/core/experiment_records/check.py` (publication checker codes)
- `experiments/_lib/llamacpp_runtime.py` (`verify_llamacpp_runtime`, `FoundRuntime`)
- `experiments/_lib/run_record.py` (`record_run_start`)
- `experiments/38-rescue-quality-signal-2026-09-30/report.md` (Clef-flash runtime comparison)
- `experiments/AGENTS.md` and [Experiment records guide](../guides/experiment-records.md)
- `AGENTS.md` Critical Gotcha 16
