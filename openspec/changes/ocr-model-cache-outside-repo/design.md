## Context

See `proposal.md` for the problem. The code that decides the weights folder exists twice, because the host and the worker are separate programs:

- `omrs_ocr_worker_core.engine.model_cache_dir(engine_name, engine_dir)` runs inside the engine environment and tells the engine where its weights are.
- `omrs.integrations.ocr_worker.routes.engine_cache_dir(name, engine_dir, environ)` runs in the host and finds the declared runtime files that the host hashes before it starts an engine.

The two engines and the smoke scripts each repeat a small copy of the rule. The tests build engine folders with a `.model-cache` inside them and clear `OMRS_OCR_MODEL_CACHE` in seven files.

## Goals / Non-Goals

**Goals:**

- A checkout or worktree holds no OCR weights by default.
- One rule, with a test that fails when the host copy and the worker copy disagree.
- No test touches the operator's real `~/.omrs`.

**Non-Goals:**

- How a package install gets the engine code and environments (`ocr-engine-install-command`).
- A reason line in the Integrations page that names the old folder (see Open Questions).
- Any change to the model files, the engine fingerprint, routing or the llama.cpp router models.

## Decisions

### D1. Default root `~/.omrs/ocr-models`

OMRS already keeps the workspace, LanceDB data and the worker folder under `~/.omrs`, and the docs name that path. Rejected: an XDG data folder (a second root), the Hugging Face cache (the dots-mocr fetch step pins files by SHA-256 into a folder it is given, and Paddle keeps its own layout), and keeping the in-folder default with better docs (the default is what people follow).

### D2. Neither function takes the engine folder

Nothing in the new default depends on the engine folder, so `model_cache_dir(engine_name)` and `engine_cache_dir(name, environ)` drop the argument. The two engine packages drop their `ENGINE_DIR` and `WORKER_DIR` use for the cache.

### D3. No fallback to the old folder

A fallback would make the folder in use depend on what is on disk, which is the pattern this change removes. The cost is one `mv` per engine. The live app needs the same move (see Migration Plan).

### D4. Tests

An autouse fixture in `tests/conftest.py` sets `OMRS_OCR_MODEL_CACHE` to an empty temporary folder. A helper module `tests/fixtures/ocr_worker/model_cache.py` gives the fixtures one way to find an engine's folder. `clean_environ` in the runtime harness keeps the cache variable (it only drops the runtime URL), so the manager and the fixtures see the same folder. Tests of the default set `HOME` and unset the variable. Seven test files stop clearing the variable.

### D5. The parity test

`test_host_and_worker_agree_on_the_model_cache` runs for the variable unset, blank, spaces and set. Proof that it works: change `MODEL_CACHE_DEFAULT_ROOT` in the host copy and see it fail, then restore.

### D6. Experiments

`experiments/AGENTS.md` (Local models) gets two lines. Experiment 38 showed the habit: 27 GB in `output/.models`.

## Risks / Trade-offs

- [An existing install looks in an empty folder] → The README and the guides show the one-time `mv`. The Migration Plan covers the live app.
- [Two copies of the rule] → The parity test.
- [A new test forgets the fixture] → The fixture is autouse, so every test has it.
- [The tripwire pin] → Recount by test-ID diff at apply time. The branch counted +4.

## Migration Plan

1. Wait for Experiment 35 to finish. Do not merge into the Exp 35 branch after its freeze.
2. Create a worktree from `v3`. Apply the tasks. The branch `parked/ocr-model-cache-outside-repo` shows one working version.
3. Move each engine's `.model-cache` to `~/.omrs/ocr-models/<engine>` in every worktree that has one.
4. Live app, in one step (the host and the worker must use the same rule): move `~/.omrs/ocr-workers/engines/<engine>/.model-cache` to `~/.omrs/ocr-models/<engine>`, refresh the worker code in `~/.omrs/ocr-workers` from the repository, reinstall the app, restart, and check the Integrations page.
5. Rollback: revert the commit. Weights already moved go back with `mv`.

## Open Questions

- Should the Integrations page say which folder an engine looked in when its files are missing? Left out so far because the code today reports no such reason.
- The dots-mocr `.model-cache` in `omrs-v3` and its DATA copy differ in two files (`modeling_dots_vision.py`, a stale project name in a comment). Settle this when the old folder is moved, not here.
