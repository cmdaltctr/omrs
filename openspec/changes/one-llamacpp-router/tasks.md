# Tasks

Rules for every group: write the test first, prove it fails on the current code, then make it pass. After each behaviour, break the code on purpose (mutation check) and confirm the test fails, then restore. Keep each file under 500 lines. Prepare the worktree with `uv sync --frozen --extra web`. Commit with `uv run --no-sync git commit`, one commit per group. Tell the operator before any step that starts a real server, downloads a model or runs a browser.

## 1. Spikes on llama.cpp b11941 (stop conditions decide the design path)

Evidence files go in `openspec/changes/one-llamacpp-router/evidence/`. Each spike runs on a scratch port and a scratch `OMRS_STATE_DIR`, never on the live app.

- [ ] 1.0 Save the collected fast-suite test IDs of the base commit (`uv run pytest -m "not slow" --collect-only -q`) to the scratchpad for the re-pin in group 11. Verify: the file holds the current `_BASE_EXECUTED` count of IDs.
- [ ] 1.1 Decision forwarding: start a b11941 router on a scratch port and `OMRS_STATE_DIR` with one preset for Clef-Flash Q8_0 plus its projector (`parallel = 1`). Send `POST /v1/systemone` with the entry's `model`, and run the projector smoke test (right text minus wrong text at least 0.2). Record request, response and timing in `evidence/spike-1.1.md`. Stop condition: if the router does not forward the request or the margin fails, take outcome B of design D10 and run `openspec-update-change` before group 5.
- [ ] 1.2 Load, unload and reload: with two presets (embedding 4B, Qwen3-4B), record `GET /v1/models` status values and the `memory` field, `POST /models/load` and `POST /models/unload` responses, and the effect of editing one section then calling `GET /models?reload=1`. Verify in `evidence/spike-1.2.md` that only the edited model unloads. Stop condition: if reload unloads an unchanged model or keeps the old preset, take the fallback of design D7 and update the change before group 4.
- [ ] 1.3 Child processes, on macOS and on Linux: with two loaded models, record the process group of each child, the result of SIGTERM to the group (all exit within 10 s?), and of SIGKILL to the router pid alone (do children exit?). Record direct-children lookup results and resident sizes. Write `evidence/spike-1.3.md`. Stop condition: if any child survives, add the per-child stop of design D9 to group 3 before it starts.
- [ ] 1.4 Linux builds: on a Linux x86-64 host (RunPod GPU pod after telling the operator about cost), unpack `ubuntu-x64` and `ubuntu-cuda-12.8-x64` plus its `cudart` archive. Check SHA-256 against the release, record the library layout (`LD_LIBRARY_PATH` or side by side), and confirm the CPU build reports no CUDA device. Write `evidence/spike-1.4.md` with the pins. Stop condition: if CUDA 12.8 fails on the pod driver, record the driver version and ask the operator to choose 13.4 or the user-path override.
- [ ] 1.5 Read `llama-server --help` of b11941 for the accepted values of every allow-listed preset key and of `spec-type`. Record them in `evidence/spike-1.5.md`. Verify: each key in design D4 has a recorded type and range.

## 2. Settings, defaults and retirement

- [ ] 2.1 Add `llamacpp_router_server`, `llamacpp_router_url`, `llamacpp_router_models_max` and `llamacpp_router_memory_margin_mib` to the provider settings and `config/rules.py` (accepted values, ranges, loopback rule for managed). Verify: new unit tests for defaults, source order and range refusal pass, and fail when one default is changed.
- [ ] 2.2 Add the `llamacpp_models` named map (entry model, rules for id, `model`, `file`, `projector`, `sha256`, `preset` allow-list types from spike 1.5), file-only, written only by `omrs web`, with the shipped list of design D11 as code default. Verify: tests for each rule in spec `llamacpp-router` ("The model list lives in omrs.jsonc", "Entry files follow fixed rules", "The preset file holds allow-listed keys only") pass and fail under mutation.
- [ ] 2.3 Derive roles from `llamacpp_embed_model`, `llamacpp_chat_model`, `answer.model`, the judge and managed decision entries; refuse `role-mismatch` and report `model-not-listed`. Verify: tests for spec "Roles are derived from the role settings".
- [ ] 2.4 Retire `llamacpp_embed_url`, `llamacpp_chat_url`, `llamacpp_classify_url`, `llamacpp_chat_server`, `llamacpp_embed_server` and `llamacpp_context_window` in `config/legacy.py` (start-up failure with replacement) and in the `omrs.jsonc` problem list (`retired`). Retire the decision entry fields `model_file`, `projector_file`, `model_sha256`, `projector_sha256` as moved to `llamacpp_models`. Check the state of change `tripwire-retirement-and-provider-symmetry` first and follow its policy names; record the overlap in the commit message. Verify: tests for spec "The per-role server settings are retired" pass.
- [ ] 2.5 Change shipped defaults: `answer.provider = llamacpp`, `answer.model = Qwen/Qwen3-4B-GGUF:Q8_0`, `llamacpp_embed_model = Qwen/Qwen3-Embedding-4B-GGUF:Q8_0`, `llamacpp_chat_model = Qwen/Qwen3-4B-GGUF:Q8_0`, `metadata.ollama_classify_model = ""`, in `config/__init__.py`, `config/defaults.yaml` and `core/answer/settings.py`. Check that `embedding.tokenizer_model` default matches Qwen3-Embedding-4B. Verify: the "No Ollama default" test of spec `llm-provider-settings` passes. Grep `docs/guides/` for `qwen3:4b`, `8081` and `16384` and list hits for group 10.
- [ ] 2.6 Point every llama.cpp client (embeddings, classification paths, Chat, judge, decision) at `llamacpp_router_url`; remove `classification_url()`. Verify: provider tests show each request goes to the router address with its model name.

## 3. Runtime manager: router mode

- [ ] 3.1 Extend `tests/fixtures/llamacpp/fake_llama_server.py` with router mode (design D16): parse `--models-preset`, `GET /v1/models` with `status.args`, load, unload, `GET /models?reload=1`, POST routing by `model`, one real child process per loaded model. Verify: fixture self-tests pass, including a child that ends on a group SIGTERM.
- [ ] 3.2 Replace `chat`, `embeddings` and `decision-*` with runtime id `router` in `spec.py` (`RUNTIME_ID_RE`, roles `router` and `ocr`). Build the fixed router argument list. Verify: tests for spec `llamacpp-runtimes` "Mode settings" and `llamacpp-server` "The argument list is fixed" pass; a test that adds `--sleep-idle-seconds` still fails the spec check.
- [ ] 3.3 Write the preset writer: one section per usable entry, `model = <file>`, `mmproj = <projector>`, allow-listed keys only, temporary file and rename, entries with no file or a failed check left out. Verify: golden-file tests and reserved-key refusal tests pass.
- [ ] 3.4 SHA-256 checks per entry with the `hashes.json` cache keyed by path, size and `mtime_ns`. Verify: tests for spec "Listed files are checked against their recorded SHA-256" (changed file isolated, decision entry without hash refused) pass.
- [ ] 3.5 Router digest of binary and argument list only; state folder layout with `models.ini`, `hashes.json` and `models/<model id>/`. Verify: adoption tests with the fake router (orphan adopted, preset edit is not a new version) pass.
- [ ] 3.6 Stop and memory: group stop reaches children; memory sums the router and its direct children whose command line holds the binary path; no other process listing. Apply the outcome of spike 1.3. Verify: tests for "No child survives" and "Memory sums children" pass, and the no-process-lookup scan test still passes.
- [ ] 3.7 Rewire `compose_runtimes.py` and `core/runtime_gate.py`: one router spec, a gate per model, OCR runtimes unchanged. Verify: import-linter contracts pass and the OCR runtime tests are unchanged and green.

## 4. Per-model locks, readiness and reload

- [ ] 4.1 Per-model `clients.lock` and `request.lock` (one-slot entries only). Verify: multi-process tests show a one-slot model serialises and a second model does not wait; the 20-second lock-order stress test ends without deadlock.
- [ ] 4.2 Readiness: status read, `POST /models/load`, poll up to `MODEL_LOAD_TIMEOUT_SECONDS = 300`, request timeout starts after `loaded`, `model-load-failed` isolated. Verify: tests for spec "A model is made ready before its request is timed" with a slow fake load.
- [ ] 4.3 Reload rule: rewrite one section under `start.lock`, call reload, per-model `version-busy` when another process holds the model's client lock, router restart only for router arguments. Apply the outcome of spike 1.2. Verify: tests for spec "A preset edit reloads only the changed model".
- [ ] 4.4 Router `/health` start wait (180 s, no model load at start) and the model state set (`not-downloaded`, `unloaded`, `loading`, `loaded`, `failed`) with fixed reasons. Verify: lifecycle tests for spec `llamacpp-server` "Lifecycle states and fixed reasons" pass.

## 5. Decision models on the router

- [ ] 5.1 Managed decision entries name a list entry; remove the `decision-<name>` runtime path in `compose_decision.py`; build floor b11941 checked when any decision entry is listed; quantisation check on the list entry's file. Follow outcome A or B of spike 1.1. Verify: tests for spec "Decision models run on the router" and `llamacpp-runtimes` "A managed decision runtime checks its build".
- [ ] 5.2 Projector smoke test and decision test run against the router address with the model name. Verify: decision provider tests with the fake router pass; `GET /v1/runtimes` lists the decision model under the router item.

## 6. Pinned binary provisioning

- [ ] 6.1 Add `integrations/llamacpp_runtime/pins.py` with the b11941 archives and SHA-256 from spike 1.4 (macOS arm64, Linux CPU, Linux CUDA 12.8 plus `cudart`). Verify: a test checks the tag equals the dots-mocr `LLAMA_TAG` and every pin is 64 hex characters.
- [ ] 6.2 Provisioning job (download, SHA-256 check, unpack into the OMRS data folder, no server start) and CLI `omrs llamacpp install [--flavour cpu|cuda]`. Blank `llamacpp_server_binary` resolves to the provisioned binary; a user path below b11941 gives `wrong-build`. Verify: tests with a local archive server for hash mismatch, unpinned platform and headless CLI; CLI output goes to stderr.
- [ ] 6.2a Automatic model download: when the managed router starts or an entry is first needed and its file is missing, start the Get a model download job (pinned revision, progress, cancel), record path and SHA-256, write the entry to `models.ini` by file path, then load it. A download in progress does not count against the start or load waits. `omrs llamacpp install` also downloads missing listed models. Verify: tests first (missing file triggers the job; slow download is not `timeout`; entry shows "Downloading"; CLI downloads after the binary), one mutation check (skip the job: the test fails).
- [ ] 6.3 Document the provisioning in `docs/guides/configuration.md` (Local llama.cpp router) and the CLI reference. Verify: the documented command runs as written against the test archive server.

## 7. Routes and web: Router panel, Model runtimes, Get a model

- [ ] 7.1 Add the router routes (`GET` and `PUT /v1/llamacpp/router`, `PUT` and `DELETE /v1/llamacpp/router/models/{id}`, start, stop, restart, install `POST` and `GET`) with the scopes of spec `llamacpp-server`; remove `/v1/llamacpp/server*`; update `GET /v1/runtimes` items with `models`. Update `openapi.yaml` and the route table. Verify: OpenAPI conformance tests and scope tests (bearer refused, `credentials` for files and mode, `manage` for preset values) pass.
- [ ] 7.2 Model downloads: status gives cache path and SHA-256; Use this model adds or replaces an entry and changes no role setting. Verify: tests for spec `model-downloads` pass.
- [ ] 7.3 Web: load the `omrs-design` skill. Replace `LlamacppChatBlock`, `LlamacppServerPanel`, `ChatServerChoice`, `LlamacppServerFields` and `LlamacppSharedWarning` with one Router panel and model table; update `providerExtras.ts`, `LlamacppUseModel` (add or replace target), `ModelRuntimesSection` and `ModelRuntimeRow` (roles `router` and `ocr`, model lines). Remove components left unused. Verify: Vitest tests for each spec scenario of `workspace-settings` and `workspace-integrations` pass, and the frontend gates pass.
- [ ] 7.4 Integrations llama.cpp card with Get llama.cpp. Verify: Vitest tests for spec "The Integrations page provisions the pinned llama.cpp build".
- [ ] 7.5 Browser check at 1,280 px and 390 px with a scratch config, fixed free port and the fake router, after telling the operator. Save screenshots and notes to `browser-check.md`. Verify: no sideways scroll; Start, Stop, Restart and Edit reachable.

## 8. Ollama out of defaults, tests, CI and first-choice docs

- [ ] 8.1 `tests/conftest.py`: set the llama.cpp shipped defaults, redirect the embedding mock to the llama.cpp builder, move Ollama-specific setup into an opt-in fixture, remove the stale extras comment. Verify: the fast suite passes with no Ollama on the machine (`OLLAMA_BASE_URL` pointed at a closed port).
- [ ] 8.2 `.github/workflows/ci.yml`: drop the Ollama environment blocks; gate the slow suite on a llama.cpp router answering at `127.0.0.1:8080` with the default embedding model listed, else print the skip line; switch the Tier 2 job to the pinned b11941 CPU build with `Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0`, re-measure its thresholds once and record them in the job comment. Run `actionlint`. Verify: `actionlint` passes and a manual Tier 2 run is green.
- [ ] 8.3 `scripts/local_ci.sh`: same environment as CI, no Ollama values. Verify: the script runs the same steps as CI.
- [ ] 8.4 Docs first choice: README, `getting-started.md`, `providers.md`, `configuration.md`, `web-workspace.md`: llama.cpp router first, Ollama as an opt-in section. Verify: the guard test of the tripwire change (or a grep) finds no instruction to install Ollama as a first step.

## 9. Single source of settings

- [ ] 9.1 `.env.example`: remove every provider, model and URL key; keep secret notes and commented developer overrides; point to `omrs config init` and `omrs.jsonc`. Verify: a test checks `.env.example` assigns no key from the provider, model or URL set.
- [ ] 9.2 Add `test_conftest_matches_shipped_defaults`: every provider, model and URL value that conftest, `ci.yml` and `local_ci.sh` set equals the shipped default. Verify: it passes, and fails when one conftest value is changed (mutation check).
- [ ] 9.3 Show the operator a diff for the gitignored repo `.env` (remove provider, model and URL keys; keep secrets). Do not edit it without approval. Verify: the operator confirms.

## 10. Docs and ADR

- [ ] 10.1 Write ADR-115 "One llama.cpp router serves every local model" (Proposed): supersede ADR-109's router-mode rejection and its per-role table, amend ADR-084, ADR-108 and ADR-110, relate ADR-103, ADR-106 and ADR-113. Add header notes to the amended ADRs and a row in `ADR_README.md`. Check the next free number again against sibling worktrees before writing. Verify: the ADR README lists it and every link resolves.
- [ ] 10.2 Update `docs/guides/architecture.md` (Local model runtimes), `configuration.md` (router keys, model list, retired keys table, upgrade notes with the one-time re-index), `mcp-tools.md` if a tool text names an address, the folder `AGENTS.md` files that name `llamacpp_chat_server` or `llamacpp_embed_server`, and root `AGENTS.md` Gotcha 17 runtime list. Fix every hit from task 2.5. Verify: a grep for the retired key names in `docs/` and `AGENTS.md` files finds only upgrade notes.
- [ ] 10.3 Amend change `pipeline-sweep-llamacpp` with the `openspec-update-change` skill (design D17): run on the OMRS router with a scratch `OMRS_CONFIG_DIR` and `OMRS_STATE_DIR`, not `llama serve` (the program rule refuses it); drop the non-goal that keeps live, CI and defaults on Ollama; map its D6a presets onto the allow-list, with `spec-type` per spike 1.5 and the thinking setting per request. Verify: `openspec validate pipeline-sweep-llamacpp --strict` passes and the PR description names the amendment.

## 11. Tripwire, local CI and validation

- [ ] 11.1 Re-pin `tests/test_clean_base_tripwire.py` by diffing collected test IDs against task 1.0, not per-file counts; update `_BASE_EXECUTED`, `_BASE_DESELECTED` and `_WEB_EXTRA_CASES` with a dated comment under 100 characters. Verify: the tripwire passes on the fast-suite JUnit report.
- [ ] 11.2 Run `./scripts/local_ci.sh` and read its final line and every `SKIPPED` line. Verify: exit 0.
- [ ] 11.3 Run `openspec validate one-llamacpp-router --strict` and `openspec validate --all --strict`. Verify: both pass.

## 12. Pull request

- [ ] 12.1 Ask the operator before pushing. Push `feat/one-llamacpp-router` and open one PR into `v3`, with the job times, the spike evidence and the sweep note. Verify: the PR exists and names the tested commit.
- [ ] 12.2 Watch CI until every check ends; fix each failure and push again. Verify: every check is green.
- [ ] 12.3 Read the CodeRabbit comments, check each against the code, fix valid ones with a commit reply, answer invalid ones with a reason, and resolve every thread. Verify: no open thread.
- [ ] 12.4 Do not merge. Wait for the operator's go. Verify: the operator merges or says go.

## 13. Live rollout (operator steps, after merge and after `local-ocr-per-backend-cuts` merges)

- [ ] 13.1 Provision the router on the live Mac (`omrs llamacpp install`) and download the models: Qwen3-Embedding-4B Q8_0, Qwen3-4B Q8_0, Clef-Flash Q8_0 with its projector (projector placed by hand, since downloads leave projectors out). Verify: each file's SHA-256 is recorded in `omrs.jsonc`.
- [ ] 13.2 Set the live list: embedding 4B (`ctx-size` 8192, `pooling` last, batch and ubatch 8192), Qwen3-4B (`ctx-size` 32768), Clef-Flash with projector and `parallel` 1. Switch live `omrs.jsonc` to `llamacpp_router_server` `managed` and one `llamacpp_router_url`. Remove stale keys (`embed_model` `qwen3-embedding:0.6b`, `metadata.ollama_classify_model`, the retired URL and server keys). Back up the file first. Verify: `omrs config show` lists no problem.
- [ ] 13.3 Stop relying on the Llama app for OMRS (quit it or leave it on its own port). Verify: `GET /v1/runtimes` shows the router running with the three models and the dots.mocr runtime apart.
- [ ] 13.4 Re-ingest every collection once, together with the re-index of `local-ocr-per-backend-cuts`. Verify: each collection's identity stamp shows `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0`, categories are filled, and a known-answer search per collection finds its source.
- [ ] 13.5 Copy gitignored evidence out before the worktree is removed (root `AGENTS.md` Gotcha 15). Verify: copy receipt recorded.

## Workflow follow-up

- Archive the change after the operator accepts the live rollout and the ADR moves to Accepted.
- At archive, update the Purpose line of `openspec/specs/llamacpp-server/spec.md` (it still says Chat) and fix stale scenario names that the MODIFIED blocks had to keep (Gotcha 12: fix the baseline).
