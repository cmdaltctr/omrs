# Browser check of the "Get a model" panel (task 7.7)

Date: 2026-10-29. Branch: `feat/add-model-search-and-download`. Viewports: 1280 px and 390 px wide.

## Setup

- A scratch `omrs web` server on port 8791. It had a scratch config without API keys, an empty library and a scratch Hugging Face cache folder. `HF_TOKEN` and `OPENROUTER_API_KEY` were unset.
- The browser was an Orca tab. The viewport was set to 1280 x 900 and 390 x 844, and the tab was reloaded after each change (without a reload the tab kept the old column layout). The tab was signed in with the bootstrap link.
- Hugging Face search was live. The download was `unsloth/SmolLM2-135M-Instruct-GGUF`, file `Q2_K` (84.1 MiB, 88,201,792 bytes).
- The first half of the run used the default Xet transfer. The Xet path showed no partial progress (finding 2). The server was then restarted once with `HF_HUB_DISABLE_XET=1` to see a partly filled bar. Those frames come from the plain HTTP path.
- The managed llama.cpp server stayed Stopped. The chat address pointed at the Llama app on port 9931. The panel only read its model list.
- Ollama was searched only. No pull ran.
- In the two finished-state screenshots, the cache folder path was replaced with `<scratch folder>/hfcache` in the page text before the capture. The real path contains the login name. Nothing else was edited.

## Result per check

| # | Check | 1280 px | 390 px |
|---|-------|---------|--------|
| 1 | Ollama and llama.cpp cards show "Get a model". OpenRouter does not. | Pass | Pass |
| 2 | Search on llama.cpp: results, downloads count, Gated badge, no horizontal scroll, long ids wrap | Pass | Pass |
| 3 | File list: labels with sizes, `Q4_K_M` preselected, "closest to full quality" mark | Pass | Pass |
| 4 | Progress: bar, bytes, Cancel, "The download stopped.", download again to finish | Pass, see findings 1 to 3 | Pass, see finding 2 |
| 5 | Finished with the managed server stopped: cache folder, Llama app note, Refresh models, no Use this model | Pass | Pass |
| 6 | Ollama search: built-in names first, then `hf.co/` entries | Pass | Pass |

Details:

1. The OpenAI-compatible and Anthropic cards also show no panel. At 390 px the page width equals the viewport width (no horizontal scroll) on the Providers page.
2. Typing `smollm2` gave 20 results with counts such as "66.9k downloads". `google/gemma-2b` carries a Gated badge. A 99-character id wraps over three lines at 390 px and nothing overflows.
3. The list is `Q2_K` 84.1 MiB up to `F16` 258.3 MiB. `Q4_K_M` is checked and has a "Recommended" badge. `Q8_0` has "closest to full quality".
4. Cancel stopped the download within about 3 seconds on both paths and removed the partial file. A new download after the cancel finished and wrote the file to the cache.
5. After "Downloaded ...", the panel shows the cache folder, the note "The Llama app lists new models only when it starts", and Refresh models. There is no Use this model button. Refresh models answered "Your server does not list it yet."
6. `qwen3` gave `qwen3`, `qwen3-embedding` and `qwen3-coder` (each tagged "Ollama library") before the `hf.co/` entries. Download was not pressed.

The browser console had no messages. The server logs had no traceback.

## Findings

Scores are likelihood x impact, each from 1 to 10.

1. **A Xet download ended as "stalled" once.** The first download after the server started kept the `.incomplete` file at 0 bytes for 60 seconds and ended with "No data arrived for 60 seconds" (`1280-stalled.png`). A raw read of the same file ran at 7.4 MB/s straight afterwards. The next three Xet downloads that I did not cancel finished in about 10 to 25 seconds. The cause is not known. Likelihood 3, impact 3, score 9. To do: repeat the first download on a fresh server several times and see how often it happens.
2. **On the Xet path the bar stays at "0 B of 84.1 MiB" until the end** (`1280-progress-xet.png`). The plain HTTP path moves in 10 MiB steps (`1280-progress.png`, `390-progress.png`). Design D10 notes that Xet reports in large steps, and all small GGUF repos checked in task 1.2 are on Xet. With no updates, the 60-second stall rule may also end a healthy download on a slow link. I did not test that. Likelihood 8, impact 2, score 16. To do: decide whether to show an indeterminate bar, or to read the size of the `.incomplete` file (the fallback named in task 1.2).
3. **The progress track is hard to see in the dark theme at 0%.** Only a thin outline shows. Likelihood 8, impact 1, score 8. To do: raise the track contrast.
4. **The last job line stays after a reload, even with no repo chosen** ("The download stopped." under the empty search box, `390-get-a-model.png`). It may be intended. It reads as stale. Likelihood 6, impact 1, score 6.
5. **Gated rows lay out differently.** The count sits beside the repo chip and the Gated badge wraps to its own line. Other rows put the count below the chip. Likelihood 2, impact 1, score 2. Below 5, so no change. Proposed issue: "Align the Gated result row with the other rows".

Note, no score: 20 results put the file list about 1,450 px below the search box at 1280 px and about 1,350 px at 390 px. The "Files in" heading is the only sign of which repo is open.

Not covered: Use this model with a running managed server, the light theme, a Download press on the Ollama card, and the file list of a gated repo. Task 8.4 covers the first of these.

## Screenshots

| File | Shows |
|------|-------|
| `1280-providers.png` | Providers page. Ollama and llama.cpp cards have "Get a model". OpenRouter has none. |
| `1280-search.png` | llama.cpp search for `smollm2`: results and download counts. |
| `1280-gated.png` | Search for `gemma-2b`: the Gated badge on `google/gemma-2b`. |
| `1280-files.png` | File list with `Q4_K_M` preselected and the two badges. |
| `1280-progress.png` | Running download on the HTTP path: 10.0 MiB of 84.1 MiB, Cancel. |
| `1280-progress-xet.png` | Running download on the Xet path: 0 B of 84.1 MiB (finding 2). |
| `1280-cancelled.png` | The line "The download stopped." after Cancel at 10.0 MiB. |
| `1280-stalled.png` | The one-line reason after the Xet stall (finding 1). |
| `1280-finished.png` | Finished state with the managed server stopped. |
| `1280-ollama-search.png` | Ollama search for `qwen3`: library names first, then `hf.co/` entries. |
| `390-get-a-model.png` | The panel before a search, with the old "The download stopped." line (finding 4). |
| `390-search.png` | llama.cpp search results. No horizontal scroll. |
| `390-files.png` | File list. |
| `390-progress.png` | Running download: 10.0 MiB of 84.1 MiB, bar and Cancel in one row. |
| `390-finished.png` | Finished state: cache folder, Llama app note, Refresh models. |
| `390-ollama-search.png` | Ollama search results. |
| `390-ollama-long-id.png` | Long `hf.co/` ids wrap over three lines. |
