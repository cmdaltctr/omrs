# Tasks

Each code task starts with a failing test. Confirm that the test fails on the current code, then make it pass. For each guardrail test, break the guard on purpose once and confirm that the test fails (mutation check). Commit each group with a Conventional Commit through `uv run --no-sync git commit`.

## 1. Checks before the build and the decision record

- [x] 1.1 Confirm that the installed `llama-server` reuses the Hugging Face cache (design D4). Download a small GGUF with `hf_hub_download` into a scratch `HF_HUB_CACHE`. Start `llama-server -hf <id>` with that cache and the network blocked. Record the build number and the result in design.md D4. If the server does not reuse the cache, record that the D4 fallback (absolute `.gguf` path) applies.
- [x] 1.1b Confirm that the Llama desktop app lists a model that `hf_hub_download` put in `~/.cache/huggingface/hub`. Record the app version, and whether the app needs a relaunch or picks the file up while it runs, in design.md D4. Warn the user before a relaunch, because the live app uses this server. Result so far (2026-10-29): the running app did not list the new file (design D4). The user deferred the relaunch check to 8.4.
- [x] 1.2 Confirm that a `tqdm_class` gets byte updates from `hf_hub_download` on `huggingface_hub` 1.27, for one Xet-stored file and for one plain LFS file (design D7). Confirm that an exception raised from `update()` stops the download and keeps the `.incomplete` file. Record the result in design.md D7; if updates do not arrive, record that the size-polling fallback applies.
- [x] 1.3 Confirm that closing the `POST /api/pull` stream stops an Ollama pull and that a second pull of the same name resumes. Record the Ollama version and the result in design.md D6.
- [x] 1.4 Write `docs/adr/106-app-searches-and-downloads-local-models.md` with the status Proposed. Record D1 (descriptor field, two-entry table, registry at a third source), D3 (REST reads without a token, library download), D4 (shared cache and fallback), D6 (no ollama.com scraping), D7 (one job), D9 (`manage` scope) and the results of 1.1 to 1.3. Add its row to `docs/adr/ADR_README.md`. Link ADR-084 and ADR-103.

## 2. Pure rules and the descriptor field

- [x] 2.1 Add tests for `core/providers/model_sources.py`: the repo-id rule, the label rule and the Ollama name rule accept the valid forms and refuse `../x`, `org/`, `a b`, `--help`, `;` and a leading `-` (spec "Names follow fixed rules"). Confirm that they fail, then write the module.
- [x] 2.2 Add tests for the label parser and the split grouping: `Qwen3-4B-Q4_K_M.gguf` gives `Q4_K_M`, `UD-Q4_K_XL` keeps its prefix, two `-0000N-of-00002` parts form one `Q8_0` entry with the sum of sizes, `mmproj` files and files with no known label are left out (design D5). Then implement them.
- [x] 2.3 Add the fixed built-in Ollama names and a test that the Ollama search filter returns the names that contain the query, in list order (design D6).
- [x] 2.4 Add `model_source` to `ConnectionDescriptor` with the default `None`. Set it on the llama.cpp and Ollama descriptors. Add a test that every other descriptor has `None` (spec "A provider declares its model source").
- [x] 2.5 Add `HF_HUB_CACHE` to `HUGGING_FACE_ENVIRONMENT` in `llamacpp_rules.py`. Extend the child-environment test: the child gets it for an `-hf` model and not for a `.gguf` file.
- [x] 2.6 Update `docs/guides/providers.md` "Registry pattern" and "Adding a new provider": describe the `model_source` field and the two source kinds. Verify that `uv run pytest tests/unit -k "model_sources or descriptor or llamacpp_rules" -q` passes.

## 3. Hugging Face adapter

- [x] 3.1 Add tests with an `httpx.MockTransport` for `integrations/huggingface_models.py` search: the exact query URL (`filter=gguf`, `sort=downloads`, `direction=-1`, `limit=20`), no `Authorization` header, a 10-second timeout, the body limit, and an empty list with `network` for a timeout or an unexpected shape. Then implement it.
- [x] 3.2 Add tests for the file list: the revision comes from `expand[]=sha`, the tree read is recursive at that revision, sizes come from the tree, gated comes from the model read, and 404 gives `not-found`. Use a saved response from `unsloth/Qwen3-4B-GGUF` as the fixture. Then implement it.
- [x] 3.3 Add tests for the download with `hf_hub_download` patched at the adapter module: one call per file at the pinned revision, byte updates reach the progress callback, the cancel event stops the call, 401 or 403 maps to `gated`. Then implement it, with `huggingface_hub` imported inside the function.
- [x] 3.4 Add tests for the size check with `dry_run=True` patched: cached files count as 0 bytes, and the check refuses when free space is below the size plus 1 GiB (spec "Free space is checked first"). Then implement it.
- [x] 3.5 Add the `omrs.integrations.huggingface_models` row to the integration inventory in `docs/guides/architecture.md` and raise its count. Verify that `uv run pytest tests/test_strategy_registration_inventory.py -q` and `uv run lint-imports` pass.

## 4. Ollama adapter

- [x] 4.1 Add tests with an `httpx.MockTransport` for `integrations/ollama_pull.py`: one `POST {base}/api/pull` with `stream: true`, progress summed over layer digests, `success` ends the pull, an `error` line gives `failed`, a refused connection gives `ollama-unreachable`, and a set cancel event closes the stream (design D6). Then implement it.
- [x] 4.2 Add the `omrs.integrations.ollama_pull` row to the integration inventory and raise its count. Verify that the inventory test and `uv run lint-imports` pass.

## 5. The download job

- [x] 5.1 Add tests for `transports/api/model_download_job.py`: a second start gives `busy`, status snapshots show growing bytes, cancel ends in `cancelled` within 5 seconds, 60 seconds without a byte gives `stalled` (use a fake clock), and the state is `idle` on a new runtime (design D7). Then implement the job with its adapter table keyed by `ModelSourceKind`.
- [x] 5.2 Add the job to `WebRuntime` and cancel it in `shutdown_runtime()`. Add a test that shutdown stops a running fake download.
- [x] 5.3 Add a test that no status, log line or error holds an `HF_TOKEN` value or exception text, with `HF_TOKEN=hf_test_secret` set. Run log text through `security.redact`.
- [x] 5.4 Update `src/omrs/transports/api/AGENTS.md`: add the model download job rules (one job, no subprocess, fixed reasons, `manage` scope). Verify that the job tests pass.

## 6. HTTP contract and routes

- [x] 6.1 Add the five operations of design D9 to `openapi.yaml`, with `additionalProperties: false`, the 409 `reason` enum and `model_source` on the provider entry of `getConnections`. Add the operation ids to `FAMILIES` in `tests/unit/test_web_openapi_conformance_support.py`. Confirm that the conformance tests fail.
- [x] 6.2 Write `transports/api/routes/model_downloads.py` and register it. The routes validate with `model_sources`, read the Ollama address from the provider values in use, and give each 409 a plain-English line in a reason map. Return `model_source` from `GET /v1/connections`. Verify that the conformance tests pass.
- [x] 6.3 Add route tests: a bearer token is refused on all five routes, a session without `manage` is refused, a provider with no source gives 400, a bad query or name gives 400 and sends no outside request, `no-space` and `gated` give 409, and a successful start gives 202 (spec "Scopes for search and download").
- [x] 6.4 Add a test that `omrs web` start-up and `GET /v1/connections` send no request to `huggingface.co` (spec "The server contacts the model host only on request").
- [x] 6.5 Update `src/omrs/transports/api/README.md` with the route group. Update `docs/guides/configuration.md`: `HF_TOKEN` for gated repos, `HF_HUB_CACHE` and `HF_HOME` for the download folder, and the 1 GiB space margin. Verify that `uv run pytest tests/unit -k "openapi or model_download or connections" -q` passes.

## 7. Front end

- [x] 7.1 Load the `omrs-design` skill. Read `web/DESIGN.md` and `web/src/AGENTS.md`.
- [x] 7.2 Add `web/src/api/modelDownloads.ts` with types that match `openapi.yaml`, and the query keys. Add `useModelDownload.ts` that polls the status every second only while the state is `running`. Add a Vitest test for the polling stop.
- [x] 7.3 Add `ModelSearchField.tsx`, `ModelFileList.tsx`, `ModelDownloadProgress.tsx`, `ModelDownloadPanel.tsx` and `modelDownloadWords.ts` (design D10). Add tests: the 400 ms debounce and the 2-character minimum, the Gated badge, the sizes, the `Q4_K_M` preselection, the progress bar, Cancel, and one plain line for each reason.
- [x] 7.4 Show the panel in `ProviderCard.tsx` only when `model_source` is set. Add a test that the OpenRouter card shows no panel.
- [x] 7.5 Add Use this model for llama.cpp through `useSaveLlamacppServer`, then the existing Restart, shown only when the managed server is `running` or `starting`. Add tests: the save sends the model value, and a session without `credentials` shows the existing refusal and keeps the old model. With the managed server `stopped`, add tests that the panel shows the cache folder and Refresh models and no Use this model, and that Refresh models refetches the llama.cpp model list (spec "An external llama.cpp server is told, not controlled"). For Ollama, refresh the model list query after success, with a test.
- [x] 7.6 Update `docs/guides/web-workspace.md` "Local llama.cpp server" and the Ollama text with a "Get a model" section: steps, what each reason means, and where the files go. Verify that `npm run lint`, `npm run typecheck` and `npm test` pass in `web/`.
- [x] 7.7 Check the panel in a browser at 1280 px and 390 px against a fake download server, following the Orca preview steps. Save the screenshots in the change folder.

## 8. Integration checks

- [x] 8.1 Count the new fast tests with `uv run pytest --collect-only -q`, compare the test IDs with the last pin, and update `tests/test_clean_base_tripwire.py`, including `_BASE_EXECUTED` and `_WEB_EXTRA_CASES` for tests that need fastapi.
- [x] 8.2 Run `./scripts/local_ci.sh`. Confirm that no step prints `SKIPPED` and that every step passes.
- [x] 8.3 Run `openspec validate add-model-search-and-download --strict` and `openspec validate --all --strict`. Confirm both pass.
- [x] 8.4 Run the live checks after a warning to the user, on a scratch server and port (Orca preview steps):
  - External server (the user's setup): download `Qwen/Qwen3-1.7B-GGUF:Q8_0`, which is not in the cache yet. Let the Llama app list it (relaunch only with approval), press Refresh models, and confirm that the model is in the llama.cpp list.
  - Managed server: on a scratch port, press Use this model and Restart with that model, and confirm `running` without a new download. The machine has no program named `llama-server` (task 1.1); ask the user before installing one, for example with `brew install llama.cpp`.
  - Relaunch check of 1.1b: after the relaunch, confirm that the Llama app lists `unsloth/SmolLM2-135M-Instruct-GGUF:Q2_K`, then tick 1.1b and remove that test model from `~/.cache/huggingface/hub`.
  - Ollama: pull `smollm2:135m`, which is not installed (`qwen3:0.6b` already is), and confirm that it is in the model list. Remove it after the check.
  - Record the results in the change folder.
- [x] 8.5 Ask the user to review ADR-106. After approval, set its status to Accepted and update `docs/adr/ADR_README.md`.

## Workflow follow-up

- Before the build, create a sibling worktree `omrs-v3-feat-add-model-search-and-download` on a new branch `feat/add-model-search-and-download` from `v3`. Open a pull request against `v3`. Watch CI and resolve the review findings.
- After the merge, copy any gitignored artefacts the project keeps (Critical Gotcha 15), then remove the worktree and the branch.
- Run `/opsx:verify`, then `/opsx:archive`.
