# Design: reproducible experiment runtime

## Context

See `proposal.md` for the reason. Current state that shapes the approach:

- `experiment.json` is validated by a pydantic model in `src/omrs/core/experiment_records/record.py`. It rejects unknown keys. The package ships `schema/experiment.v1.schema.json`, and a test keeps the two identical.
- `omrs experiments check` (`check.py`) reads records, plans and run records and writes nothing. It already reads `plan.json` for the `plan-changed` warning.
- `experiments/_lib/run_record.py` appends one `omrs-run-record/1` line per run through `core/experiment_records/run_record.py`. That model also rejects unknown keys.
- `experiments/_lib/preflight.py` and `manifest.py` hold the existing checks that run before any measurement.
- The llama.cpp server reports its build on `GET /props` as `build_info` (for example `b11671-ba3c05f71`). In router mode, `GET /v1/models` lists each model with the arguments it was started with, including the model path.
- Templates live in `core/experiment_records/templates/`. `tests/unit/test_experiment_skill_drift.py` keeps the repository skill copy `.agents/skills/s-experiment/references/` byte-identical to them. The personal skill `~/.agents/skills/s-experiment/` is a general copy for all projects, so it gets the rule in its own words, not a byte copy.
- Measured on 27 October 2026 on this Mac: the same Qwen3 embedding GGUF through Ollama 0.40.11 and through llama.cpp build 11671 gave identical vectors (cosine 1.0 on 120 texts). Median time was 17.0 ms and 15.7 ms per text. oMLX scored Clef-flash at 0.45 s a page against 0.84 s for llama.cpp Q8_0, but it runs only on Apple silicon.

## Goals / Non-Goals

**Goals:**

- One runtime for local models in new experiments, with the exact weights and build in the plan.
- A check that stops a run before scoring when the live server differs from the plan.
- A purpose field that separates paper evidence from project tuning, enforced by the checker for paper evidence.

**Non-Goals:**

- Changing any past experiment record, plan or output.
- Moving CI, the retrieval tripwire baselines or the live OMRS app from Ollama.
- Running the re-runs. Each chosen re-run is its own experiment and change.
- Rules for model types that llama.cpp cannot run, such as the ONNX reranker and the OCR engines. The existing runtime-manifest requirement still covers them.

## Decisions

### D1. llama.cpp GGUF is the only local runtime for experiment evidence

llama.cpp runs the same engine on macOS, Linux and Windows. A GGUF file is one file with a published SHA-256. Ollama hides the engine (MLX on a Mac for some families since 0.40) and ships its own quantisations. MLX and oMLX run only on Apple silicon.

Alternatives: Ollama with a pinned version and the MLX switch turned off. Rejected, because the engine choice stays hidden and the Q4_K_M files cannot be downloaded elsewhere. oMLX as an allowed fallback. Rejected, because a Mac-only fallback breaks the reason for the rule. Its parity numbers are kept in ADR-103 as evidence.

The exception for an experiment whose manipulated variable is the runtime keeps runtime comparisons possible (Experiment 38's build comparison, Experiment 41 on MLX OCR).

### D2. `purpose` is an optional key in format 1, not a format 2

Adding the key to format 1 leaves all 49 existing records valid with no edit, and a missing key reads as `optimisation`. A format 2 would force every record to be rewritten, which this change must not do.

Trade-off: an `omrs` install older than this change rejects a record that has the key. Only this project writes these records, and the live app is reinstalled with the change. The same choice applies to the optional `runtime` key in the run record.

### D3. The checker enforces the rules only for `publication`

All new experiments should follow the runtime rule, and the guide and templates say so. The checker makes it an error only for `publication`, because:

- Quick experiments have no `plan.json` to check.
- Old records have no purpose and must stay quiet.
- An optimisation experiment that breaks the rule is not cited anywhere, so a guide rule is enough.

A `publication` experiment must also be Confirmatory, so its protocol and plan are committed before the first run. That is pre-registration, which a paper needs.

### D4. Shape of the `runtime` block

```json
"runtime": {
  "runtime_under_test": false,
  "models": [
    {
      "role": "embedding",
      "repository": "Qwen/Qwen3-Embedding-0.6B-GGUF",
      "file": "Qwen3-Embedding-0.6B-Q8_0.gguf",
      "sha256": "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439",
      "runtime": "llama.cpp",
      "build": 11671,
      "server_args": {"pooling": "last", "ubatch-size": 8192, "ctx-size": 8192}
    }
  ],
  "references": [{"role": "reference", "provider": "cloudflare", "model": "clef-flash"}],
  "tolerance": [
    {"metric": "recall_at_10", "max_abs_change": 0.01},
    {"item_score": "noul", "max_abs_change": 0.10}
  ]
}
```

One pydantic model in `core/experiment_records/` validates the block. The checker and the run-time check both use it, so they cannot disagree. With `runtime_under_test: true`, an entry may name another runtime and must give a `version` and a SHA-256 for each weights file.

The build is an exact number, not a minimum. A run on another build adds a plan amendment first (spec "A run checks the live server against the plan"). The tolerance then says whether the new result still counts as the same.

### D5. The live-server check lives in `experiments/_lib/`

A new `experiments/_lib/llamacpp_runtime.py` reads `/props` for the build and `/v1/models` (router mode) or `/props` `model_path` (single model) for each file path. It hashes each file and compares the results with the plan. It raises the existing `PreflightError` on a difference and returns the found values for the run record. It talks only to `127.0.0.1` (ADR-074 decision 6). Because of that, the model file is on the same machine and can be hashed.

Hashing a 9.7 GB file takes about 30 seconds. That is acceptable once per run. The check does not cache hashes, because a cache could hide a replaced file.

`record_run_start` gains an optional `runtime` argument. The run record stores it as an optional `runtime` key: the build and one `{file, sha256}` per model.

### D6. One ADR, ADR-074 amended

ADR-103 records the rule, the purpose tier, the measurements above and the rejected alternatives. ADR-074 keeps decisions 1, 2 and 4 to 7. Decision 3 (MLX 8-bit fallback) is withdrawn, and ADR-074 gets an "Amended by ADR-103" note. AGENTS.md Critical Gotcha 16 drops "or MLX 8-bit".

### D7. Choosing what to carry forward is the user's call

The change writes `carry-forward.md` in the change folder. It lists each past experiment with the local runtime and models it used and what a `publication` re-run would need. The user marks which experiments go forward. The change does not decide this, and it does not start any re-run.

## Risks / Trade-offs

- [A GGUF build differs a little across GPU back ends (Metal, CUDA, CPU)] → The plan states a tolerance. Reproduction is judged against it, not against identical numbers.
- [Older `omrs` installs reject records with `purpose`] → Reinstall the live app with the change. The checker on this branch reads both shapes.
- [Some models have no official GGUF] → The plan may name a community GGUF with its SHA-256. The rule asks for a public file, not an official one.
- [The runtime rule for `optimisation` experiments is a guide rule only] → Accepted (D3). An optimisation result that turns out to matter is re-run as `publication`.
- [Hashing large files slows each run start] → About 30 seconds for 9.7 GB, once per run.

## Migration Plan

1. Merge the code, templates and docs. No record is rewritten.
2. Reinstall the live app with locked constraints so the library reads the new field.
3. Rollback: revert the merge. Records created with `purpose` would then fail the older loader. Remove the key from those records by hand. Only records created after the merge can have it.
