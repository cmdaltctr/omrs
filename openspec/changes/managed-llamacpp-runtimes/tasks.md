# Tasks

Each group writes its tests first. Each test must fail on the code before the group's change, then pass after it (Karpathy rule 5). Work only in the worktree `omrs-feat-managed-llamacpp-runtimes`. Never use `~/.omrs`, its `omrs.jsonc`, any `.env`, or the Llama app on port 9931.

## 1. Test fixtures

- [x] 1.1 Copy the fake `llama-server` from the `feat/dots-mocr-llamacpp-backend` branch (`git show feat/dots-mocr-llamacpp-backend:tests/fixtures/ocr_worker/fake_llama_server.py`) to `tests/fixtures/llamacpp/fake_llama_server.py`. Add only what this change needs:
  - `GET /props` that reports `FAKE_LLAMA_BUILD`;
  - `POST /v1/embeddings` with a fixed vector;
  - `FAKE_LLAMA_REQUEST_DELAY` (seconds per request) and `FAKE_LLAMA_HEALTH_DELAY` per request (slow `/health` after start);
  - `FAKE_LLAMA_BIND_FAILS` (a count; each failed start prints llama-server's bind error line and exits 1);
  - `FAKE_LLAMA_EXIT_AFTER` (exit after N requests, to act as a crash).
  - Verify: a fixture self-test starts the fake, reads `/health`, `/props`, `--version`, and sees each variable change the behaviour.
- [x] 1.2 Add `tests/fixtures/llamacpp/client.py`: a small process that joins one runtime through the manager, sends requests on command lines from standard input, and prints one JSON line per result. Tests use it as a second, third or fifth OMRS client.
  - Verify: a self-test starts two client processes against one fake server and reads both answers.
- [x] 1.3 Add an autouse fixture in `tests/conftest.py` that sets `OMRS_STATE_DIR` to a tmp folder, beside the `OMRS_CONFIG_DIR` fixture.
  - Verify: a test asserts that the resolved state root is under `tmp_path` and never under the home folder.

## 2. Package skeleton and moved launch rules (design D1, D2, D3)

- [x] 2.1 Create `src/omrs/integrations/llamacpp_runtime/` with `rules.py`, `spec.py`, `state.py` and `locks.py`. Move the launch checks (program rule, model kind, loopback port, argument lists, child environment, reasons) from `src/omrs/core/providers/llm/llamacpp_rules.py` into `rules.py`. Keep `LLAMACPP_SERVER_FIELDS` in `core/`. Update every importer (`compose_llamacpp.py`, `transports/api/llamacpp_chat_rule.py`, `transports/api/llamacpp_server.py`, `transports/api/settings_handover.py`, `transports/api/routes/llamacpp_server.py`).
  - Verify: the existing llama.cpp rule tests pass against the new module path; `uv run lint-imports` passes; `grep -rn "llamacpp_rules import" src/omrs/transports` names only field-list uses.
- [x] 2.2 Write `spec.py` (`RuntimeSpec`: id, role, mode, binary, argument list, declared files with SHA-256, build, port policy, slot count) and the argument builders for Chat (no `--sleep-idle-seconds`) and embeddings (`--embedding`).
  - Verify tests first: the Chat list equals `[binary, "-m", "/m/q.gguf", "--host", "127.0.0.1", "--port", "8081", "-c", "16384"]`; the embeddings list equals the spec scenario; no list holds `--sleep-idle-seconds`.
- [x] 2.3 Write `state.py`: state root (`OMRS_STATE_DIR`, `$XDG_STATE_HOME/omrs`, `~/.local/state/omrs`), runtime folder, atomic `server.json` write (`.tmp` then rename) and a tolerant read (a broken file reads as no record).
  - Verify tests first: each root source in order; a broken `server.json` reads as no record; a write never leaves a partial file.
- [x] 2.4 Write `locks.py`: shared and exclusive `flock`, blocking and non-blocking, each on its own descriptor; `not-supported` on Windows.
  - Verify tests first: a shared lock in a child process makes a non-blocking exclusive attempt fail; the lock frees when the child is killed with SIGKILL.
- [x] 2.5 Add the integration inventory row for `llamacpp_runtime` in `docs/guides/architecture.md`.
  - Verify: `tests/test_strategy_registration_inventory.py` passes, and fails before the row exists.

## 3. Lease lifecycle across processes (design D4)

Write all tests in this group first, against the fake server and the client process from group 1. Then write `manager.py` and `process.py` until they pass.

- [x] 3.1 Two clients share one server: two client processes join one runtime; the fake's start log shows exactly one start.
- [x] 3.2 First leaves, server lives: the first client exits normally; the second client's next request succeeds with no new start.
- [x] 3.3 Last leaves, server stops: the only client exits normally; the server process group is gone and `server.json` records `stopped_by` `last-client`.
- [x] 3.4 SIGKILL one of two clients: the server keeps running and the other client's next request succeeds.
- [x] 3.5 SIGKILL the only client, then a new client joins: the new client adopts the orphan; the start log still shows one start.
- [x] 3.6 A slow `/health` (5 s) and a request in progress (3 s in the fast suite; 60 s in a test marked `slow`) never make the server stale: a second client joins and adopts it; no signal goes to it.
- [x] 3.7 A recorded pid that now runs another command (a `sleep` process written into `server.json`) is never signalled; the manager starts a new server and the `sleep` process still runs.
- [x] 3.8 Five clients start at once against a stopped runtime: exactly one server starts and all five get an answer.
- [x] 3.9 SIGINT to a CLI process group: a client in its own process group starts the server, a second client stands in for the web app, SIGINT goes to the first group; the server keeps running and the second client's request succeeds.
- [x] 3.10 The lock descriptor is not inherited: after the starter exits with no other client and the server still runs (stopped from leaving by a test hook), a non-blocking exclusive lock on `clients.lock` succeeds.
- [x] 3.11 A changed pinned binary path while the old server has clients: the new client gets `version-busy`, the old server keeps running and is not signalled. With no other client, the old server stops and the new one starts.
- [x] 3.12 Lock order: a test runs leave and join in many threads and processes for 20 s with no deadlock (each finishes within its timeout).
  - Verify for 3.1 to 3.12: `uv run pytest tests/test_llamacpp_runtime_lease.py -q` passes, and each test fails when its rule is removed from the code (check by hand once per rule and record the result in the pull request).

## 4. Start, retries, idle stop, request lock, operator stop and exit (design D5 to D9)

- [x] 4.1 Start checks and detach. Tests first:
  - wrong build refused: the fake reports 11960 for a declared 11941; state `failed`, reason `wrong-build`, no start;
  - changed model file refused: one byte changed in a declared file; reason `file-changed` and the reason line names the file name; no start;
  - health timeout stops the process and gives `timeout`;
  - the child has no pipe to the starter and its output goes to `server.log`.
- [x] 4.2 Bind retries. Test first: with `FAKE_LLAMA_BIND_FAILS=10`, the manager tries 4 ports in total and reports `bind-failed`; with `FAKE_LLAMA_BIND_FAILS=2`, the third try runs. An early exit without the bind line gives `exited` with no retry. Chat and embeddings (fixed port) get no retry.
- [x] 4.3 Crash restart. Test first: with `FAKE_LLAMA_EXIT_AFTER=1`, the second request starts exactly one new server under `start.lock` and succeeds; a second crash in the same request ends it with `exited`.
- [x] 4.4 Idle stop. Test first: with `IDLE_STOP_SECONDS` patched to 2 s, the only client leaves after 2 s idle and the server stops with `stopped_by` `idle`; with a second client active, the server keeps running; the next request after an idle stop starts it again. A test asserts that the shipped constant is 600 and that no setting changes it.
- [x] 4.5 Request lock (design D6). Test first: on a `-np 1` runtime with a fake request delay of 3 s and a client timeout of 4 s, two client processes each send one request at the same time; both succeed, and the second request's timer starts after the first ends. Without the lock (test hook), the second times out.
- [x] 4.6 Operator stop. Test first: stop while a client process uses the runtime; the server stops, `stopped_by` is `operator`, the client's request in progress fails, and its next request does not start the server; a new client process starts it again.
- [x] 4.7 Exit paths. Test first: SIGTERM to the only client (CLI entry point) stops the server before the client exits; `omrs web` start-up sweep stops an owned server with no client and leaves a server that a client holds.
- [x] 4.8 Log cap: after a request, a `server.log` over 5 MiB is emptied in place and the fake's next line still lands in it.
  - Verify for group 4: `uv run pytest tests/test_llamacpp_runtime_*.py -q` passes; each file stays under 500 lines.

## 5. Chat and embeddings on the manager (design D1, D2, D12)

- [x] 5.1 Rework `transports/api/llamacpp_server.py` into a thin adapter: the routes call `RuntimeManager` through `run_in_threadpool`; the lifespan hook leaves the `chat` lease. Keep the route bodies and the 409 reasons.
  - Verify: the existing `/v1/llamacpp/server` route tests pass with only the idle sleep cases changed; a new test shows a CLI client and the web app sharing one Chat server, and the server living on after `omrs web` exits while the CLI uses it.
- [x] 5.2 Inject a lease into the llama.cpp Chat and classification clients (classification only when `llamacpp_classify_url` is blank) from `compose.py`. `core/` must not import `integrations.llamacpp_runtime`.
  - Verify: a CLI-path test with `llamacpp_chat_server=managed` starts the fake as a client and gets an answer; `lint-imports` passes.
- [x] 5.3 Add `llamacpp_embed_server` (env `LLAMACPP_EMBED_SERVER`, default `external`) to `config/provider_sources.py` and `config/rules.py`. Read it from env, `.env` and `omrs.jsonc`; refuse it in the Settings page write path. Inject the embeddings lease.
  - Verify tests first: default `external` starts nothing; `managed` starts the fake with `--embedding` and embeds text; `PUT /v1/settings/configuration` with the key is refused.
- [x] 5.4 Retire `llamacpp_idle_sleep_seconds` (design D12): remove it from `provider_sources.py`, `user_config.py`, `compose_llamacpp.py`, the card fields and the status `saved` block; add the env and `.env` start-up failure and the `omrs.jsonc` problem-list entry in `config/legacy.py`; `PUT /v1/llamacpp/server` with `idle_sleep` returns 400.
  - Verify tests first: `.env` with `LLAMACPP_IDLE_SLEEP_SECONDS` fails start-up with the message; the `omrs.jsonc` key is listed; the 400 message names the 10-minute idle stop.

## 6. OCR host seam (design D10)

- [x] 6.1 Add `declared_runtime(folder, cache_dir)` to `src/omrs/integrations/ocr_worker/manifest.py`, standard library only. Apply the path, program and flag rules.
  - Verify tests first: a valid block reads; `..`, an absolute path, a link outside the cache, a program with another name and each reserved flag are refused with a reason that names the rule; `manifest.py` imports only standard-library modules (an AST test); `ocr-workers/provision.py` still loads the file by path.
- [x] 6.2 Carry the declared runtime on `RouteCommand` in `routes.py`; build the `RuntimeSpec` (id `ocr-<engine folder>`) in the pool; give `ManagedOcrClient` the lease. Join and take the request lock before a parse; start the worker with `OMRS_OCR_RUNTIME_URL`; restart the worker when the URL changes; close the worker before an idle leave.
  - Verify tests first, with a test engine folder that declares the fake: the worker environment holds `OMRS_OCR_RUNTIME_URL`; the probe starts no server; a restart on a new port restarts the worker; no host module names an engine (grep test).
- [x] 6.3 Fallback rules. Tests first:
  - a runtime that fails before dispatch (`file-changed`) makes the primary route unavailable and the fallback parses the PDF;
  - an operator stop during a primary parse sends that request once to the fallback (operator decision, 2026-11-01), and later requests of that lease go to the fallback without a start;
  - one retry only, no loop: when the fallback also fails or is also stopped by the operator, the file gets a structured error, the fake fallback records exactly one request for that file, and the host sends nothing to the primary route again for it;
  - a worker crash after dispatch still gives a structured error with no fallback retry;
  - a worker killed with SIGKILL leaves the runtime running while the host holds its lease.
- [x] 6.4 External OCR (`ocr_runtime_url`). First, start the real `llama-server` b11941 binary from the dots engine cache in this worktree's scratch folder (operator approval needed if it is not on disk) and record whether `GET /props` reports the build, and in which field. Then write the build check against that field.
  - Evidence (2026-11-01): official `llama-b11941-bin-macos-arm64.tar.gz` (SHA-256 `fb5c491b35c75731019caa85d704fb839532c15dbb9bd3f6b3f75a667e7ac49a`, same as the dots-mocr task 1.2 record). `llama-server --version` printed `version: 0.7.0-dev (build 11941, commit 19ff817fb)`. The binary starts without a model (router mode) on a loopback port. `GET /props` returned `{"role":"router","model_path":"none",...,"build_info":"b11941-19ff817fb",...}`. The build is in `build_info`, format `b<build>-<commit>`. `PROPS_BUILD_FIELD` and the parser (`^b?(\d+)`) already match, so no code changed. Server stopped, no process left.
  - External OCR stays, opt-in only (operator decision, 2026-11-01). A blank `ocr_runtime_url` means managed.
  - Verify tests first: a matching build passes the URL to the worker and starts nothing; the build check still runs when the URL is set; another build gives `wrong-build` and the fallback serves the file; the runtime item reports `mode` `external` and `files_checked` false; a blank URL gives a managed runtime.
- [x] 6.5 Engine without a block. Test: a PaddleOCR-VL-shaped test engine starts no server and gets no `OMRS_OCR_RUNTIME_URL`.

## 7. HTTP routes and contract (design D8, D11)

- [x] 7.1 Change `src/omrs/transports/api/openapi.yaml` first: `GET /v1/runtimes` (`listRuntimes`), `POST /v1/runtimes/{runtime_id}/stop` (`stopRuntime`), the item schema with `additionalProperties: false`, the 409 reason `external-runtime`, the new reasons, and the removed `idle_sleep`. Add both operation ids to a family in `FAMILIES`.
  - Verify: the OpenAPI conformance tests fail before the routes exist.
- [x] 7.2 Write `src/omrs/transports/api/routes/runtimes.py`: `read` for the list; `require_session("manage")` for stop, bearer refused; 404 for an unknown or malformed id; 409 `external-runtime`. The list reads `server.json`, the recorded pid's `rss` and a non-blocking lock attempt only.
  - Verify tests first: list shape; reading starts nothing and changes no runtime file; bearer stop refused with no signal; external stop gives 409; the conformance tests pass.
- [x] 7.3 Update `docs/guides/web-workspace.md` route table for both new routes and the changed `/v1/llamacpp/server` body.
  - Verify: `grep -n "idle_sleep" docs/guides/web-workspace.md` finds nothing.

## 8. Web page (design D11)

- [x] 8.1 Load the `omrs-design` skill and read `web/DESIGN.md`, `web/AGENTS.md` and `web/src/AGENTS.md` before any web edit. Run `npm ci` in `web/`.
  - Verify: the skill is loaded in the session log; `node_modules/` exists.
- [x] 8.2 Write Vitest tests first for a "Model runtimes" section in `web/src/integrations/`: rows for each role and mode, the badge, one reason line, memory, used by, "External server. Model files are not checked." on an external OCR row (plus the mode External and no Stop button), "Running, no OMRS process uses it", Stop only for a managed running runtime with `manage`, confirmation when `clients` is `some`. Then write the section, its API hook and the section chip.
  - Verify: `npm test` passes; each new test fails before the component exists.
- [x] 8.3 Remove the idle sleep field from the llama.cpp card (`web/src/settings/LlamacppServerPanel.tsx` and its tests and fixtures). Match the existing style by hand. Do not run Prettier.
  - Verify: `npm run lint`, `npm run typecheck`, `npm test` and `npm run build` pass.
- [x] 8.4 Browser check at 1,280 px and 390 px. Warn the operator before the server starts. Use a scratch `OMRS_CONFIG_DIR`, `OMRS_STATE_DIR` and `--workspace`, a free port checked with `lsof -iTCP:<port> -sTCP:LISTEN`, and the fake `llama-server` as the managed Chat program. Use `chrome-devtools`; if Chrome is missing, use `orca-cli`.
  - Verify: screenshots at both widths show the section with a running and a stopped row; Stop works; no sideways scroll at 390 px; the scratch server is stopped after the check.

## 9. Documentation, ADR and agent guides

- [x] 9.1 Write ADR-109 "OMRS owns local model runtimes; components are clients" in `docs/adr/` (check first that 109 is still free on every branch; else use the next free number). Cite the research in design.md: Ollama, LM Studio, llama-swap, docling, MinerU, dots.ocr, PaddleOCR-VL, surya, GAIA #5314 and #5352, unsloth #6425, LM Studio #2481, and llama.cpp #27388, #24496, #29689 and PR #30012.
  - Verify: the ADR index lists it; a search of the ADR for home-folder paths and user names finds nothing.
- [x] 9.2 Update `docs/guides/configuration.md` (state folder and local-disk rule, `llamacpp_embed_server`, `ocr_runtime_url`, the retired idle sleep key, the 10-minute idle stop), `docs/guides/architecture.md` (the manager and the lease) and `ocr-workers/README.md` (the runtime block and `OMRS_OCR_RUNTIME_URL`).
  - Verify: `grep -rn "LLAMACPP_IDLE_SLEEP_SECONDS" docs/guides` names it only as retired; the documentation drift check finds no old default.
- [x] 9.3 Update Gotcha 17 in the root `AGENTS.md` (runtime state files are written by every process) and rule 15 in `src/omrs/transports/api/AGENTS.md`.
  - Verify: both files name the runtime state files as written by every process.
- [x] 9.4 Check, read only, whether the live app sets `LLAMACPP_IDLE_SLEEP_SECONDS`, because start-up would then fail.
  - Evidence (2026-11-01, names counted and values not read): not set in the shell environment, in `~/.config/omrs/omrs.jsonc` or in the `com.omrs.web` login item plist. No `~/.omrs/.env` exists. The retirement (task 5.4) goes ahead as planned.

## 10. Closing gates

- [x] 10.1 Re-pin the tripwire by test-ID diff: collect test IDs with `pytest --collect-only -q` before and after the change, diff them, and update `_BASE_EXECUTED` (and `_WEB_EXTRA_CASES` for fastapi tests) with a dated comment that names the added and removed IDs.
  - Verify: the diff is in the pull request description.
- [x] 10.2 Run the parallel fast suite with a JUnit report, then the tripwire on that report: `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q --junitxml=<scratch>/fast.xml`, then `OMRS_TRIPWIRE_JUNIT=<scratch>/fast.xml uv run pytest tests/test_clean_base_tripwire.py -q`.
  - Verify: both pass.
- [x] 10.3 Run `openspec validate --all --strict`.
  - Verify: passes.
- [ ] 10.4 Ask the operator before the full local CI run, then run `./scripts/local_ci.sh`.
  - Verify: every step passes, and no step reports `SKIPPED` without a stated reason.
- [ ] 10.5 Commit with `uv run --no-sync git commit`, open a pull request into `v3`, watch CI to the end, and work through every review comment.
  - Verify: every check is green and every thread is answered and resolved. Merge only when the operator says so.

## Workflow follow-up

- Archive this change after the merge, then sync `llamacpp-runtimes`, `llamacpp-server`, `ocr-worker-engines` and `workspace-integrations`.
- Tell the `dots-mocr-llamacpp-backend` worktree to rebase on `v3` and start its engine rework group.
- Before `git worktree remove`, copy any gitignored evidence (browser screenshots, the `/props` check) to `~/Development/DATA/omrs/` with SHA-256 values. Never copy `.env`.
