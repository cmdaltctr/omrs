## Why

A user who wants a local model must find a GGUF repo on Hugging Face, pick a quantisation, and type an id such as `Qwen/Qwen3-4B-GGUF:Q4_K_M` into the llama.cpp card. For Ollama they must know the exact name and run `ollama pull` in a terminal. Most users do not know these steps. The managed llama.cpp server also downloads a `-hf` model silently at start, so a large model shows no progress and can end in `timeout`.

## What Changes

- Add a **Get a model** panel to the llama.cpp and Ollama provider cards. The user types a name, sees matching models, picks a file, and presses Download.
- Search Hugging Face from the web server: GGUF repos only (`filter=gguf`), sorted by downloads, with the repo's GGUF files, their quantisation labels and their sizes. One search serves both providers, because Ollama can pull a Hugging Face GGUF as `hf.co/{org}/{repo}:{quant}`.
- Give the Ollama panel a short built-in list of common Ollama library names, plus a typed name. No scraping of ollama.com.
- Run each download as a job with byte progress, one at a time per server, that the user can cancel.
  - llama.cpp: download with `huggingface_hub` into the standard Hugging Face cache. Both the managed `llama-server -hf` and the Llama desktop app read that cache.
    - When omrs runs the Chat server (managed), **Use this model** saves the model value through the existing save route and offers a restart.
    - When the server is the user's own, such as the Llama app router on port 9931, omrs does not control it. The panel shows where the file is, says that the server must load it (the Llama app lists cached models when it starts), and offers **Refresh models**, which re-reads the existing model list.
  - Ollama: relay the progress of the local Ollama `POST /api/pull`. The model then shows in the existing model list.
- Check free disk space before a download starts. Show a gated repo as gated, and refuse its download when no `HF_TOKEN` is set.
- Add the model source as an optional field of the provider descriptor, so a card shows the panel only when its provider declares a source. No branch on provider names.
- New HTTP routes in `openapi.yaml`, guarded by the browser session with the `manage` scope. Saving the downloaded model as the server's model keeps the existing `credentials` rule.
- Add ADR-106 and update the provider, web workspace, configuration and architecture guides.

## Capabilities

### New Capabilities

- `model-downloads`: search for local models, list the downloadable files of one model, download one file set as a job with progress and cancel, and the guardrails on names, sizes, scopes and network use.

### Modified Capabilities

None. The llama.cpp model rule, the argument list, the scopes of `PUT /v1/llamacpp/server` and the model-list route stay as they are. The new panel uses them without a change.

## Impact

- **Backend:** new adapters `integrations/huggingface_models.py` (search, file list, download) and `integrations/ollama_pull.py` (pull stream); pure name and quantisation rules in `core/providers/model_sources.py`; an optional `model_source` field on `ConnectionDescriptor` set by the llama.cpp and Ollama descriptors; a `ModelDownloadJob` on `WebRuntime` in `transports/api/model_download_job.py`; a thin route group `transports/api/routes/model_downloads.py`.
- **HTTP contract:** five new operations (search, file list, start, status, cancel) in `openapi.yaml` and the conformance families.
- **Front end:** `web/src/api/modelDownloads.ts`, a `ModelDownloadPanel` under `web/src/settings/`, and the llama.cpp and Ollama cards.
- **Dependencies:** none new. `huggingface-hub>=1.0` and `httpx` are in the base install; the locked `huggingface_hub` 1.27 has `tqdm_class` and `dry_run` on `hf_hub_download`.
- **Network:** the server contacts `huggingface.co` only when the user searches, opens a model or downloads. It contacts no host at start-up or in the background.
- **Docs:** ADR-106, `docs/adr/ADR_README.md`, `docs/guides/providers.md`, `docs/guides/web-workspace.md`, `docs/guides/configuration.md`, the integration inventory in `docs/guides/architecture.md`, `src/omrs/transports/api/README.md`.
- **Tests:** new unit and route tests, front-end tests, and new pins in `tests/test_clean_base_tripwire.py`.
