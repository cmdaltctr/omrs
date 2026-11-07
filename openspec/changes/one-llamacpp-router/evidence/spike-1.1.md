# Spike 1.1: decision model forwarding through the router (macOS)

| Item | Value |
| --- | --- |
| llama.cpp build | b11941, commit 19ff817fb (`llama-server --version`: `version: 0.7.0-dev (build 11941, commit 19ff817fb)`) |
| Binary | `<scratch>/llama-b11941/mac/llama-b11941/llama-server` (official macOS arm64 asset, SHA-256 checked earlier) |
| Date | 2026-11-06 |
| Machine | `sysctl hw.model` = Mac17,9, `hw.memsize` = 68719476736 bytes (64 GiB), Apple M5 Pro, macOS 27.2 |
| Raw record | `<scratch>/spikes/mac/out/spike-1.1.json` |
| Script | `<scratch>/spikes/mac/spike_1_1.py` (helpers in `common.py`) |
| Run command | `cd <worktree> && uv run --no-sync python <scratch>/spikes/mac/spike_1_1.py` |

Paths: `<scratch>` is the session scratchpad. `<worktree>` is the `omrs-feat-one-llamacpp-router` worktree. `~` is the real home folder (model files only).

## Verdict

**D10: outcome A.** The b11941 router forwards `POST /v1/systemone` to the Clef-Flash child by the `model` name (HTTP 200, reply `model` = `ggml-org/Clef-Flash-GGUF:Q8_0`). The OMRS projector smoke test through the router returned `None` (pass): right text P(yes) = 0.938747, wrong text P(yes) = 0.019527, margin **0.919220** against `SMOKE_MARGIN` 0.2 (`exp43-r4-2026-11-02`).

## Setup

Fresh router, preset with the Clef-Flash section only. No `[*]` section.

```ini
[ggml-org/Clef-Flash-GGUF:Q8_0]
model = ~/.cache/huggingface/hub/models--ggml-org--Clef-Flash-GGUF/snapshots/4a192915ef971886004b5b13294f2b4c7a7fc39d/Clef-Flash-Q8_0.gguf
mmproj = ~/Development/DATA/omrs/ocr-models/clef-flash/mmproj-Clef-Flash-Q8_0.gguf
parallel = 1

```
```text
<scratch>/llama-b11941/mac/llama-b11941/llama-server --models-preset <scratch>/spikes/mac/state/runtimes/router/models.ini --models-max 4 --models-memory-margin 8192 --host 127.0.0.1 --port 18431
```
Started as `process.py` does (new session, stdin `/dev/null`, log file, minimal environment, scratch `HOME`). `/health` 200 after 0.112 s.

OMRS code used, imported from the worktree venv (`uv run --no-sync`), not copied:

- `omrs.core.providers.decision.llamacpp.build_request(*, address, model, question, text, image, key, hosted)` with `address = http://127.0.0.1:<port>` (the router), `model = "ggml-org/Clef-Flash-GGUF:Q8_0"`, `key = None`, `hosted = False`.
- `omrs.core.providers.decision.llamacpp.read_reply(reply)` to parse P(yes).
- `omrs.core.providers.decision.checks.run_smoke_test(ask)` with `smoke_image()` (5033 bytes PNG, SHA-256 `964e039281de3f0860b24ab631f7dbcf09e08e369f213476b83a2dd582afef17`), `SMOKE_QUESTION`, `SMOKE_RIGHT_TEXT`, `SMOKE_WRONG_TEXT`.

The `ask` function posts the built request to the router and returns `read_reply(body)` on HTTP 200, else `None`.

## 1. Load

`POST /models/load` `{"model": "ggml-org/Clef-Flash-GGUF:Q8_0"}` -> 200 `{"success": true}` in 0.328 s. Time to `loaded`: **3.487 s** (warm page cache; the model file is 8.99 GiB).

`status.args` holds `--model` with the model path and `--mmproj` with the projector path: **True**. `--parallel 1` present: **True**.

```json
[
  "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
  "--host",
  "127.0.0.1",
  "--log-colors",
  "off",
  "--port",
  "54299",
  "--alias",
  "ggml-org/Clef-Flash-GGUF:Q8_0",
  "--model",
  "~/.cache/huggingface/hub/models--ggml-org--Clef-Flash-GGUF/snapshots/4a192915ef971886004b5b13294f2b4c7a7fc39d/Clef-Flash-Q8_0.gguf",
  "--mmproj",
  "~/Development/DATA/omrs/ocr-models/clef-flash/mmproj-Clef-Flash-Q8_0.gguf",
  "--parallel",
  "1"
]
```

`architecture` reported for the loaded model: `{"input_modalities": ["text", "image", "video"], "output_modalities": ["decisions"]}`.

Child process: pid 42593, pgid 42591, RSS 10119072 KiB, command `<scratch>/llama-b11941/mac/llama-b11941/llama-server --host 127.0.0.1 --log-colors off --port 54299 --alias ggml-org/Clef-Flash-GGUF:Q8_0 --model ~/.cache/huggingface/hub/models--ggml-org--Clef-Flash-GGUF/snapshots/4a192915ef971886004b5b13294f2b4c7a7fc39d/Clef-Flash-Q8_0.gguf --mmproj ~/Development/DATA/omrs/ocr-models/clef-flash/mmproj-Clef-Flash-Q8_0.gguf --parallel 1`.

Status snapshots while loading:

t = 0.0 s:

```json
{
  "id": "ggml-org/Clef-Flash-GGUF:Q8_0",
  "aliases": [],
  "tags": [],
  "object": "model",
  "owned_by": "llamacpp",
  "created": 1793983114,
  "status": {
    "value": "loading",
    "args": [
      "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
      "--host",
      "127.0.0.1",
      "--log-colors",
      "off",
      "--port",
      "54299",
      "--alias",
      "ggml-org/Clef-Flash-GGUF:Q8_0",
      "--model",
      "~/.cache/huggingface/hub/models--ggml-org--Clef-Flash-GGUF/snapshots/4a192915ef971886004b5b13294f2b4c7a7fc39d/Clef-Flash-Q8_0.gguf",
      "--mmproj",
      "~/Development/DATA/omrs/ocr-models/clef-flash/mmproj-Clef-Flash-Q8_0.gguf",
      "--parallel",
      "1"
    ],
    "preset": "[ggml-org/Clef-Flash-GGUF:Q8_0]\nlog-colors = off\nmodel = ~/.cache/huggingface/hub/models--ggml-org--Clef-Flash-GGUF/snapshots/4a192915ef971886004b5b13294f2b4c7a7fc39d/Clef-Flash-Q8_0.gguf\nmmproj = ~/Development/DATA/omrs/ocr-models/clef-flash/mmproj-Clef-Flash-Q8_0.gguf\nparallel = 1\n\n"
  },
  "architecture": {
    "input_modalities": [
      "text",
      "image"
    ],
    "output_modalities": [
      "decisions"
    ]
  },
  "source": "preset",
  "can_remove": false,
  "context_length": 262144,
  "memory": {
    "status": "measured",
    "min": {
      "n_ctx": 4096,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 8565579840,
          "context": 0,
          "compute": 162285632,
          "total": 55662788608,
          "free": 55662329856
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 1080700928,
          "context": 0,
          "compute": 68202752
        }
      ]
    },
    "max": {
      "n_ctx": 262144,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 8565579840,
          "context": 0,
          "compute": 162285632,
          "total": 55662788608,
          "free": 55662329856
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 1080700928,
          "context": 0,
          "compute": 68202752
        }
      ]
    },
    "effective": null
  }
}
```
t = 3.159 s:

```json
{
  "id": "ggml-org/Clef-Flash-GGUF:Q8_0",
  "aliases": [],
  "tags": [],
  "object": "model",
  "owned_by": "llamacpp",
  "created": 1793983117,
  "status": {
    "value": "loaded",
    "args": [
      "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
      "--host",
      "127.0.0.1",
      "--log-colors",
      "off",
      "--port",
      "54299",
      "--alias",
      "ggml-org/Clef-Flash-GGUF:Q8_0",
      "--model",
      "~/.cache/huggingface/hub/models--ggml-org--Clef-Flash-GGUF/snapshots/4a192915ef971886004b5b13294f2b4c7a7fc39d/Clef-Flash-Q8_0.gguf",
      "--mmproj",
      "~/Development/DATA/omrs/ocr-models/clef-flash/mmproj-Clef-Flash-Q8_0.gguf",
      "--parallel",
      "1"
    ],
    "preset": "[ggml-org/Clef-Flash-GGUF:Q8_0]\nlog-colors = off\nmodel = ~/.cache/huggingface/hub/models--ggml-org--Clef-Flash-GGUF/snapshots/4a192915ef971886004b5b13294f2b4c7a7fc39d/Clef-Flash-Q8_0.gguf\nmmproj = ~/Development/DATA/omrs/ocr-models/clef-flash/mmproj-Clef-Flash-Q8_0.gguf\nparallel = 1\n\n"
  },
  "architecture": {
    "input_modalities": [
      "text",
      "image",
      "video"
    ],
    "output_modalities": [
      "decisions"
    ]
  },
  "source": "preset",
  "can_remove": false,
  "context_length": 262144,
  "memory": {
    "status": "measured",
    "min": {
      "n_ctx": 4096,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 8565579840,
          "context": 0,
          "compute": 162285632,
          "total": 55662788608,
          "free": 55662329856
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 1080700928,
          "context": 0,
          "compute": 68202752
        }
      ]
    },
    "max": {
      "n_ctx": 262144,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 8565579840,
          "context": 0,
          "compute": 162285632,
          "total": 55662788608,
          "free": 55662329856
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 1080700928,
          "context": 0,
          "compute": 68202752
        }
      ]
    },
    "effective": {
      "n_ctx": 262144,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 8565579792,
          "context": 0,
          "compute": 162285632,
          "total": 55662788608,
          "free": 46266220544
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 1080700928,
          "context": 0,
          "compute": 34101376
        }
      ]
    }
  },
  "meta": {
    "vocab_type": 2,
    "n_vocab": 248320,
    "n_ctx": 262144,
    "n_ctx_train": 262144,
    "n_embd": 4096,
    "n_params": 9075566084,
    "size": 9646280720,
    "ftype": "Q8_0"
  }
}
```

Full `GET /v1/models` with the model loaded (raw):

`GET /v1/models` -> **200** in 0.0 s

Response body:

```json
{
  "data": [
    {
      "id": "ggml-org/Clef-Flash-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793983117,
      "status": {
        "value": "loaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--port",
          "54299",
          "--alias",
          "ggml-org/Clef-Flash-GGUF:Q8_0",
          "--model",
          "~/.cache/huggingface/hub/models--ggml-org--Clef-Flash-GGUF/snapshots/4a192915ef971886004b5b13294f2b4c7a7fc39d/Clef-Flash-Q8_0.gguf",
          "--mmproj",
          "~/Development/DATA/omrs/ocr-models/clef-flash/mmproj-Clef-Flash-Q8_0.gguf",
          "--parallel",
          "1"
        ],
        "preset": "[ggml-org/Clef-Flash-GGUF:Q8_0]\nlog-colors = off\nmodel = ~/.cache/huggingface/hub/models--ggml-org--Clef-Flash-GGUF/snapshots/4a192915ef971886004b5b13294f2b4c7a7fc39d/Clef-Flash-Q8_0.gguf\nmmproj = ~/Development/DATA/omrs/ocr-models/clef-flash/mmproj-Clef-Flash-Q8_0.gguf\nparallel = 1\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text",
          "image",
          "video"
        ],
        "output_modalities": [
          "decisions"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 262144,
      "memory": {
        "status": "measured",
        "min": {
          "n_ctx": 4096,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 8565579840,
              "context": 0,
              "compute": 162285632,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 1080700928,
              "context": 0,
              "compute": 68202752
            }
          ]
        },
        "max": {
          "n_ctx": 262144,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 8565579840,
              "context": 0,
              "compute": 162285632,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 1080700928,
              "context": 0,
              "compute": 68202752
            }
          ]
        },
        "effective": {
          "n_ctx": 262144,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 8565579792,
              "context": 0,
              "compute": 162285632,
              "total": 55662788608,
              "free": 46266220544
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 1080700928,
              "context": 0,
              "compute": 34101376
            }
          ]
        }
      },
      "meta": {
        "vocab_type": 2,
        "n_vocab": 248320,
        "n_ctx": 262144,
        "n_ctx_train": 262144,
        "n_embd": 4096,
        "n_params": 9075566084,
        "size": 9646280720,
        "ftype": "Q8_0"
      }
    }
  ],
  "object": "list"
}
```

## 2. One `POST /v1/systemone` through the router

Built with `build_request` (right smoke text and smoke image). P(yes) from `read_reply`: **0.9387470626107116**. Time **0.669 s** (first request after load).

`POST http://127.0.0.1:<port>/v1/systemone` -> **200** in 0.669 s

Headers: `{"Content-Type": "application/json"}`

Request body (base64 image cut short):

```json
{
  "model": "ggml-org/Clef-Flash-GGUF:Q8_0",
  "state": {
    "text": "Harbour weather notes\nMonday: light rain in the morning, dry later.\nTuesday: sunny spells and a gentle breeze.\nWednesday: cloudy with showers near the coast.\nThursday: strong wind, boats stay in the harbour."
  },
  "images": [
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAABEwAAAJsAQAAAA...<6734 chars in all>"
  ],
  "questions": {
    "fidelity": {
      "type": "noul",
      "instructions": "Does the text match the text written or printed on the page image?"
    }
  }
}
```

Response body:

```json
{
  "model": "ggml-org/Clef-Flash-GGUF:Q8_0",
  "answers": {
    "fidelity": {
      "type": "noul",
      "noul": 0.9387470626107116
    }
  },
  "usage": {
    "input_tokens": 457,
    "output_tokens": 0
  }
}
```

## 3. Projector smoke test through the router

`run_smoke_test(ask)` return value: **`None`** (`None` means pass; failure would be `"projector-not-loaded"`). Total 0.94 s for two requests.

| Text | P(yes) | Time |
| --- | --- | --- |
| Right (`SMOKE_RIGHT_TEXT`) | 0.9387470626107116 | 0.472 s |
| Wrong (`SMOKE_WRONG_TEXT`) | 0.019527447122082275 | 0.468 s |
| Margin (right minus wrong) | 0.91922 | needs at least 0.2 |

Raw exchanges:

`POST http://127.0.0.1:<port>/v1/systemone` -> **200** in 0.472 s

Headers: `{"Content-Type": "application/json"}`

Request body (base64 image cut short):

```json
{
  "model": "ggml-org/Clef-Flash-GGUF:Q8_0",
  "state": {
    "text": "Harbour weather notes\nMonday: light rain in the morning, dry later.\nTuesday: sunny spells and a gentle breeze.\nWednesday: cloudy with showers near the coast.\nThursday: strong wind, boats stay in the harbour."
  },
  "images": [
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAABEwAAAJsAQAAAA...<6734 chars in all>"
  ],
  "questions": {
    "fidelity": {
      "type": "noul",
      "instructions": "Does the text match the text written or printed on the page image?"
    }
  }
}
```

Response body:

```json
{
  "model": "ggml-org/Clef-Flash-GGUF:Q8_0",
  "answers": {
    "fidelity": {
      "type": "noul",
      "noul": 0.9387470626107116
    }
  },
  "usage": {
    "input_tokens": 457,
    "output_tokens": 0
  }
}
```

`POST http://127.0.0.1:<port>/v1/systemone` -> **200** in 0.468 s

Headers: `{"Content-Type": "application/json"}`

Request body (base64 image cut short):

```json
{
  "model": "ggml-org/Clef-Flash-GGUF:Q8_0",
  "state": {
    "text": "Garden supply order 4417\nThree bags of compost and two spades.\nOne wooden ladder, five metres long.\nDelivery to the side gate after noon.\nTotal due on arrival: fifty-eight pounds."
  },
  "images": [
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAABEwAAAJsAQAAAA...<6734 chars in all>"
  ],
  "questions": {
    "fidelity": {
      "type": "noul",
      "instructions": "Does the text match the text written or printed on the page image?"
    }
  }
}
```

Response body:

```json
{
  "model": "ggml-org/Clef-Flash-GGUF:Q8_0",
  "answers": {
    "fidelity": {
      "type": "noul",
      "noul": 0.019527447122082275
    }
  },
  "usage": {
    "input_tokens": 456,
    "output_tokens": 0
  }
}
```


## 4. Unknown or missing model

`POST /v1/systemone` naming an unknown model (no image):

`POST http://127.0.0.1:<port>/v1/systemone` -> **400** in 0.0 s

Headers: `{"Content-Type": "application/json"}`

Request body (base64 image cut short):

```json
{
  "model": "no-such/model:Q8_0",
  "state": {
    "text": "x"
  },
  "questions": {
    "fidelity": {
      "type": "noul",
      "instructions": "Does the text match the text written or printed on the page image?"
    }
  }
}
```

Response body:

```json
{
  "error": {
    "code": 400,
    "message": "model 'no-such/model:Q8_0' not found",
    "type": "invalid_request_error"
  }
}
```

`POST /v1/systemone` with no `model` field:

`POST http://127.0.0.1:<port>/v1/systemone` -> **400** in 0.0 s

Headers: `{"Content-Type": "application/json"}`

Request body (base64 image cut short):

```json
{
  "state": {
    "text": "x"
  },
  "questions": {
    "fidelity": {
      "type": "noul",
      "instructions": "Does the text match the text written or printed on the page image?"
    }
  }
}
```

Response body:

```json
{
  "error": {
    "code": 400,
    "message": "model name is missing from the request",
    "type": "invalid_request_error"
  }
}
```

Both are refused by the router before any child is involved. The message for an unknown name matches the one for `/v1/embeddings` in spike 1.2.

## 5. Stop

SIGTERM to the router group (pgid 42591): router gone in {'42591': 0.177} s, no SIGKILL. Scan for leftover processes of the spike binary: `[]`.

## Verdict (repeated)

**D10 outcome A:** the router forwards `/v1/systemone` by `model`, the projector is loaded through the preset `mmproj` key (`--mmproj` in `status.args`), and the OMRS smoke test passes with margin 0.919 (needs 0.2).
