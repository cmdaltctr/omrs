# Proposal

## Why

OMRS selects dots.mocr as its primary OCR engine by default. On 2026-10-28 that engine was not provisioned in any worktree, and `ocr_workers_dir` was empty in the live `omrs.jsonc`. No page showed this. The Integrations page lists only pip extras, Magika and marimo. Settings › Document reading shows the engines, but it cannot set the workers folder: `ocr_workers_dir` is read-only, with the reason "set when the OCR workers are installed", and the installer (`ocr-workers/provision.py`) never sets it. Other parts that a setting depends on are also not shown: the token-aware chunking tokenizer, the reranker ONNX model, and the Ollama and llama.cpp servers. A missing tokenizer makes chunking fall back to the legacy splitter with only a log warning. The llama.cpp and OpenRouter cards always say "available", because they check only modules that every install includes.

OCR settings are also server-wide only. A user profile can choose its PDF reader on the Read document step, but it cannot choose its OCR engine or OCR routing. The archived change `add-pdf-reader-step-setting` kept OCR host-owned on purpose (its design D5). The operator now wants every document-reading setting editable in user-profile pipelines. Built-in profiles keep the server settings.

## What Changes

- The Integrations page gets three new groups:
  - **OCR engines**: each engine folder under the workers folder, plus the local OCR tier. Each shows its status (ready, not provisioned, workers folder not set) and the command that fixes it.
  - **Model files**: the token-aware chunking tokenizer at its pinned revision, the reranker model and the local OCR tier model. Each shows whether it is in the local cache and gives the command that fetches it.
  - **Local servers**: Ollama and llama.cpp. Each shows whether it responds at the configured address and which settings use it.
- The llama.cpp and OpenRouter cards keep "Base default". They also report readiness: the configured server responds, or a key reference is set. They no longer show "available" when nothing can be used.
- The OCR engines group can set the OCR workers folder. The server checks the folder before it saves it to `omrs.jsonc`, and the value applies at the next launch. `ocr_workers_dir` is no longer read-only.
- **BREAKING (spec):** the Read document step of a user-profile pipeline gets the eight OCR document-reading settings: OCR fallback on or off, both confidence and page-fraction thresholds, the routing unit, primary and fallback engine, and maths routing with its page fraction. An empty value uses the server setting. This replaces the rule that a step "SHALL NOT add an OCR route … or change an OCR setting".
- A step OCR setting enters the source's index identity, as the step reader does. A changed step OCR setting therefore reprocesses the source on the next ingest.
- Built-in profiles (`documents`, `codebase`) are unchanged. They keep using Settings › Document reading.
- **BREAKING:** `OCR_WORKER_COMMAND` and `OCR_WORKER_ENV_DIR` are removed. They predate engine folders and override the primary engine, so a step's chosen engine could be replaced without warning. Start-up refuses either variable and names `OCR_WORKERS_DIR` with `OCR_ENGINE_PRIMARY`. Settings › Document reading drops the "worker command set" note. No index identity changes.

## Capabilities

### New Capabilities

- `runtime-components`: how the server probes OCR engines, model files and local servers, and the read-only status it reports for each one.

### Modified Capabilities

- `workspace-integrations`: the page shows the three runtime groups, sets the OCR workers folder, and shows provider readiness on the llama.cpp and OpenRouter cards.
- `settings-file`: `ocr_workers_dir` leaves the read-only list. A new requirement checks the folder before it is saved.
- `workspace-settings`: the "no provider request" rule allows the keyless local server health probe of the Integrations page. Model-list and key-check requests still need a Test or List models action.
- `pipeline-graphs`: the Read document step takes the OCR settings, OCR routing follows the step's settings, and the index identity records them.

## Impact

- Server: `src/omrs/transports/api/integrations_catalogue.py` and a new runtime-components probe module. Also `routes/` for the integrations and workers-folder routes, `openapi.yaml`, `config/settings_file_write.py`, `capabilities.py` (`ocr_engine_options`) and `compose_pipeline_runs.py` (an OCR client per engine pair).
- Core: `core/ingestion/graph_adapters_catalogue.py` (`ReadParams`), `graph_adapters.py`, `graph_fingerprint.py` (`IngestionShape`) and `core/pipelines/levers.py` (host-owned hints).
- Web: `web/src/integrations/` (three groups, the workers-folder field, readiness lines) and `web/src/studio/labels.ts` (labels for the new step settings).
- Docs: `docs/guides/configuration.md`, `docs/guides/ingestion.md` and a new ADR that amends design D5 of `add-pdf-reader-step-setting`.
- No new dependency. The probes use the standard library and packages already in the base install. No probe downloads, installs or starts anything.
- Memory: two steps that select different OCR engines can keep two workers loaded at once (dots.mocr peaked at 22 GiB in Experiment 37, PaddleOCR-VL at 15 GiB). The design limits this.
