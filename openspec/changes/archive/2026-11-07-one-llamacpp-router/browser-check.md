# Browser check, task 7.5 (one-llamacpp-router)

> Screenshots are kept out of Git: they show local scratch paths. `<screenshots>` is the folder `browser-check/` beside the session files in the OMRS data folder (`DATA/omrs/handoffs/router-session/browser-check/`, with `SHA256SUMS`).

- Date: 2026-11-06
- Commit: 48f2a3b9 (branch `feat/one-llamacpp-router`, worktree clean before this check)
- Result: all checks pass. Four small defects found (none blocks the merge). Screenshots are in `<screenshots>/`.

## Setup

- Built the pages first with `npm run build` in `web/`.
- Scratch folders under the session scratchpad: `config/`, `state/`, `workspace/`, `data/`, `home/`. The live `omrs.jsonc` was not copied.
- Scratch `omrs.jsonc` holds four keys: `llamacpp_server_binary` (the fake `llama-server` from `tests/fixtures/llamacpp/install.py`), `llamacpp_router_url` (`http://127.0.0.1:18792/v1`), and `llamacpp_models` (the two shipped entries, each pointing at a tiny fake `.gguf` file with its SHA-256). `answer.model` stayed empty.
- Server: `omrs web --workspace <scratch>/workspace --port 18791`, `HF_HUB_OFFLINE=1`, `env -u OPENROUTER_API_KEY`, own `HOME`, `OMRS_CONFIG_DIR`, `OMRS_STATE_DIR`, `XDG_DATA_HOME`. The Orca tab kept the origin `http://127.0.0.1:18791`; the `--allow-origin` pane variants were also passed. Sign-in worked with the `#bootstrap=` token.
- Ports 8765 and 9931, `~/.omrs`, `~/.config/omrs` and the login item were not touched.
- First run used the shipped list with no files. Pressing Start then began a real Hugging Face download (see defect 2). I stopped the server within seconds (68 KB written, scratch cache deleted) and rebuilt the scratch config with fake files and `HF_HUB_OFFLINE=1`.
- Orca capture notes. A plain screenshot at 1,280 px returned a blank or offset frame. At 1,280 px the pages were captured with `full-screenshot`, with the other cards hidden in the live DOM (display only) so the router panel fits one frame. At 390 px plain screenshots of the viewport work, so long screens have two frames (controls, table). Where a scroll is followed by a frame, the first frame can be stale.

## Results

Width 1,280 px and 390 px, light and dark. "Measure" = `scrollWidth <= clientWidth` plus every Start, Stop, Restart, Edit, Save, Cancel and Use default button inside the viewport width (run through Orca eval).

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | Router panel: mode row ("Who runs llama.cpp"), address, program path, "Program in force" line, state line | Pass at both widths, both themes | `providers-router-running-1280-dark.png`, `providers-router-running-1280-light.png`, `providers-router-390-dark-controls.png`, `providers-router-390-dark-table.png` |
| 2 | Start, Stop, Restart with the fake router (1,280 px) | Pass. Start gave Running and the port 18792 opened. Stop gave Stopped and the port closed. Restart gave Running again | text of the state line, `lsof` |
| 3 | Start, Stop, Restart at 390 px | Pass, same results | measure: 9 buttons inside, 0 outside |
| 4 | Edit on a model row | Pass. Inline form opens (context size, batch, parallel, cache fields), Save model and Cancel reachable at 390 px | `providers-model-edit-390-dark.png` (1,280 px form checked from the page snapshot only) |
| 5 | Memory rows "Models loaded at once" and "Free memory margin (MiB)": Edit, Save, Use default | Pass at both widths. Save wrote the key (2 and 3, then 4,096), showed "Saved in settings" and "Restart to apply". Use default returned to 4 and 8,192 and removed the key from `omrs.jsonc` | text diff, `omrs.jsonc` read back |
| 6 | Model table | Pass. Table at 1,280 px; stacked cards at 390 px with no clipping | `providers-router-running-1280-dark.png`, `providers-router-390-dark-table.png` |
| 7 | Problems line for an unlisted role model | Pass. Chat model set to `Qwen/NotListed-GGUF:Q4_K_M` gave "The chat model is not in the list. Edit the list below or choose another model." Restored with Clear | `providers-router-problem-1280-light.png`, `providers-router-problem-390-dark.png` |
| 8 | Settings > Chat on the fresh config: "Choose a Chat model" | Pass. Text, model picker and "Use as Chat model" show. Picker lists the one router model | `chat-fresh-1280-dark.png`, `chat-fresh-1280-light.png`, `chat-fresh-390-dark.png`, `chat-fresh-390-light.png` |
| 9 | Shared-model note when Chat uses the classification model | Pass. Warning "Chat and classification share this model..." with three ways out. The router table shows "Classification, Chat, Shared by Chat and classification" | `chat-shared-model-1280-dark.png`, `chat-shared-model-1280-light.png`, `chat-shared-model-390-light.png` |
| 10 | Integrations > Model runtimes: router row and Stop | Pass. Row shows Managed, Running, address, memory, models with roles. Stop opens a confirmation, "Stop runtime" stopped the fake router (port closed) | `integrations-model-runtimes-1280-dark.png`, `integrations-model-runtimes-1280-light.png`, `integrations-model-runtimes-390-dark.png`, `integrations-model-runtimes-390-light.png`, `integrations-stop-confirm-1280-dark.png` |
| 11 | Integrations > Extras: "llama.cpp provider" card and Get llama.cpp (not pressed) | Pass, with a wording defect (defect 3) | `integrations-llamacpp-card-1280-dark.png`, `integrations-llamacpp-card-1280-light.png`, `integrations-llamacpp-card-390-light.png` |
| 12 | "Get a model" panel opens (no download started) | Pass. Search box and the Hugging Face cache note show | `get-a-model-1280-dark.png`, `get-a-model-1280-light.png`, `get-a-model-390-dark.png` |
| 13 | No sideways scroll at 390 px | Pass. `scrollWidth` 390, `clientWidth` 390 on Settings > Providers, Settings > Chat, Integrations, Integrations > Model runtimes, Integrations > Model files, and with "Get a model" open. The panel, Chat and runtimes screens were measured in both themes. Integrations, Model files and "Get a model" were measured in light theme only | measure output, screenshots above |

## Defects

Each score is likelihood x impact, 1 to 10.

### 1. Stop confirmation for the router names another process and OCR (7 x 2 = 14)

- What: Stopping the router from Integrations > Model runtimes opens "Another OMRS process uses this runtime. Requests in progress fail, and OCR uses the fallback engine." Only one OMRS process ran (the web server that started the router). The text also talks about OCR for a runtime that serves embeddings and classification.
- Repro:
  1. Start the scratch server and sign in.
  2. Settings > Providers > Router > Start (fake router), wait for Running.
  3. Integrations > Model runtimes > llama.cpp router > Stop.
  4. The dialog "Stop llama.cpp router?" shows the text above. Screenshot `integrations-stop-confirm-1280-dark.png`.
- Where to look: `web/src/integrations/StopRuntime.tsx` line 60 (fixed text) and the `clients` value that the model-runtimes route returns for the router (`item.clients === "some"`). I did not read the API value, so whether the router reports `some` for its own process is unconfirmed.

### 2. A normal first download shows as "Failed" (10 x 3 = 30)

- What: On a fresh install the listed models have no file. Start begins the automatic download and the panel state line reads "Failed: Models are still downloading." and Start, Stop, Restart stay as if the router had crashed. A download in progress is not a failure. After a server restart the last state stays "Failed: No model is downloaded yet." even after the files exist, until Start is pressed again.
- Repro:
  1. Fresh scratch config with the shipped model list (no `file` values), router mode managed, program path set.
  2. Settings > Providers > Router > Start.
  3. State line shows "Failed: Models are still downloading." (the server log shows the Hugging Face request and a `.incomplete` blob for Qwen3-Embedding-4B).
- Operator decision (not a defect by itself): Start on a fresh install downloads about 4 GB from the internet with no prompt. The panel does not say so before the press.

### 3. Integrations card says "Ready" and "Not installed" together (4 x 2 = 8)

- What: With a program path in force that the user set, the "llama.cpp provider" card shows "Ready" and "llama.cpp build b11941. Not installed", plus a Get llama.cpp button. The second line refers to the pinned build, not to the program in use.
- Repro: set `llamacpp_server_binary` to a valid `llama-server`, open Integrations > Extras, find the llama.cpp provider card. Screenshots `integrations-llamacpp-card-1280-light.png`, `integrations-llamacpp-card-390-light.png`.

### 4. Start looks pressable while the router runs (10 x 1 = 10)

- What: While the state is Running, Start is disabled but keeps the accent fill, and in light theme its label is faint. Stop and Restart use the plain outline.
- Repro: Router panel with the router Running. Screenshots `providers-router-running-1280-dark.png`, `providers-router-running-1280-light.png`.

## Not checked

- The Get llama.cpp install (not pressed, as agreed) and the Test buttons.
- A real `llama-server` and a real model. State "Unloaded" for both models is the fake router's behaviour.
- Screenshots missing: Router panel at 390 px in light theme (a stale frame was discarded and the server was stopped before a retake; the same screen passed the DOM measure in light theme), the model Edit form at 1,280 px (checked in the page snapshot only), "Get a model" at 390 px light, problem line at 390 px light and 1,280 px dark.
- Settings > Chat at 1,280 px and 390 px was only captured with the answer provider default (llama.cpp); other providers were not tried.

## Cleanup

Server stopped (`pkill -f "omrs web --workspace <scratch>/workspace"`), no fake router process left, Orca tab closed, ports 18791 and 18792 free. The scratch folders remain in the session scratchpad.

## Re-check after fixes (2026-11-06)

- Commit: 6d8d239c (branch `feat/one-llamacpp-router`). Pages rebuilt first with `npm run build` in `web/`.
- Result: checks 1 to 5 pass in their listed scope. Two new defects found (one with a score of 30, so it needs a fix before merge). Screenshots in `<screenshots>/`, prefix `recheck-`.
- Setup: fresh scratch root `browser2/` (config, state, workspace, data, home, models, fakebin) in the session scratchpad. Server `omrs web --workspace <scratch>/workspace --port 18791` with `HF_HUB_OFFLINE=1`, own `HOME`, `OMRS_CONFIG_DIR`, `OMRS_STATE_DIR`, `XDG_DATA_HOME`, and the same `--allow-origin` pane variants. Fake `llama-server` and fake router from `tests/fixtures/llamacpp`, router address `http://127.0.0.1:18792/v1`.
- Network guard: the model host reads in `huggingface_models.py` use `httpx` and ignore `HF_HUB_OFFLINE`. The server therefore ran with `HTTPS_PROXY` and `HTTP_PROXY` set to `127.0.0.1:18793` (and `NO_PROXY` for loopback). Port 18793 was closed (every request fails at once) or held by a small listener that never answers (each request waits for the 10-second timeout). No request left the machine. No model file was written (`find` on the scratch cache and data folders: none).
- Two scratch configs: A (programme set to the fake, shipped model list, no files) and B (same, plus both listed models pointing at tiny fake `.gguf` files with their SHA-256). The server restarted between A and B.
- Orca tab: one tab, `--page <id>` on every command, viewport set again after every page load. Themes set through the `omrs-preferences` key, then reload.
- Ports 8765 and 9931, `~/.omrs`, `~/.config/omrs` and the login item were not touched. Both ports stayed occupied by their own owners throughout.

### Results

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1a | Config A, Start: dialog names both models and "The size is unknown." (title "Download 2 models?", each row "Size unknown"). Same text in the four combinations of 1,280 and 390 px, light and dark | Pass | `recheck-start-dialog-1280-dark.png`, `recheck-start-dialog-1280-light.png`, `recheck-start-dialog-390-dark.png`, `recheck-start-dialog-390-light.png` |
| 1b | Cancel starts nothing: dialog closes, state line "Stopped", port 18792 closed, no fake-router process (all four combinations) | Pass | `lsof`, `pgrep` after each Cancel |
| 1c | Download: state line becomes "Downloading models. The router starts when they are ready." and never "Failed" while the download is pending (1,280 dark and 390 light). Rows show "Not downloaded" and "Downloading". No `huggingface.co` line in the server log, no file written | Pass for the wording. The end of the wait is defect 5 | `recheck-downloading-1280-dark.png` |
| 1d | With both files present (config B), Start shows no dialog, state goes Running, port 18792 opens (1,280 and 390 px, both themes) | Pass | state line text, `lsof` |
| 2 | While the router runs, Start is disabled with the same outline colours as Stop and Restart, at 0.6 opacity (light: text `rgb(57,58,52)` on `rgb(248,247,245)`; dark: `rgb(201,197,186)` on `rgb(24,23,21)`). No accent fill. Faint but legible in the light theme | Pass | `recheck-start-outline-1280-light.png`, `recheck-router-running-1280-dark.png`, `recheck-router-running-390-light.png`, computed styles |
| 3 | Integrations > Model runtimes: Stop with only this process opens no dialog; state goes Stopped and port 18792 closes (1,280 light and dark, 390 light and dark) | Pass | `recheck-runtimes-stopped-1280-light.png`, `recheck-runtimes-stopped-390-dark.png` |
| 4 | Integrations llama.cpp card with `llamacpp_server_binary` set to the fake: second line is only "Uses your own program: <path>", text "Not installed" absent, no Get button (1,280 light and dark, 390 light) | Pass | `recheck-llamacpp-card-1280-light.png`, `recheck-llamacpp-card-390-light.png` |
| 5 | No sideways scroll at 390 px: `scrollWidth` 390 and `clientWidth` 390 on Settings > Providers (Router panel closed, running, dialog open), Integrations, Integrations > Model runtimes, light and dark. Router buttons Start, Stop, Restart, Edit all inside the viewport | Pass | measure output |

### The four earlier defects

| Earlier defect | Status | Note |
|----------------|--------|------|
| 1. Stop confirmation names another process and OCR | Fixed | No dialog in four combinations. The dialog for a real second process was not tried (needs a second OMRS process). |
| 2. First Start downloads about 4 GB with no prompt, and the line says "Failed: Models still downloading." | Fixed for the prompt and the line. Not fully closed | Dialog now asks first; the line says "Downloading". The size in the dialog was only seen as "unknown". The old note that a stored failure survives a server restart was not re-checked: the state folder was wiped between runs. Defect 5 below is a new problem in the same path. |
| 3. Card says "Ready" and "Not installed" together | Fixed | Check 4. |
| 4. Start looks pressable while the router runs | Fixed | Check 2. |

### New defects

Scores are likelihood x impact, 1 to 10.

#### 5. A failed automatic download makes the server spin (5 x 6 = 30)

- What: when the model host cannot be read (no network, host down, or a plan that is refused), a waiting first Start never ends. The router lease asks for the download again at once, it fails at once, and this repeats about 90 times a second. One CPU core stays at 98 per cent, the server log grows by about 1.2 MB a minute, and the panel flips between "Downloading models. The router starts when they are ready." and "Stopped" with no failure line. Stop does not end it (six Stop calls, button and API); only stopping the server did. With a listener that never answers, the same loop runs once every 10 seconds, so the loop also exists in a slow-network case.
- Likely cause (read from code, not changed): `RouterControl.load` in `src/omrs/transports/api/llamacpp_server.py`. After the last download ends without a file, it calls `self.start(config)`. `start` joins the router, sees the same missing file, queues the download again and sets the waiting flag again. `RouterDownloads._ended_without_file` calls `load` for every failed plan.
- Repro:
  1. Config A, server started with the proxy variables above and port 18793 closed.
  2. Settings > Providers > Router > Start, then Download in the dialog.
  3. Read `cannot start: network` lines in the server log: 164 after 2 seconds, 525 after 6 seconds. `ps -o pcpu` shows about 98.
  4. Press Stop or POST `/v1/llamacpp/router/stop`. The count keeps rising.
- Expected by the spec text: the failed `not-downloaded` state with "No model is downloaded yet." and an end to the wait.
- Screenshot: `recheck-offline-spin-1280-dark.png`.
- Fix: end the wait with the `not-downloaded` refusal when a plan fails (do not call `start` from `load` for an entry that still has no file), and test that a failed plan queues no second download.

#### 6. Model runtimes page shows "Stopped" for up to 30 seconds after Start (4 x 2 = 8)

- What: open Integrations > Model runtimes while the router is stopped, go to Settings > Providers, press Start, and return within 30 seconds. The card still says "Stopped" and has no Stop button, while `GET /v1/runtimes` already says `running`. After 30 seconds the page is right. The page list uses the 30-second stale time and the Start action does not refresh the runtime list (`web/src/api/llamacppRouterHooks.ts`, `web/src/api/modelRuntimesHooks.ts`).
- Repro: steps above with config B; 1,280 px, light theme.
- Fix: invalidate `modelRuntimesKey` in the success handler of the router Start, Stop and Restart actions.

#### 7. Dialog rows wrap unevenly at 390 px (6 x 1 = 6, cosmetic)

- What: at 390 px the first model's "Size unknown" drops under its name while the second stays on the right. See `recheck-start-dialog-390-dark.png`. Also, while the size read waits for a slow host (up to 10 seconds per model), the Start, Stop and Restart buttons are all disabled and the line says "Stopped" with no sign that a check runs.
- Fix: give the size its own line below the name at narrow widths for every row, and show a short "Checking model sizes" line while the read runs.

### Not checked

- Real download sizes in the dialog and any real download (the guard blocks the host by design).
- The "Another OMRS process" dialog when a second process holds the router.
- A stored `not-downloaded` failure surviving a server restart (state folder wiped between runs).
- The Downloading state line at 390 px in dark and at 1,280 px in light, and the Downloading screenshot at 390 px (the one taken was the top of the page, discarded).
- Chat, Model files and Get a model screens (not changed after task 7.5).

### Cleanup

Server stopped with `pkill -f "omrs web --workspace <scratch>/workspace"`, the fake router stopped with it, the listener on 18793 stopped, the Orca tab closed, ports 18791, 18792 and 18793 free. Scratch folders remain in the session scratchpad. Screenshots show the scratch path, which holds the user name: strip it before any upload. `.openspec.yaml` of this change appeared as modified (a `pin: true` line) during the check. It was clean when the check began and this check did not write it.
