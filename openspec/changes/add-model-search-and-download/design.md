## Context

See proposal.md for the motivation. The current state that shapes the approach:

- The managed llama.cpp server (`llamacpp-server` spec, ADR-084) accepts a model as an absolute `.gguf` path (`-m`) or a Hugging Face id `org/name:tag` (`-hf`). The rules live in `core/providers/llm/llamacpp_rules.py`. `child_environment()` passes `LLAMA_CACHE`, `HF_HOME` and `HF_TOKEN` to the child for an `-hf` model.
- On the development machine, earlier `-hf` downloads are in the standard Hugging Face cache (`~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF`). `~/.cache/llama.cpp` is empty. So the llama.cpp build in use reads and writes the Hugging Face cache layout. Task 1.1 confirms this before any build work.
- The live app on the development machine uses an external llama.cpp server: the Llama desktop app, a router on port 9931 with `--models-max 1` (since 2026-10-29). omrs does not own it (`llamacpp-server` spec: "omrs owns only the server it starts"). At launch the app writes `~/Library/Application Support/Llama/models.ini` from the models in `~/.cache/huggingface/hub`, one `[org/name:LABEL]` entry each. So a file in the standard cache reaches it, but only after the app lists the cache again. Task 1.1 checks when that happens.
- `huggingface-hub>=1.0` and `httpx` are base dependencies. The locked `huggingface_hub` is 1.27. Its `hf_hub_download` takes `tqdm_class` and `dry_run`.
- Provider cards come from `ConnectionDescriptor` entries (`core/providers/llm/connection.py`). Optional capabilities already exist as optional fields (`reasoning_levels`, `credit`), and a card shows a feature only when its descriptor sets the field.
- `POST /v1/connections/{provider}/models` lists the models a running provider holds. Ollama answers from `/api/tags`.
- `InstallJob` on `WebRuntime` is the model for a single, guarded, in-memory job with a status route that the front end polls.
- Ollama has no public search API. `ollama.com/api/tags` lists only cloud models (size 0). Ollama pulls any Hugging Face GGUF as `hf.co/{org}/{repo}:{quant}`.
- Hugging Face read endpoints, checked live on 2026-10-29 without a token: `GET /api/models?search=&filter=gguf&sort=downloads&limit=` and `GET /api/models/{repo}/tree/{rev}` (each `.gguf` with its `size`).

## Goals / Non-Goals

**Goals:**

- One search flow for both local providers, with a quantisation picker that shows sizes.
- Downloads with byte progress and cancel, one at a time, that never block the event loop.
- Each external system behind its own adapter in `integrations/`, pure rules in `core/`, thin routes in `transports/api/`.
- A provider gets the feature by setting one descriptor field.

**Non-Goals:**

- Storing a Hugging Face token in the app. `HF_TOKEN` comes from the environment only, as today.
- Deleting downloaded models, or a disk-usage view of the cache.
- Downloads for the llama.cpp embedding server. Its address is read-only in the app. A file in the shared cache can still serve it, set by hand.
- Choosing the model for a role (Chat, embeddings, metadata) automatically after a download. The existing pickers do that.
- Non-GGUF formats (safetensors, MLX). ADR-103 keeps local models on llama.cpp GGUF.
- Search or download from the stdio MCP server or the CLI (gotcha 17: only `omrs web` changes the workspace).

## Decisions

### D1. The provider descriptor declares the model source

Add `model_source: ModelSourceKind | None = None` to `ConnectionDescriptor`, where `ModelSourceKind = Literal["huggingface-gguf", "ollama-pull"]`. The llama.cpp descriptor sets `"huggingface-gguf"`. The Ollama descriptor sets `"ollama-pull"`. `GET /v1/connections` returns the field per provider, so the card shows the panel from data.

The job picks its adapter from a two-entry table keyed by `ModelSourceKind`, not by provider name. This keeps invariant 11 (no `if/elif` over names).

*Alternative:* a full strategy registry under `core/providers/` with `register()` lines. Rejected: two fixed sources, both adapters to one external system each. ADR-106 records the rule that a third source becomes a registry.

### D2. Module layout

| Layer | Module | Holds |
| --- | --- | --- |
| core (pure) | `core/providers/model_sources.py` | `ModelSourceKind`, repo-id, label and Ollama-name rules, the quantisation label parser, the split-part grouping, the built-in Ollama names |
| integrations (leaf) | `integrations/huggingface_models.py` | search and file-list reads over `httpx`; the download through `huggingface_hub`; the cache path and dry-run size |
| integrations (leaf) | `integrations/ollama_pull.py` | the streamed `POST /api/pull` and its progress lines |
| transports | `transports/api/model_download_job.py` | `ModelDownloadJob` on `WebRuntime`: one job, state, progress, cancel, stall watch, shutdown |
| transports | `transports/api/routes/model_downloads.py` | five thin routes; they validate with `model_sources`, resolve the Ollama address from the provider values in use, and call the job or the adapters |

`integrations/` imports neither `core` nor `transports` (contract `integrations-are-leaves`). The routes pass plain values (base URL, repo, revision, file names, cache folder) into the adapters. `huggingface_hub` is imported inside functions, as `integrations/AGENTS.md` rule 1 asks.

### D3. Reads use the REST API; the download uses `huggingface_hub`

Search and file list send fixed `GET` requests with `httpx`: a 10-second timeout, no redirects to another host, a body limit (the same limits as `transports/api/provider_fetch.py`, written again in the adapter, because `integrations/` must not import `transports/`), and no token. Metadata of gated repos is public, so the reads never need `HF_TOKEN`.

- Search: `GET https://huggingface.co/api/models?search=<q>&filter=gguf&sort=downloads&direction=-1&limit=20&expand[]=downloads&expand[]=likes&expand[]=gated&expand[]=lastModified`.
- File list: `GET /api/models/{repo}?expand[]=sha&expand[]=gated`, then `GET /api/models/{repo}/tree/{sha}?recursive=true`. The `sha` pins the revision for the download.

The download calls `hf_hub_download(repo_id, filename, revision=sha, tqdm_class=...)` for each file of the set, in a worker thread. This gives the cache layout that llama.cpp reads, resume of `.incomplete` files, and the Xet transfer path, without our own code.

*Alternative:* `HfApi.list_models()` for the reads. Rejected: it has no per-call timeout or body limit, and it sends a stored token by default.

*Alternative:* our own `httpx` download into the cache. Rejected: it would copy the cache layout, resume and Xet logic of the library.

### D4. Where the llama.cpp files go and how the server uses them

The download writes to the default Hugging Face hub cache (`HF_HUB_CACHE`, else `HF_HOME/hub`, else `~/.cache/huggingface/hub`). The model value is `org/name:LABEL`, and the existing `-hf` path loads it from the cache. Add `HF_HUB_CACHE` to `HUGGING_FACE_ENVIRONMENT` in `llamacpp_rules.py`, so the child reads the same folder that the download wrote when the user moved the cache. This stays inside the existing requirement (only cache and token variables, only for an `-hf` model).

Task 1.1 checks this on the installed build: download a small GGUF with `hf_hub_download`, then start `llama-server -hf <id>` with the network blocked. **Fallback** if the build does not reuse the cache: the job returns the absolute snapshot path of the main file, and Use this model saves that path (`-m`). The `.gguf` path rule accepts it, so the specs do not change.

**An external server.** When the Chat server is not one that omrs runs (the managed server state is not `running` or `starting`), the panel offers no Use this model. It shows the cache folder of the file, says that the user's server must load the model, and gives a Refresh models button that refetches `POST /v1/connections/llamacpp/models`. For the Llama app, the model value in that list is `org/name:LABEL`, the same as the managed form, so the existing role pickers can select it. omrs does not edit `models.ini`, does not restart the app, and sends no signal to it.

Both servers read the default cache. When `HF_HUB_CACHE` or `HF_HOME` is set for `omrs web`, the download goes to that folder, and an external server that reads the default folder does not see it. The panel then names the folder in use, so the user can point their server at it.

### D5. Quantisation labels and split files

The parser takes the file stem, removes a split suffix `-NNNNN-of-NNNNN`, and matches the last known llama.cpp label: `IQ1_S` to `IQ4_XS`/`IQ4_NL`, `Q2_K` to `Q6_K` with `_S`/`_M`/`_L`/`_XL`, `Q4_0`, `Q4_1`, `Q5_0`, `Q5_1`, `Q8_0`, `TQ1_0`, `TQ2_0`, `MXFP4`, `MXFP4_MOE`, `BF16`, `F16`, `F32`, with an optional `UD-` prefix. Files with `mmproj` in the name are left out. Files with no known label are left out of the picker, because `-hf repo:TAG` needs a label. Parts with the same label form one entry; the entry size is the sum.

The picker preselects `Q4_K_M` when it exists, else the smallest label at 4 bits or more. It marks `Q8_0` as "closest to full quality" (gotcha 16: decision models run at 8-bit or higher).

### D6. Ollama search and pull

The search for Ollama returns the built-in names that contain the query, then the Hugging Face GGUF repos written as `hf.co/{org}/{repo}`. Choosing an `hf.co/` entry opens the same file list, and the pull name becomes `hf.co/{org}/{repo}:{LABEL}`. A typed name that passes the Ollama name rule is also accepted.

The built-in list is fixed data in `model_sources.py`, about 12 names (for example `qwen3`, `qwen3-embedding`, `gemma3`, `llama3.2`, `mistral`, `phi4`, `nomic-embed-text`, `mxbai-embed-large`, `bge-m3`, `granite-embedding`). A tagless name pulls `:latest`.

The pull sends `POST {ollama_base_url}/api/pull` with `{"model": name, "stream": true}` and reads JSON lines. Progress is the sum of `completed` over the `total` of each layer digest. The status `success` ends the job. An `error` line fails it with `failed`. A refused connection fails it with `ollama-unreachable`.

*Alternative:* scrape `ollama.com/search` and `/library/<name>/tags`. Rejected: HTML scraping breaks without warning, and it adds a third host.

### D7. One job, progress, cancel and stall

`ModelDownloadJob` lives on `WebRuntime` next to `InstallJob`, separate from it, because its guards differ (no subprocess, no `uv`, bytes not lines).

- **One at a time.** `start()` refuses with `busy` while a job runs. Installs and downloads may run at the same time; they share nothing.
- **Progress.** The Hugging Face download passes a `tqdm` subclass as `tqdm_class`. Its `update()` adds bytes to the job counter. The Ollama pull updates the counter from each line. Status reads take a snapshot under a lock.
- **Cancel.** A cancel sets an event. The `tqdm` subclass raises a private `DownloadCancelled` from `update()`, which stops `hf_hub_download` and leaves the `.incomplete` file for a later resume. The Ollama pull closes the stream, and Ollama keeps its partial layers.
- **Stall.** A watchdog task checks the time of the last byte every 5 seconds. After 60 seconds without a byte it cancels the job with the reason `stalled`.
- **Shutdown.** `shutdown_runtime()` cancels a running job and waits up to 5 seconds.
- **Errors.** Library and HTTP errors map to the fixed reasons: 401 or 403 on a gated repo to `gated`, 404 to `not-found`, a connection or read error to `network`. No exception text reaches a response or the log at a level above `debug`, and `security.redact` runs on anything logged.

Task 1.2 checks, before the build, that the `tqdm_class` gets byte updates for a Xet-stored file and for a plain LFS file on `huggingface_hub` 1.27. **Fallback:** poll the size of the `.incomplete` blob every second for progress, and keep cancel through the same event checked between files.

### D8. Free space and the gated check

Before the job starts, the route runs `hf_hub_download(..., dry_run=True)` for each file. The bytes still to download are the sum for files that will download. `shutil.disk_usage(cache folder)` gives the free space. A start with less than that sum plus 1 GiB is refused with `no-space`, and the message names both sizes. A gated repo with no `HF_TOKEN` in the environment of `omrs web` is refused with `gated` before any request with a token. Ollama has no size before the pull, so the Ollama job skips the space check; a full disk ends the pull with Ollama's error, mapped to `failed`.

### D9. Routes and scopes

| Operation | Route | Scope | Notes |
| --- | --- | --- | --- |
| `searchModels` | `GET /v1/model-downloads/search?provider=&q=` | session `manage` | 400 for a bad query or a provider with no source |
| `listModelFiles` | `GET /v1/model-downloads/files?provider=&repo=` | session `manage` | 404 `not-found` |
| `startModelDownload` | `POST /v1/model-downloads` | session `manage` | 202; 409 `busy`, `no-space`, `gated` |
| `getModelDownload` | `GET /v1/model-downloads/current` | session `manage` | the status shape of the spec |
| `cancelModelDownload` | `DELETE /v1/model-downloads/current` | session `manage` | 409 when no job runs |

The search uses `manage`, not `read`, because each call makes the server contact an outside host. A bearer token never gets `manage`. The start body holds `provider`, and either `repo` with `revision` and `label`, or an Ollama `name`. No request text reaches a path, an argument list or a header other than the checked values. The 409 reasons go into the contract enum, a message map in the route, and the front-end refusal words (`transports/api/AGENTS.md` rule 4).

### D10. Front end

A `ModelDownloadPanel` in `web/src/settings/`, shown by `ProviderCard` when `model_source` is set, split by responsibility:

- `useModelDownload.ts`: the queries and mutations; polls `getModelDownload` every second while the state is `running`.
- `ModelSearchField.tsx`: the search box, 400 ms debounce, at least 2 characters, the results list with downloads and a Gated badge.
- `ModelFileList.tsx`: the labels with sizes, the preselected entry and the Download button.
- `ModelDownloadProgress.tsx`: the bar, the bytes, Cancel, and the one-line reason through `describeError`.
- `modelDownloadWords.ts`: the plain-English text of each reason.

After a llama.cpp success, when omrs runs the Chat server, the panel shows Use this model, which calls the existing `useSaveLlamacppServer` with the model value, then offers the existing Restart. With an external server it shows the D4 note and Refresh models, which invalidates the llama.cpp model list query. After an Ollama success the panel refreshes the Ollama model list query. Build with the `omrs-design` skill and the primitives in `components/ui/`. Each file stays under 200 lines.

## Risks / Trade-offs

- [llama.cpp may stop reusing the Hugging Face cache in a later build] → Task 1.1 checks the build in use; the D4 fallback saves an absolute `.gguf` path, which the current rules accept.
- [`tqdm_class` may get no byte updates on the Xet path] → Task 1.2 checks it first; the D7 fallback polls the `.incomplete` file size.
- [Hugging Face changes the search response] → The adapter reads only `id`, `downloads`, `likes`, `gated`, `lastModified`; an unexpected shape gives an empty list and the reason `network`, never a crash. A contract test pins a saved response.
- [A cancelled Hugging Face download may finish the current chunk before it stops] → The spec allows 5 seconds; the cancel event is checked on every `update()` call.
- [Search results include low-quality or unsafe repos] → Sorting by downloads and showing the author keeps known publishers on top. GGUF files hold weights and metadata, not code. The download runs no file it gets.
- [Large downloads fill the disk] → The D8 space check with a 1 GiB margin; the size shows on every entry before Download.
- [The Llama app lists cached models only when it starts] → The panel says so in plain words, and Refresh models shows the new model once the app lists it. Task 1.1 records whether the app also picks up a new file while it runs.
- [A non-default `HF_HUB_CACHE` hides the file from an external server] → The panel names the folder in use (D4).
- [Ollama has no size before the pull] → The panel shows "Size known after the pull starts" and the bar starts when the first `total` arrives.

## Migration Plan

No data migration. The feature is additive: one new descriptor field with a `None` default, new routes, a new panel. Rollback is a revert of the merge commit. Downloaded files stay in the Hugging Face cache or in Ollama and keep working with a model value set by hand.

## Open Questions

- The exact built-in Ollama names can be tuned during the build without a spec change, because the spec fixes only that the list is fixed data.
