# Live checks: tasks 8.4 and 1.1b

Date: 2026-10-29. Branch `feat/add-model-search-and-download`. Code under test: `158b6034` for the first download attempt, then `f68ee693` (the Xet fix) for everything after it.

## Result

| Step | Result |
| --- | --- |
| A1 Download `Qwen/Qwen3-1.7B-GGUF:Q8_0` in the panel | Fail on `158b6034` (bug 1). Pass on `f68ee693`. |
| A2 Quit and reopen the Llama app | Pass. |
| A3 Refresh models lists the new model | Pass. |
| 1.1b The relaunched app lists `unsloth/SmolLM2-135M-Instruct-GGUF:Q2_K` | Pass. |
| B Managed server: Download (cached), Use this model, Restart | Pass. |
| C Ollama pull and list line | Pass, with a changed model name (bug 3). |
| D Cleanup | Done. |

The checks found three bugs and two small observations. See "Bugs" below.

## Versions

| Item | Version |
| --- | --- |
| Llama app | 0.46.1 (build 261028.1706), from `Info.plist` |
| Llama app server program (`~/.llama-app/llama`) | 0.7.0-dev, build 11941, commit 19ff817fb |
| Homebrew `llama.cpp` (new) | 0.8.0, build 11960, commit 8642541b2 |
| Homebrew dependencies installed with it | `libomp` 23.1.4, `ggml` 0.28.0 |
| `llama-server` path | `/opt/homebrew/bin/llama-server`, a link to `../Cellar/llama.cpp/0.8.0/bin/llama-server` |
| Ollama | 0.40.13 |
| `huggingface_hub` | 1.27.0 (`hf_xet` 1.6.0, Python 3.14.9, from the Xet log) |

`brew install llama.cpp` took about 20 seconds. Homebrew warned that the `llama` command in `~/.local/bin` hides the Homebrew one. That is harmless here.

## Setup

- Scratch `omrs web` on port 8792, started from the worktree. It used a copy of `~/.config/omrs/omrs.jsonc` without the API key, and its own workspace and LanceDB folder. `OPENROUTER_API_KEY` was unset for the process.
- `HF_HUB_CACHE` and `HF_HOME` were not set, so downloads went to `~/.cache/huggingface/hub`.
- The page was a new Orca browser tab, signed in with the bootstrap token and the `--allow-origin` option. The tab was closed at the end.
- I did not touch `~/.omrs`, the live `~/.config/omrs/omrs.jsonc`, or the live server on port 8765.
- Before the checks the Llama app listed 8 models and `models.ini` had a time stamp of 2026-10-28 15:19. `Qwen/Qwen3-1.7B-GGUF` was not in the cache. `unsloth/SmolLM2-135M-Instruct-GGUF` (Q2_K only, 88,201,792 bytes) was.

## A. External server (the Llama app on port 9931)

The managed server stayed stopped for all of step A. The scratch Chat address was `http://127.0.0.1:9931/v1`.

### A1. Download

First attempt on `158b6034`: **fail**.

- Started 16:59:49. The bar showed 0 B for 44 seconds, then 261.4 MiB, then nothing.
- At 17:01:34 the job ended with "No data arrived for 60 seconds, so the download ended. Try again." The server log said `ended: failed stalled`. The partial file was deleted.
- The Xet log shows the transfer was healthy. It had received 263 MB at 17:00:20 and 841 MB at 17:01:30, about 8 MB per second. The progress callback of `hf_hub_download` fired once in that time.
- I asked the coordinator. It fixed the watchdog in `f68ee693` (count Xet network bytes as a sign of life).

Second attempt on `f68ee693`: **pass**.

- Started 17:10:07. The job passed the 60-second mark and ended `succeeded` at 17:13:32, after 3 minutes 25 seconds.
- The bar stayed at 0 B for about 2 minutes, then moved in steps: 133.4 MiB, 261.4 MiB, 369.3 MiB, then done. See bug 2.
- The cache holds one blob of 1,834,426,016 bytes (1.7 GiB on disk), one snapshot file `Qwen3-1.7B-Q8_0.gguf`, and no `.incomplete` file.
- The panel text after success:
  - "Downloaded Qwen/Qwen3-1.7B-GGUF:Q8_0."
  - "The file is in ~/.cache/huggingface/hub. If your server reads another cache folder, point it at this one."
  - "Your own llama.cpp server must load this model. The Llama app lists new models only when it starts, so quit and reopen it, then press Refresh models."
  - A Refresh models button. There was no Use this model button.

### A2. Relaunch

- 17:14:03: `osascript` quit the app. Both the app and its `llama serve` process ended. Port 9931 went down.
- 17:14:16: `open -a Llama`. Port 9931 answered at the first poll, within 3 seconds.
- `models.ini` was rewritten at 17:14. It now holds 10 entries. The 8 old entries are unchanged. The new ones are `Qwen/Qwen3-1.7B-GGUF:Q8_0` and `unsloth/SmolLM2-135M-Instruct-GGUF:Q2_K`. `~/.config/llama/models.user.ini` kept its old time stamp.
- The live app was without a server for about 13 seconds. This was approved.

### A3. Refresh models

- After pressing Refresh models the panel said: "Your server lists Qwen/Qwen3-1.7B-GGUF:Q8_0."
- `POST /v1/connections/llamacpp/models` through the scratch server returned `reachable: true` and 10 models, including `Qwen/Qwen3-1.7B-GGUF:Q8_0`.

### 1.1b

**Pass.** After the relaunch the app lists `unsloth/SmolLM2-135M-Instruct-GGUF:Q2_K`. Together with the earlier result (design D4: a running app did not pick up the file after 45 seconds), the rule is: the Llama app lists the cache when it starts, and not while it runs. The panel text already says so. Task 1.1b can be ticked. Version: Llama app 0.46.1.

## B. Managed server

The panel accepts `/opt/homebrew/bin/llama-server`. It needed no other setup.

1. Set in the scratch settings: Chat address `http://127.0.0.1:9942/v1` (the managed port comes from this address), program path `/opt/homebrew/bin/llama-server`, model `unsloth/SmolLM2-135M-Instruct-GGUF:Q2_K`.
2. Start: the state went Starting, then Running, within 6 seconds. The process was `llama-server -hf unsloth/SmolLM2-135M-Instruct-GGUF:Q2_K --host 127.0.0.1 --port 9942 --sleep-idle-seconds 300 -c 16384`. The log shows `loading model`, `model loaded`, and `listening on http://127.0.0.1:9942` after 4 seconds, with no download line. `~/.cache/llama.cpp` stayed absent.
3. Panel file list for `unsloth/SmolLM2-135M-Instruct-GGUF`, Q2_K (84.1 MiB), Download: the bar read "0 B of 0 B" and the job ended in 2 seconds. The panel said "Downloaded unsloth/SmolLM2-135M-Instruct-GGUF:Q2_K." The cache did not change (same 3 entries, same blob, same time stamp of 15:34).
4. Use this model: it worked in this session, so the credentials scope was present and the Model row fallback was not needed. The panel said "Saved. The server loads the new model after a restart." and showed "Restart server to load it".
5. Restart: the process id changed from 16020 to 21602 and the state was Running within 2 seconds. The new log shows the same load from the cache. `GET /health` returned `ok` and `/v1/models` listed the model. The cache did not change.
6. Stop: the state went Stopped. No `llama-server` process and no listener on port 9942 stayed.

**Pass.** The cached model loaded with no new bytes, once through Start and once through Restart.

## C. Ollama

Changed model name. The panel cannot pull `smollm2:135m` (bug 3). I pulled the same model through the panel's Hugging Face route instead.

- Search "smollm2" listed only `hf.co/...` repos. Search "smollm2:135m" showed "No model matches that search."
- Chose `hf.co/unsloth/SmolLM2-135M-Instruct-GGUF`, file Q2_K, Download. Start 17:08:16.
- The bar went 0, 4.4, 11.9, 18.8, 27.4, 42.0, 50.9, 60.8, 77.5, then 84.1 MiB of 84.1 MiB, about every 2 seconds. It finished in about 24 seconds.
- The panel said "Downloaded ..." and "Ollama lists hf.co/unsloth/SmolLM2-135M-Instruct-GGUF:Q2_K."
- `ollama list` confirmed it (88 MB).
- I ran `ollama rm "hf.co/unsloth/SmolLM2-135M-Instruct-GGUF:Q2_K"`. The list is back to `qwen3:0.6b`, `qwen3:4b` and `qwen3-embedding:0.6b`.

**Pass** for the pull, progress and list line. The library-name path (a name with no `hf.co/` prefix and no tag, which pulls `:latest`) was not checked live.

## D. Cleanup

- Removed `~/.cache/huggingface/hub/models--unsloth--SmolLM2-135M-Instruct-GGUF` (84 MB). Nothing else in the cache was removed.
- Kept `~/.cache/huggingface/hub/models--Qwen--Qwen3-1.7B-GGUF`: 1,834,426,016 bytes (1.7 GiB). The Llama app lists it now.
- Stopped only the scratch server (`pkill -f` with its workspace path). The live server on port 8765 still runs. The Llama app is running on port 9931 with 10 models.
- Three `.incomplete` files for `perplexity-ai--pplx-computer-qwen-3-8-27b-mlx-20260824` were already in the cache. They are not from these checks. I left them.
- Homebrew `llama.cpp` 0.8.0, `libomp` and `ggml` stay installed (approved).
- The scratch folder, with the server logs, stays in the scratchpad.

## Bugs

Scores follow the rule: likelihood times impact, fix at 5 or more.

### 1. Stall watchdog ended a healthy Xet download (fixed in `f68ee693`)

- What is wrong: the 60-second stall watchdog only saw `tqdm` callbacks. On a large Xet file those arrive rarely, so a working download looked stalled.
- Score: likelihood 9, impact 7, total 63.
- Status: fixed by the coordinator. The same download then finished in 3 minutes 25 seconds.
- What to do: keep a test with a large Xet-like pattern (long gaps between callbacks, bytes still flowing). Re-run A1 after any change to the watchdog.

### 2. The progress bar lags far behind the network on a large Xet file

- What is wrong: the bar showed 0 B for about 2 minutes while the Xet log showed 1.18 GB received (17:12:18). It then moved in steps. A user can think the download is stuck. The job still ends correctly.
- Score: likelihood 8, impact 2, total 16.
- What to do:
  1. Decide whether to feed the Xet network byte count to the bar as well as to the watchdog (the fix already reads it).
  2. If not, add a line under the bar for Xet files, for example "Large files can show no change for a while", and a test that the line shows.

### 3. The Ollama panel cannot pull a name that is not in the built-in list

- What is wrong: design D6 says a typed name that passes the Ollama name rule is accepted. Only the route does this. The panel shows only the built-in names and `hf.co/` results, so `smollm2:135m` (or any tagged name outside the 13 built-in names) cannot be pulled from the panel.
- Score: likelihood 6, impact 3, total 18.
- What to do, pick one:
  1. Add a "Pull `<typed name>`" row when the typed text passes `is_valid_ollama_name`, with a test.
  2. Change D6 and the guide to say the panel offers only built-in names and `hf.co/` repos.
  3. Add popular small names to the built-in list (for example `smollm2`) and keep the rest as is.

### 4. Minor: "0 B of 0 B" for an already cached file

- The bar shows "0 B of 0 B" for 1 to 2 seconds before the success line (step B3).
- Score: likelihood 3, impact 1, total 3. Below 5, so no fix. Proposed issue title: "Download panel shows 0 B of 0 B for a file that is already cached".

### 5. Minor: the Llama app keeps a deleted model in its list until its next launch

- After step D the app still lists `unsloth/SmolLM2-135M-Instruct-GGUF:Q2_K` and `models.ini` still has the entry, because the app lists the cache only at launch. A request for that model would fail.
- Nothing to fix in omrs. Nobody uses the entry. To clear it, quit and reopen the Llama app (about 13 seconds without a server). I left the app running as asked.

## Follow-up by the coordinator

- Bug 2 is fixed in `7cb436fc`: on Xet the bar follows the network bytes, capped at the file size.
- Bug 3 is fixed after this check: the Ollama panel offers the typed name first, with the badge "Typed name", when it passes the Ollama name rule.
- Bug 4 stays a proposed issue (score 3).
- Tasks 1.1b, 7.7 and 8.4 are ticked.

## Next steps (as written by the worker)

1. Decide bug 2 and bug 3 (options above).
2. Tick task 1.1b in `tasks.md` and note the Llama app version (0.46.1) and the launch-only listing rule in design D4.
3. Tick the live-check items of 8.4 that passed. Leave a note that the Ollama library-name path was not run live.
4. Add the proposed issue for bug 4 only if you want it.
