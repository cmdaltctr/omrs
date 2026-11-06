# Browser check, task 7.5 (one-llamacpp-router)

- Date: 2026-11-06
- Commit: 48f2a3b9 (branch `feat/one-llamacpp-router`, worktree clean before this check)
- Result: all checks pass. Four small defects found (none blocks the merge). Screenshots are in `browser-check/`.

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
