# ADR-106: The App Searches and Downloads Local Models

- **Date:** 2026-10-29
- **Status:** Accepted (2026-10-29; merged to v3 at PR #148, merge commit `8c8b6f6c`; browser and live checks passed)
- **Deciders:** Maintainer
- **Related:** [ADR-084](084-context-windows-and-an-owned-llama-server.md) (the managed llama.cpp server and its child environment), [ADR-103](103-experiments-run-local-models-through-llama-cpp-gguf.md) (local models are llama.cpp GGUF)
- **Change:** `openspec/changes/archive/2026-10-29-add-model-search-and-download/`
- **Amended by:** [ADR-108](108-local-chat-and-classification-stay-apart.md) (decision 4: the saved Chat server choice decides who runs the server, and Use this model saves the Chat model)

## Context

A user who wants a local model must find a GGUF repo on Hugging Face, pick a quantisation and type an id such as `Qwen/Qwen3-4B-GGUF:Q4_K_M`. For Ollama the user must know the exact name and run `ollama pull` in a terminal. The managed llama.cpp server downloads a `-hf` model at start with no progress, so a large model can end in `timeout`.

Facts that shape the decision:

- Hugging Face has public read endpoints for search (`GET /api/models?filter=gguf`) and for the files of one repo (`GET /api/models/{repo}/tree/{sha}`). Metadata of gated repos is public.
- `huggingface-hub` 1.27 and `httpx` are base dependencies. `hf_hub_download` takes `tqdm_class` and `dry_run`.
- Ollama has no public search API. It pulls any Hugging Face GGUF as `hf.co/{org}/{repo}:{quant}`.
- The live setup on the development machine uses the Llama desktop app on port 9931, a server that omrs does not own.

## Decision

1. **The provider descriptor declares the model source.** `ConnectionDescriptor` gets an optional `model_source` field: `huggingface-gguf` for llama.cpp, `ollama-pull` for Ollama, `None` for every other provider. A card shows the Get a model panel only when the field is set. The job picks its adapter from a two-entry table keyed by the source kind, not by provider name. A third source turns the table into a registry with `register()` lines.
2. **Reads use the REST API without a token. The download uses the library.** Search and file list are fixed `GET` requests over `httpx`, with a 10-second timeout, no redirect to another host, a body limit and no `Authorization` header. The download calls `hf_hub_download` at the pinned revision, so files land in the standard cache layout and use the Xet transfer path.
3. **llama.cpp files go to the shared Hugging Face cache.** The model value is `org/name:LABEL`, which the existing `-hf` path loads from the cache. `HF_HUB_CACHE` joins the child environment of an `-hf` model, so the managed server reads the folder that the download wrote. The fallback, if a build stops reading that cache, is to save the absolute `.gguf` path.
4. **An external server is told, not controlled.** When omrs does not run the Chat server, the panel offers no Use this model. It names the cache folder, tells the user to relaunch the Llama app, and offers Refresh models. omrs does not edit `models.ini` or send a signal to the app.
   - *Amended by [ADR-108](108-local-chat-and-classification-stay-apart.md) (2026-10-29):* the saved setting `llamacpp_chat_server`, not the server state, decides who runs the Chat server. With `managed`, Use this model saves the downloaded value as the Chat model (provider `llamacpp`) through `PUT /v1/settings/chat`, then offers Restart. It shows in every server state. With `external`, the panel stays as this decision says.
5. **No scraping of ollama.com.** The Ollama search shows a fixed list of common library names, then the Hugging Face results as `hf.co/{org}/{repo}`.
6. **One download job.** `ModelDownloadJob` on `WebRuntime` runs one download at a time, reports bytes, and stops on cancel, on a 60-second stall and at shutdown. On Xet, progress counts the network bytes as well, because the assembly progress can stay silent for more than 60 seconds on a large file (found in the live and browser checks). It runs no subprocess. Errors map to fixed reasons; no exception text or token reaches a response or a log.
7. **Cancel on Xet uses a private function, and a cancelled download starts again.** On the plain HTTP path, an exception from the progress class stops the download. On the Xet path `hf_xet` ignores that exception, so a watcher thread calls `huggingface_hub.utils._xet.abort_xet_session()`. A test pins that this function exists. The `huggingface-hub` floor is 1.23.0, the first release with this function and with the `update_transfer` progress route (found by the CI floor job, which installs the oldest allowed version). The library deletes the partial file, so a later download fetches all bytes again. Ollama keeps its partial layers and resumes.
8. **The `manage` scope guards every route.** Search makes the server contact an outside host, so it needs `manage`, not `read`. A bearer token never gets `manage`. Saving the downloaded model keeps the `credentials` rule of the existing save route.

## Pre-build checks (2026-10-29)

- **Cache reuse (task 1.1).** The machine has no separate `llama-server` program. The Llama app ships `~/.llama-app/llama` (build 11941, commit 19ff817fb); its `serve` command is the llama.cpp server. With `--offline`, a closed endpoint and a scratch `HF_HUB_CACHE` filled by `hf_hub_download`, `llama serve -hf unsloth/SmolLM2-135M-Instruct-GGUF:Q2_K` loaded the model and answered `/health`. The fallback of decision 3 does not apply.
- **Llama app (task 1.1b).** Llama app 0.46.1 did not list a newly cached model while it ran. It lists the cache when it launches. The relaunch check moved to the live checks (task 8.4).
- **Progress and cancel (task 1.2, `huggingface_hub` 1.27.0, `hf_xet` 1.6.0).** Every small GGUF repo checked is on Xet; the plain HTTP path was checked with `HF_HUB_DISABLE_XET=1`. Byte updates arrive on both paths. An exception from `update()` stops HTTP but not Xet. `abort_xet_session()` from another thread stops Xet at once, and the next download works. No partial file stays on either path.
- **Ollama pull (task 1.3, Ollama 0.40.13).** Closing the `POST /api/pull` stream at 21.4 MB stopped the pull. A second pull of the same name started at 21.4 MB and ended with `success`.

## Consequences

### Positive

- A user gets a local model from the app with sizes shown before the download, progress and cancel.
- One search serves both local providers.
- A provider gets the feature by setting one descriptor field.
- The server contacts `huggingface.co` only when the user searches, opens a model or downloads.

### Negative

- Cancel on Xet depends on a private `huggingface_hub` function. If an upgrade removes it, the pinning test fails, and until a fix a Xet download stops only at its end.
- A cancelled or failed llama.cpp download starts again from zero.
- The user must relaunch the Llama app before it lists a new model.

### Neutral

- Downloaded files stay in the Hugging Face cache or in Ollama after a rollback and work with a model value set by hand.
- The app has no delete or disk-usage view for downloaded models.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| A strategy registry for model sources now | Two fixed sources, each with one adapter. The table becomes a registry at a third source. |
| `HfApi.list_models()` for the reads | It has no per-call timeout or body limit, and it sends a stored token by default. |
| Our own `httpx` download into the cache | It would copy the cache layout and Xet logic of the library. |
| Let `llama-server -hf` download at start | No progress, no cancel, and the card can report `timeout` on a large model. |
| Scrape `ollama.com` for search and tags | HTML scraping breaks without warning and adds a third host. |
| Run each download in a child process and kill it on cancel | Uses only public functions, but breaks the no-subprocess rule of the job and adds process handling. |
| Turn Xet off for omrs downloads | The switch is process-wide, so every Hugging Face download in `omrs web` gets slower. |

## References

- `src/omrs/core/providers/model_sources.py`, `src/omrs/integrations/huggingface_models.py`, `src/omrs/integrations/ollama_pull.py`
- `src/omrs/transports/api/model_download_job.py`, `src/omrs/transports/api/routes/model_downloads.py`
- `web/src/settings/ModelDownloadPanel.tsx`
- `openspec/changes/archive/2026-10-29-add-model-search-and-download/design.md` (D1 to D10 and the check results)
