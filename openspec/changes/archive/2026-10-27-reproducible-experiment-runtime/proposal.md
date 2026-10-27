# Proposal: reproducible experiment runtime

## Why

Experiments have run local models through three runtimes: Ollama, llama.cpp and MLX (a Python helper, and lately oMLX). The results are not comparable, and some cannot be reproduced off a Mac:

- MLX runs only on Apple silicon.
- Ollama 0.40 runs some model families on MLX on a Mac and on llama.cpp elsewhere, so one Ollama tag can give different numbers on different machines.
- Ollama's own Q4_K_M files (`qwen3:0.6b`, `qwen3:4b`) match no public GGUF file, so nobody can download the exact weights outside Ollama.

Until now every experiment was an optimisation study for this project. Some results will now go into papers, and a paper result must be reproducible by another group on another platform. On 27 October 2026, the same Qwen3 embedding GGUF gave identical vectors through Ollama and through llama.cpp, and llama.cpp was slightly faster (15.7 ms against 17.0 ms per text), so moving to llama.cpp costs no speed.

## What Changes

- New experiments run every local language, embedding and decision model through llama.cpp (`llama-server` or `llama serve`) with a public GGUF file. Ollama, MLX and oMLX are not used for experiment evidence. Hosted APIs stay allowed as named reference arms.
- One exception: an experiment whose manipulated variable is the runtime itself (for example, Experiment 41 on MLX OCR backends) may run the runtimes it compares.
- `plan.json` gains a `runtime` block. For each local model it records the Hugging Face repository, file name, SHA-256, llama.cpp build and the server arguments that affect output. It also records a tolerance: how far a result may move on other hardware and still count as reproduced.
- Each run checks the live server against the plan before it scores: the build number from `/props` and the SHA-256 of the model file. A mismatch stops the run.
- `experiment.json` gains an optional `purpose` field: `optimisation` or `publication`. A record without the field counts as `optimisation`. Existing records are not changed.
- A `publication` experiment must be Confirmatory and must have the `runtime` block. The checker reports an error when it does not.
- Past experiments stay as they are. An experiment chosen for a paper is re-run as a new `publication` follow-up (for example `38a`). It does not change its old record.
- `omrs experiments new` and the web New experiment form take a purpose. The library shows it.
- A new ADR records the rule. ADR-074 decision 3 (MLX 8-bit as a fallback) is withdrawn, and AGENTS.md Critical Gotcha 16 is updated to match.
- The experiments guide, the package templates and both copies of the `s-experiment` skill state the rule.

Out of scope: moving CI and the retrieval tripwire baselines from Ollama to llama.cpp, moving the live OMRS app from Ollama, and the re-runs themselves. Each is a separate change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `experiment-records`: the record gains the optional `purpose` field. The checker enforces the publication rules. The scaffold and the folder guide carry the purpose and the runtime rule.
- `experiment-validity-gates`: a new requirement that local models run through llama.cpp GGUF, pinned in the plan and checked against the live server before a run.
- `workspace-experiment-library`: the New experiment form asks for the purpose, and the library shows it.

## Impact

- Code: `src/omrs/core/experiment_records/` (`record.py`, `schema/experiment.v1.schema.json`, `check.py`, `scaffold.py`, `templates/`), a new run-time identity check beside `run_record.py`, `transports/cli/experiments.py`, `transports/api/routes/experiment_library.py`, `core/workspace/experiment_pages.py`, and `web/src/experiments/library/` (`NewExperimentForm`, labels).
- Docs: new ADR-103, ADR-074 (Amended by ADR-103), `docs/adr/ADR_README.md`, AGENTS.md Gotcha 16, `experiments/AGENTS.md`, `docs/guides/experiment-records.md`.
- Skills: the repository copy `.agents/skills/s-experiment/` (kept byte-identical by `tests/unit/test_experiment_skill_drift.py`) and the personal copy `~/.agents/skills/s-experiment/`.
- Compatibility: an `omrs` install older than this change rejects a record that has `purpose`, because format 1 rejects unknown keys. The live app is reinstalled with the change.
- Dependencies: none. llama.cpp stays an external program called over HTTP (ADR-074 decision 7).
