# ADR-119: OCR Model Weights Live Outside the Repository

- **Date:** 2026-11-10
- **Status:** Proposed (2026-11-10; amends ADR-062 decision 5)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-062](062-isolate-paddleocr-vl-in-a-versioned-ocr-worker.md),
  [ADR-072](072-modular-ocr-engines-dots-mocr-primary-and-maths-routing.md),
  [ADR-113](113-dots-mocr-runs-on-llama-cpp.md),
  [ADR-103](103-experiments-run-local-models-through-llama-cpp-gguf.md)

## Context

Each OCR engine kept its model weights in `<engine folder>/.model-cache` by
default (ADR-062 decision 5 and the shared worker core). Git ignores the
folder, but the weights still sit inside the repository folder:

- On 2026-11-10 the two caches of `omrs-v3` held 7.6 GB (dots-mocr
  PyTorch weights 5.7 GB, PaddleOCR-VL 1.9 GB).
- Every worktree gets its own copy. The project runs one worktree per
  change, so each new worktree that provisions an engine downloads the
  weights again.
- A contributor who follows the README ends up with several GB inside the
  checkout. The repository then looks like a place for weights and data, and
  experiments copied the habit: Experiment 38 put 27 GB of model weights and
  model environments into its own `output/.models`.
- `OMRS_OCR_MODEL_CACHE` already moved the weights elsewhere, but only for an
  operator who knew about it.

The weights are the largest part of an engine and the least tied to a
checkout. The engine code and lockfile belong to a commit. The weights belong
to the machine.

## Decision

1. **The default weights root is `~/.omrs/ocr-models`.** Engine `<name>` uses
   `~/.omrs/ocr-models/<name>/`. `OMRS_OCR_MODEL_CACHE`, when set and not
   blank, replaces the root (`$OMRS_OCR_MODEL_CACHE/<name>/`). It is the
   same rule as before with a different default.
2. **The rule exists in two places and a test keeps them equal.** The worker
   core (`model_cache_dir`) resolves where an engine reads its weights. The
   host (`engine_cache_dir`) resolves where it hashes the declared runtime
   files before it starts an engine. A parity test fails when the two
   disagree. Neither function takes the engine folder any more.
3. **The old folder is not read.** OMRS does not fall back to
   `<engine folder>/.model-cache`. An operator who has weights there moves
   the folder once (the OCR workers README shows the command).
4. **Tests never use the real folder.** The conftest points
   `OMRS_OCR_MODEL_CACHE` at an empty temporary folder for every test. A
   test of the default sets `HOME` and unsets the variable.
5. **Experiments keep weights outside their folder too.** `experiments/AGENTS.md`
   says: keep model weights and model environments in the Hugging Face cache
   or the local data store, and never download them into `output/`. The plan
   pins each file by SHA-256, so a model outside the folder stays
   reproducible.

This ADR sets where weights live. It does not decide how a package install
gets the engine code and environments (a separate, parked proposal,
`ocr-engine-install-command`).

## Consequences

### Positive

- A checkout or worktree no longer holds OCR weights. One set of weights
  serves every worktree on the machine.
- A new contributor gets the right layout without reading about an
  environment variable.
- A test run cannot read, hash or write the operator's real weights.
- Experiments stop growing by tens of GB inside the repository.

### Negative

- **Breaking for existing installs.** An engine whose weights sit in the old
  folder looks in an empty folder after the change. The engine reports itself
  as not provisioned, or re-downloads, until the folder is moved.
- **The live app needs a manual step.** Its hand-built worker copy under
  `~/.omrs/ocr-workers` still reads the old location until that copy is
  refreshed from the repository. The operator moves
  `~/.omrs/ocr-workers/engines/<engine>/.model-cache` to
  `~/.omrs/ocr-models/<engine>` and refreshes the worker code in the same
  step, because the host and the worker must use the same rule.
- Two copies of one rule still exist (decision 2). The parity test is the
  guard.

### Neutral

- `~/.omrs` also holds the workspace, the LanceDB data and the worker
  folder, so the weights join folders that already live there.
- The engine fingerprint does not include the cache path, so documents are
  not re-indexed.
- The weights of the llama.cpp router models stay where they were (the
  `file` entries in `omrs.jsonc`).

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Keep `.model-cache` in the engine folder and document `OMRS_OCR_MODEL_CACHE`** | The default is what people follow. It leaves several GB in every worktree and relies on the reader finding the variable. |
| **Fall back to the old folder when it exists** | It keeps existing installs working without a move, but the folder in use then depends on what is on disk. Two possible locations is the pattern this ADR removes. The cost of the move is one `mv`. |
| **XDG data folder (`~/.local/share/omrs`)** | OMRS already keeps the workspace, the worker folder and the data under `~/.omrs`, and the project documents that path. A second root adds a place to look. |
| **The Hugging Face cache** | The dots-mocr fetch step pins each file by SHA-256 into a folder it is given, and Paddle keeps its own cache layout. The Hugging Face layout (blobs and snapshot symlinks) fits neither. |
| **Do nothing** | The repository keeps growing with weights, and experiments copy the habit. |

## References

- `ocr-workers/core/src/omrs_ocr_worker_core/engine.py` (`model_cache_dir`)
- `src/omrs/integrations/ocr_worker/routes.py` (`engine_cache_dir`)
- `tests/test_ocr_worker_core.py` (default and parity tests)
- `tests/conftest.py` (`_isolated_ocr_model_cache`)
- `ocr-workers/README.md#model-cache`, `docs/guides/configuration.md`
- `experiments/AGENTS.md` (Local models)
- Commits `8187b11f` and `843b3a4e` on `v3`
