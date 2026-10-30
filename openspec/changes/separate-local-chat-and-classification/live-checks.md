# Live checks: separate-local-chat-and-classification (task 8.5)

- Date: 2026-10-29, branch `feat/separate-local-chat-and-classification`.
- Scratch setup: a scratch config folder and workspace in the session scratchpad, `omrs web` on port 8781. No OpenRouter key. The live app (`~/.omrs`, `~/.config/omrs`, port 8765) and the Llama app settings were not changed.
- Llama app: port 9931 (embeddings and classification, Text model `Qwen/Qwen3-0.6B-GGUF:Q8_0`).
- OMRS's own server: Homebrew `llama-server` 0.8.0, Chat address `http://127.0.0.1:8782/v1`, Chat server choice `managed`, Chat model a local `Qwen3-1.7B-Q8_0.gguf` (linked as `/tmp/omrs-live/Qwen3-1.7B-Q8_0.gguf`).

## 1. Classification on the Llama app, Chat on OMRS's own server

1. The Start button on the llama.cpp card started the server. Its argument list was `llama-server -m /tmp/omrs-live/Qwen3-1.7B-Q8_0.gguf --host 127.0.0.1 --port 8782 --sleep-idle-seconds 300 -c 8192`. `GET /v1/models` on 8782 listed only the Chat model.
2. `omrs ingest` of one small Markdown file: the classification requests went to `http://127.0.0.1:9931/v1/completions` (HTTP 200, category `plant_watering`). The owned server's log shows no new task during the ingest (task count 2 before and after).
3. `omrs answer "How often must the office kettle be descaled?"`: status `ok`, `completion_source` `server`, answer "The office kettle must be descaled every 14 days [1]." The owned server's log shows the answer tasks.

Result: pass. Classification reached 9931; the answer came from the owned server.

Note: Qwen3 1.7B thinks at length, and both answer tasks reached the 8,192-token window (`truncated = 1`). The answer still came back cited. A larger context window suits this model better.

## 2. Chat test with a name the Llama app does not list

The Chat test ran in process (`chat_settings._run_test`) against the Llama app on 9931 with the choice `external`:

| Model | Result |
| --- | --- |
| `qwen3:4b` | `ok: false`, reason `model-not-listed`, 16 ms, no prompt sent |
| `Qwen/Qwen3-0.6B-GGUF:Q8_0` | `ok: true`, 2,757 ms |

Result: pass.

## 3. Browser check (task 7.10)

A headless Edge with its own scratch profile opened Settings > Providers at 1280 px and 390 px. Screenshots are in `screenshots/`.

| State | Checks |
| --- | --- |
| `managed`, Chat on llama.cpp (`managed-*.png`) | Three blocks in order: Embeddings, Classification (metadata), Chat. "Text model (classification)" in the Classification block. Read-only Chat model row with "Change in Settings > Chat". OMRS server callout. Local server panel without a Model row. |
| `external`, Chat on OpenRouter (`external-*.png`) | "Chat uses OpenRouter (deepseek/deepseek-v4-flash-0731)". Llama app callout naming `models.user.ini` and the relaunch pause. No Local server panel. |
| `managed`, no classification address (`shared-*.png`) | Shared-address warning in the Classification block and in the Local server panel. |

At 390 px, `scrollWidth` equals the page width in every state, so nothing scrolls sideways. Observation (not a defect of this change): long read-only values such as the Text model wrap one character group per line in the narrow value column.
