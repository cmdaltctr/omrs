# Design

## Context

Facts found on 2026-10-28 in `v3` at `ac098537`:

- The Integrations catalogue (`src/omrs/transports/api/integrations_catalogue.py`) lists pip extras, Magika and marimo. The llama.cpp and OpenRouter entries probe only `llama_index.embeddings.openai_like` and `llama_index.llms.openai_like`. Every install has those modules, so the entries always report `available`.
- `capabilities.ocr_engine_options` already lists engine folders and their state for Settings › Document reading. Its reason for a missing engine does not name the licence step.
- `ocr_workers_dir` is in `READ_ONLY_KEYS` (`config/settings_file_write.py:78`) with the reason "set when the OCR workers are installed". `ocr-workers/provision.py` does not write `omrs.jsonc`, and it is not in the wheel. The live app runs from a `uv tool` environment, so its workers folder must point at a checkout.
- The Read document step (`ReadParams` in `core/ingestion/graph_adapters_catalogue.py`) takes `pdf_reader` as an option parameter. `with_pdf_reader` applies it to a settings copy in `identify_adapter` and `read_adapter`, and `IngestionShape.pdf_reader` carries it into the index identity.
- A graph run gets one OCR resource. `compose_pipeline_runs.plan_run` builds it from the settings of the first node that enables OCR (`compose_pipeline_runs.py:65-67`). Each `ManagedOcrClient` has its own lock. No lock spans two clients.
- `add-pdf-reader-step-setting` design D5 kept OCR host-owned on purpose. This change reverses that decision, and a new ADR records the reason.
- Measured memory (configuration guide, Experiment 37): dots.mocr peaked at about 22 GiB and PaddleOCR-VL at about 15 GiB.

## Goals / Non-Goals

**Goals:**

- Show every runtime component that a setting depends on, with its state, its reason and the command that fixes it.
- Let the user set the OCR workers folder from the web app.
- Let a user-profile pipeline set every OCR document-reading setting on its Read document step.

**Non-Goals:**

- Install an OCR engine or download a model from the page. `provision.py` is not in the wheel, and a 5.7 GB download with a licence step needs its own job design. The page gives copy commands only.
- Start or stop Ollama or llama.cpp from the page.
- Ship OCR workers inside the wheel, or move them out of the checkout.
- Change any default.
- Change built-in profiles. They run no saved pipeline (ADR-080).

## Decisions

### D1. One probe module, one response block

Add `src/omrs/transports/api/runtime_components.py`. It returns the `runtime` block of `GET /v1/integrations` (spec `runtime-components`). Each item is a frozen dataclass: `name`, `purpose`, `status`, `reason`, `fix`, `used_by`.

- OCR engines: reuse `resolve_engine_command`, the same resolver that parsing uses, so the page and parsing cannot disagree. Read `[tool.omrs-ocr] requires-acceptance` and `licence-file` from the engine's `pyproject.toml`, as `provision.py` does (`licence_gate`). The fix then adds `--accept-model-licence`, and the reason names the licence file. Move the manifest read into a small shared helper in `integrations/ocr_worker/`, so that `provision.py` and the probe do not hold two copies. `provision.py` must stay standard-library only, so the helper uses `tomllib` only.
- The local OCR tier: `ready` when the model loads from `ocr_local_model_directory`, or from the library cache, without the network.
- Model files: call `huggingface_hub.try_to_load_from_cache` for the tokenizer (`tokenizer.json`) and the reranker (`onnx/model.onnx` or the file that `reranker.py` loads). No network request. The fix is `uvx --from huggingface_hub hf download <repo> <file> --revision <rev>`, because a `uv tool` install does not put `hf` on PATH.
- Local servers: `httpx` (already a base dependency) with `timeout=1.0`. Ollama: `GET /api/version`. llama.cpp: `GET <base>/health` with `/v1` removed. Run all server probes with `asyncio.gather`. Remove credentials from an address with `urllib.parse` before it is shown.
- `used_by` comes from the launch settings: `ocr_engine_primary` and `ocr_engine_fallback` for engines, `embed_provider` and `metadata_llm_provider` for servers, and the chunking setting for the tokenizer.

Alternative considered: a separate `GET /v1/runtime` route. Rejected. The page already loads `/v1/integrations`, and one request keeps the page state simple.

### D2. Provider readiness on two cards

Add an optional `readiness` field (`{"ready": bool, "line": str}`) to catalogue entries. Only llama.cpp and OpenRouter set it. llama.cpp reads the llama.cpp server items from D1. OpenRouter checks that the key reference field is non-empty. It does not resolve the key. The status field and the "Base default" rule do not change, so the existing spec scenarios still hold.

### D3. Writable workers folder with a check

Remove `ocr_workers_dir` from `READ_ONLY_KEYS`. Add a rule in `config/rules.py` (beside `document_reading_problem`): absolute after `~` expansion, an existing folder, holds `engines/`. Store it with `display_path` so the home folder is `~`. The OCR engines group sends the key through the existing settings write route, so the revision check, the atomic replace and the restart-pending state are unchanged. The `env`/`.env` lock works as it does for every other key.

### D4. OCR options on the Read document step

Add the eight keys of `DOCUMENT_READING_KEYS` other than `pdf_reader` to `ReadParams`, each `None` by default. They are option parameters, like `pdf_reader`, and they are not levers. Validators reuse `document_reading_problem` for the value rules, so the step and the Settings page accept the same values. The engine fields take any folder-name string. Admission then checks availability with `ocr_engine_options` and raises `option_unavailable`, as for an uninstalled reader.

Generalise `with_pdf_reader` to `with_read_options(settings, params)`. It applies every non-`None` read option to a settings copy. `identify_adapter` and `read_adapter` both call it. `IngestionShape` gets `read_options: Mapping[str, Any]`. `identity_block` includes only the keys that are set, so a node that inherits everything gives the same identity as today (spec: inheriting keeps the standard identity).

Add the eight keys to `_HOST_OWNED_EXACT` in `levers.py`, with the hint "Set it on the Read document step". A graph-wide override then fails with `host_owned_setting`.

Studio renders `ReadParams` from its JSON schema, as it does for `pdf_reader`. The engine choices come from the existing step-option list that carries reader availability. Add the engines there with their ready state. Add labels in `web/src/studio/labels.ts`.

### D5. An Engine-scoped OCR client pool

Replace the single graph OCR resource with an `OcrClientPool` that the Engine owns:

- One lazy `ManagedOcrClient` per resolved `RouteCommand`. Two nodes that use the same engine share it. The host routes use the same pool, so a node that inherits the host engine shares the host client.
- `pool.routes(settings) -> OcrRoutes` builds the primary and fallback pair for a node's effective settings.
- One pool-wide `threading.Lock` around each parse dispatch. Two engines then never parse at the same time. A second engine stays loaded while it waits: a started worker has no idle exit and stops only when the Engine closes or the worker fails.

The pool lives in `integrations/ocr_worker/`. Composition builds it, and `core/` sees only the `ocr` resource port, so the import contracts do not change. `plan_run` stops using "the first node that wants OCR", and each read node asks the pool for its routes.

Alternative considered: one OCR resource per node. Rejected, because two nodes with the same engine would start two 22 GiB workers.

### D6. Record the reversal in an ADR

Write ADR-105, "Pipeline steps own their OCR settings". It amends design D5 of `add-pdf-reader-step-setting`. Experiment 35 needs no change: it uses built-in profile settings through its own scratch configuration.

### D7. Remove the explicit OCR worker command

`OCR_WORKER_COMMAND` (with `OCR_WORKER_ENV_DIR`) predates engine folders. It overrides the primary route, so a Read document step that names `paddleocr-vl` could still get the command's engine, with no sign. Nobody sets it: the live config and environment hold neither variable, and Experiment 37 unset it before running. Remove both settings, the override branch in `routes.py`, `worker_command_set` on the Document reading route and page, and the docs mentions.

A leftover value must not pass in silence. Add both names to `config/legacy.py` in a new "removed" group, with its own message, because they are not renames. Start-up then names `OCR_WORKERS_DIR` and `OCR_ENGINE_PRIMARY` as the replacement. The command decided only how a worker starts, never what it read, so no index identity changes. Experiment folders 24, 31, 33, 37 and 42 already ran; their scripts and outputs stay as historical records.

## Risks / Trade-offs

- [Two engines loaded at once, about 37 GiB on a 48 GB Mac] → D5 serialises parsing. The configuration guide gets a note: a pipeline that mixes engines needs memory for both until the server stops.
- [A slow probe delays the Integrations page] → 1 s timeout, all probes in parallel, and a 2 s whole-response bound in the spec.
- [The workers folder points into a worktree that is later removed] → the probe then reports `missing` for every engine, and the page shows the fix. The guide recommends the integration worktree (`omrs-v3`) or a stable checkout.
- [A changed step OCR setting reprocesses the whole collection on the next ingest] → this is intended (identity). Studio shows the existing "this change reindexes" notice for index-shaping parameters.
- [The licence reason is shown and the page has no accept action] → intended. Licence acceptance stays a deliberate command-line act.

## Migration Plan

No data migration. Saved graphs keep `null` for the new parameters, so they keep their identity. Roll back by reverting the change. Graphs saved with step OCR values then fail validation with `invalid_parameter`, and the user clears the values.

## Open Questions

- Should the OCR engines group also offer "Use this checkout" for a development server, filled from the server's own `ocr-workers/` folder? This is cheap to add, and the default is yes unless the operator objects.
