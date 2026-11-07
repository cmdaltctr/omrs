# Spike 1.2: router load, unload and reload (macOS)

| Item | Value |
| --- | --- |
| llama.cpp build | b11941, commit 19ff817fb (`llama-server --version`: `version: 0.7.0-dev (build 11941, commit 19ff817fb)`) |
| Binary | `<scratch>/llama-b11941/mac/llama-b11941/llama-server` (official macOS arm64 asset, SHA-256 checked earlier) |
| Date | 2026-11-06 |
| Machine | `sysctl hw.model` = Mac17,9, `hw.memsize` = 68719476736 bytes (64 GiB), Apple M5 Pro, macOS 27.2 |
| Raw record | `<scratch>/spikes/mac/out/spike-1.2.json` |
| Script | `<scratch>/spikes/mac/spike_1_2.py` (helpers in `common.py`) |
| Run command | `cd <worktree> && uv run --no-sync python <scratch>/spikes/mac/spike_1_2.py` |

Paths: `<scratch>` is the session scratchpad. `<worktree>` is the `omrs-feat-one-llamacpp-router` worktree. `~` is the real home folder (model files only).

## Verdict

**D7 is met on b11941: yes.** A preset edit of one section followed by `GET /models?reload=1` unloaded only the edited model (`Qwen/Qwen3-4B-GGUF:Q8_0`). The embedding model stayed `loaded` with the same child pid (36805 before, 36805 after). The next load of the edited model used the new value (`--ctx-size 4096` in `status.args`). A reload with an identical file, or with sections reordered and a comment added, unloaded nothing. Removing a section unloaded and dropped that model only. Adding a section listed it as `unloaded` and spawned no model process.

## Setup

Preset file `<scratch>/spikes/mac/state/runtimes/router/models.ini`, written by temporary file and rename. No `[*]` section.
```ini
[Qwen/Qwen3-Embedding-4B-GGUF:Q8_0]
model = ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf
embeddings = true
pooling = last
ctx-size = 8192
batch-size = 8192
ubatch-size = 8192
parallel = 1

[Qwen/Qwen3-4B-GGUF:Q8_0]
model = ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf
ctx-size = 8192

```
Router argument list (started with `start_new_session=True`, stdin `/dev/null`, output to `server.log`, child environment `PATH`, `HOME` (scratch), `LANG`, `TMPDIR` (scratch), as in `process.py`):

```text
<scratch>/llama-b11941/mac/llama-b11941/llama-server --models-preset <scratch>/spikes/mac/state/runtimes/router/models.ini --models-max 4 --models-memory-margin 8192 --host 127.0.0.1 --port 18431
```
Scratch `HOME` = `<scratch>/spikes/mac/home` (empty). `OMRS_STATE_DIR` and `OMRS_CONFIG_DIR` were not read by anything here; the preset and log live under `<scratch>/spikes/mac/state/runtimes/router/`.

## 1. Start, `/health` and the model list

- Launch to first `GET /health` 200: **0.117 s** (2 polls). Body `{"status": "ok"}`.
- `/health` answers 200 with no model loaded: **yes**.
- `GET /v1/models` with scratch `HOME` lists **only the two preset models** (`"source": "preset"`). No cache model appears, because the scratch `HOME` has no Hugging Face cache.
- From the b11941 source (read only, `gh api repos/ggml-org/llama.cpp/contents/...?ref=b11941`): `server_models::load_models()` always calls `ctx_preset.load_from_cache()` (`tools/server/server-models.cpp` line 730), which lists every model in the Hugging Face cache as a preset with `LLAMA_ARG_HF_REPO`. The cache folder is the first set of `LLAMA_CACHE`, `HF_HUB_CACHE`, `HUGGINGFACE_HUB_CACHE`, `HF_HOME/hub`, `XDG_CACHE_HOME/huggingface/hub`, `HOME/.cache/huggingface/hub`, then the passwd home (`common/hf-cache.cpp` lines 34 to 62). A preset section with the same name wins over a cache entry (`final_presets` order: cache, `--models-dir`, preset). A cache entry is hidden only when a preset sets `dedup-cache-models` and resolves the same HF file (lines 780 to 815). **So with the real `HOME`, the router would list, and autoload on request, every model in `~/.cache/huggingface/hub`.** There is no flag to turn the cache source off. Pointing `LLAMA_CACHE` at an empty folder would hide it (source reading only, not run).
- `/v1/models` carries a `memory` field per model only when `--models-memory-margin` is above 0 (`server_models_sched::memory_enabled()`, `server-models-sched.cpp` line 312). It was present in this run (margin 8192).

`GET /props` on the router:

`GET /props` -> **200** in 0.0 s

Response body:

```json
{
  "role": "router",
  "max_instances": 4,
  "models_autoload": true,
  "model_alias": "llama-server",
  "model_path": "none",
  "default_generation_settings": {
    "params": null,
    "n_ctx": 0
  },
  "ui_settings": {},
  "build_info": "b11941-19ff817fb",
  "cors_proxy_enabled": false
}
```

`GET /v1/models` before any load (raw):

`GET /v1/models` -> **200** in 0.001 s

Response body:

```json
{
  "data": [
    {
      "id": "Qwen/Qwen3-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982756,
      "status": {
        "value": "unloaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--port",
          "0",
          "--alias",
          "Qwen/Qwen3-4B-GGUF:Q8_0",
          "--ctx-size",
          "8192",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf"
        ],
        "preset": "[Qwen/Qwen3-4B-GGUF:Q8_0]\nlog-colors = off\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "measuring",
        "min": null,
        "max": null,
        "effective": null
      }
    },
    {
      "id": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982756,
      "status": {
        "value": "unloaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--embeddings",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--pooling",
          "last",
          "--port",
          "0",
          "--alias",
          "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
          "--batch-size",
          "8192",
          "--ctx-size",
          "8192",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf",
          "--parallel",
          "1",
          "--ubatch-size",
          "8192"
        ],
        "preset": "[Qwen/Qwen3-Embedding-4B-GGUF:Q8_0]\nembeddings = true\nlog-colors = off\npooling = last\nbatch-size = 8192\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf\nparallel = 1\nubatch-size = 8192\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "unmeasured",
        "min": null,
        "max": null,
        "effective": null
      }
    }
  ],
  "object": "list"
}
```

`GET /models` (no `/v1`) before any load returns the same shape:

Status 200, ids ['Qwen/Qwen3-4B-GGUF:Q8_0', 'Qwen/Qwen3-Embedding-4B-GGUF:Q8_0'].

## 2. Status values and the `memory` field

Status values seen in `status.value`: `unloaded`, `loading`, `loaded`. No `failed` flag was set in this run. `status.args` is the full child argument list, rendered even while `unloaded`. `status.preset` is the section as INI text with `host`, `port`, `alias`, `tags` removed and `log-colors = off` added.

The `memory` object has `status` (`unmeasured`, `measuring`, `measured`), `min`, `max` and `effective`. `min` and `max` appear after measuring; `effective` appears once the model is loaded. Each holds `n_ctx` and a `devices` list with `kind` (`device` or `host`), `name` (`MTL0`, `Host`), `model`, `context`, `compute` (bytes), and for a device `total` and `free` (bytes).

At start, both models were `unloaded` with memory status `measuring` (Qwen/Qwen3-4B-GGUF:Q8_0) and `unmeasured` (Qwen/Qwen3-Embedding-4B-GGUF:Q8_0). The router measures each model with a short child process run with `--offline` (log: `measure_next: measuring memory for model name=...`). See the surprise in section 3.

Snapshots while loading and after load, embedding model (raw `/v1/models` entry for the model at each change):

t = 0.001 s after the load POST returned:

```json
{
  "id": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
  "aliases": [],
  "tags": [],
  "object": "model",
  "owned_by": "llamacpp",
  "created": 1793982760,
  "status": {
    "value": "loading",
    "args": [
      "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
      "--embeddings",
      "--host",
      "127.0.0.1",
      "--log-colors",
      "off",
      "--pooling",
      "last",
      "--port",
      "52703",
      "--alias",
      "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
      "--batch-size",
      "8192",
      "--ctx-size",
      "8192",
      "--model",
      "~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf",
      "--parallel",
      "1",
      "--ubatch-size",
      "8192"
    ],
    "preset": "[Qwen/Qwen3-Embedding-4B-GGUF:Q8_0]\nembeddings = true\nlog-colors = off\npooling = last\nbatch-size = 8192\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf\nparallel = 1\nubatch-size = 8192\n\n"
  },
  "architecture": {
    "input_modalities": [
      "text"
    ],
    "output_modalities": [
      "text"
    ]
  },
  "source": "preset",
  "can_remove": false,
  "context_length": 40960,
  "memory": {
    "status": "measured",
    "min": {
      "n_ctx": 8192,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 4273711264,
          "context": 1207959552,
          "compute": 1426325536,
          "total": 55662788608,
          "free": 55662329856
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 412528800,
          "context": 0,
          "compute": 940179520
        }
      ]
    },
    "max": {
      "n_ctx": 8192,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 4273711264,
          "context": 1207959552,
          "compute": 1426325536,
          "total": 55662788608,
          "free": 55662329856
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 412528800,
          "context": 0,
          "compute": 940179520
        }
      ]
    },
    "effective": null
  }
}
```
t = 1.77 s after the load POST returned:

```json
{
  "id": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
  "aliases": [],
  "tags": [],
  "object": "model",
  "owned_by": "llamacpp",
  "created": 1793982761,
  "status": {
    "value": "loaded",
    "args": [
      "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
      "--embeddings",
      "--host",
      "127.0.0.1",
      "--log-colors",
      "off",
      "--pooling",
      "last",
      "--port",
      "52703",
      "--alias",
      "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
      "--batch-size",
      "8192",
      "--ctx-size",
      "8192",
      "--model",
      "~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf",
      "--parallel",
      "1",
      "--ubatch-size",
      "8192"
    ],
    "preset": "[Qwen/Qwen3-Embedding-4B-GGUF:Q8_0]\nembeddings = true\nlog-colors = off\npooling = last\nbatch-size = 8192\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf\nparallel = 1\nubatch-size = 8192\n\n"
  },
  "architecture": {
    "input_modalities": [
      "text"
    ],
    "output_modalities": [
      "text"
    ]
  },
  "source": "preset",
  "can_remove": false,
  "context_length": 40960,
  "memory": {
    "status": "measured",
    "min": {
      "n_ctx": 8192,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 4273711264,
          "context": 1207959552,
          "compute": 1426325536,
          "total": 55662788608,
          "free": 55662329856
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 412528800,
          "context": 0,
          "compute": 940179520
        }
      ]
    },
    "max": {
      "n_ctx": 8192,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 4273711264,
          "context": 1207959552,
          "compute": 1426325536,
          "total": 55662788608,
          "free": 55662329856
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 412528800,
          "context": 0,
          "compute": 940179520
        }
      ]
    },
    "effective": {
      "n_ctx": 8192,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 4273711264,
          "context": 1207959552,
          "compute": 1426325536,
          "total": 55662788608,
          "free": 48754049024
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 412528800,
          "context": 0,
          "compute": 470089760
        }
      ]
    }
  },
  "meta": {
    "vocab_type": 2,
    "n_vocab": 151665,
    "n_ctx": 8192,
    "n_ctx_train": 40960,
    "n_embd": 2560,
    "n_params": 4021774336,
    "size": 4273711264,
    "ftype": "Q8_0"
  }
}
```

Snapshots while loading and after load, text model:

t = 0.0 s after the load POST returned:

```json
{
  "id": "Qwen/Qwen3-4B-GGUF:Q8_0",
  "aliases": [],
  "tags": [],
  "object": "model",
  "owned_by": "llamacpp",
  "created": 1793982761,
  "status": {
    "value": "loading",
    "args": [
      "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
      "--host",
      "127.0.0.1",
      "--log-colors",
      "off",
      "--port",
      "52745",
      "--alias",
      "Qwen/Qwen3-4B-GGUF:Q8_0",
      "--ctx-size",
      "8192",
      "--model",
      "~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf"
    ],
    "preset": "[Qwen/Qwen3-4B-GGUF:Q8_0]\nlog-colors = off\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf\n\n"
  },
  "architecture": {
    "input_modalities": [
      "text"
    ],
    "output_modalities": [
      "text"
    ]
  },
  "source": "preset",
  "can_remove": false,
  "context_length": 40960,
  "memory": {
    "status": "measured",
    "min": {
      "n_ctx": 8192,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 4274448384,
          "context": 1207959552,
          "compute": 340541440,
          "total": 55662788608,
          "free": 55662329856
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 413265920,
          "context": 0,
          "compute": 58761216
        }
      ]
    },
    "max": {
      "n_ctx": 8192,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 4274448384,
          "context": 1207959552,
          "compute": 340541440,
          "total": 55662788608,
          "free": 55662329856
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 413265920,
          "context": 0,
          "compute": 58761216
        }
      ]
    },
    "effective": null
  }
}
```
t = 4.465 s after the load POST returned:

```json
{
  "id": "Qwen/Qwen3-4B-GGUF:Q8_0",
  "aliases": [],
  "tags": [],
  "object": "model",
  "owned_by": "llamacpp",
  "created": 1793982766,
  "status": {
    "value": "loaded",
    "args": [
      "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
      "--host",
      "127.0.0.1",
      "--log-colors",
      "off",
      "--port",
      "52745",
      "--alias",
      "Qwen/Qwen3-4B-GGUF:Q8_0",
      "--ctx-size",
      "8192",
      "--model",
      "~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf"
    ],
    "preset": "[Qwen/Qwen3-4B-GGUF:Q8_0]\nlog-colors = off\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf\n\n"
  },
  "architecture": {
    "input_modalities": [
      "text"
    ],
    "output_modalities": [
      "text"
    ]
  },
  "source": "preset",
  "can_remove": false,
  "context_length": 40960,
  "memory": {
    "status": "measured",
    "min": {
      "n_ctx": 8192,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 4274448384,
          "context": 1207959552,
          "compute": 340541440,
          "total": 55662788608,
          "free": 55662329856
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 413265920,
          "context": 0,
          "compute": 58761216
        }
      ]
    },
    "max": {
      "n_ctx": 8192,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 4274448384,
          "context": 1207959552,
          "compute": 340541440,
          "total": 55662788608,
          "free": 55662329856
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 413265920,
          "context": 0,
          "compute": 58761216
        }
      ]
    },
    "effective": {
      "n_ctx": 8192,
      "devices": [
        {
          "kind": "device",
          "name": "MTL0",
          "model": 4274448384,
          "context": 1207959552,
          "compute": 107304992,
          "total": 55662788608,
          "free": 50072322048
        },
        {
          "kind": "host",
          "name": "Host",
          "model": 413265920,
          "context": 0,
          "compute": 29378592
        }
      ]
    }
  },
  "meta": {
    "vocab_type": 2,
    "n_vocab": 151936,
    "n_ctx": 8192,
    "n_ctx_train": 40960,
    "n_embd": 2560,
    "n_params": 4022468096,
    "size": 4274448384,
    "ftype": "Q8_0"
  }
}
```

Full `GET /v1/models` after both loads (raw):

`GET /v1/models` -> **200** in 0.0 s

Response body:

```json
{
  "data": [
    {
      "id": "Qwen/Qwen3-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982766,
      "status": {
        "value": "loaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--port",
          "52745",
          "--alias",
          "Qwen/Qwen3-4B-GGUF:Q8_0",
          "--ctx-size",
          "8192",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf"
        ],
        "preset": "[Qwen/Qwen3-4B-GGUF:Q8_0]\nlog-colors = off\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "measured",
        "min": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4274448384,
              "context": 1207959552,
              "compute": 340541440,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 413265920,
              "context": 0,
              "compute": 58761216
            }
          ]
        },
        "max": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4274448384,
              "context": 1207959552,
              "compute": 340541440,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 413265920,
              "context": 0,
              "compute": 58761216
            }
          ]
        },
        "effective": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4274448384,
              "context": 1207959552,
              "compute": 107304992,
              "total": 55662788608,
              "free": 50072322048
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 413265920,
              "context": 0,
              "compute": 29378592
            }
          ]
        }
      },
      "meta": {
        "vocab_type": 2,
        "n_vocab": 151936,
        "n_ctx": 8192,
        "n_ctx_train": 40960,
        "n_embd": 2560,
        "n_params": 4022468096,
        "size": 4274448384,
        "ftype": "Q8_0"
      }
    },
    {
      "id": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982766,
      "status": {
        "value": "loaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--embeddings",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--pooling",
          "last",
          "--port",
          "52703",
          "--alias",
          "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
          "--batch-size",
          "8192",
          "--ctx-size",
          "8192",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf",
          "--parallel",
          "1",
          "--ubatch-size",
          "8192"
        ],
        "preset": "[Qwen/Qwen3-Embedding-4B-GGUF:Q8_0]\nembeddings = true\nlog-colors = off\npooling = last\nbatch-size = 8192\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf\nparallel = 1\nubatch-size = 8192\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "measured",
        "min": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 940179520
            }
          ]
        },
        "max": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 940179520
            }
          ]
        },
        "effective": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 48754049024
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 470089760
            }
          ]
        }
      },
      "meta": {
        "vocab_type": 2,
        "n_vocab": 151665,
        "n_ctx": 8192,
        "n_ctx_train": 40960,
        "n_embd": 2560,
        "n_params": 4021774336,
        "size": 4273711264,
        "ftype": "Q8_0"
      }
    }
  ],
  "object": "list"
}
```

Full `GET /v1/models` after unloading the text model (raw):

`GET /v1/models` -> **200** in 0.0 s

Response body:

```json
{
  "data": [
    {
      "id": "Qwen/Qwen3-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982766,
      "status": {
        "value": "unloaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--port",
          "52745",
          "--alias",
          "Qwen/Qwen3-4B-GGUF:Q8_0",
          "--ctx-size",
          "8192",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf"
        ],
        "preset": "[Qwen/Qwen3-4B-GGUF:Q8_0]\nlog-colors = off\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "measured",
        "min": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4274448384,
              "context": 1207959552,
              "compute": 340541440,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 413265920,
              "context": 0,
              "compute": 58761216
            }
          ]
        },
        "max": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4274448384,
              "context": 1207959552,
              "compute": 340541440,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 413265920,
              "context": 0,
              "compute": 58761216
            }
          ]
        },
        "effective": null
      }
    },
    {
      "id": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982766,
      "status": {
        "value": "loaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--embeddings",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--pooling",
          "last",
          "--port",
          "52703",
          "--alias",
          "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
          "--batch-size",
          "8192",
          "--ctx-size",
          "8192",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf",
          "--parallel",
          "1",
          "--ubatch-size",
          "8192"
        ],
        "preset": "[Qwen/Qwen3-Embedding-4B-GGUF:Q8_0]\nembeddings = true\nlog-colors = off\npooling = last\nbatch-size = 8192\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf\nparallel = 1\nubatch-size = 8192\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "measured",
        "min": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 940179520
            }
          ]
        },
        "max": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 940179520
            }
          ]
        },
        "effective": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 48754049024
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 470089760
            }
          ]
        }
      },
      "meta": {
        "vocab_type": 2,
        "n_vocab": 151665,
        "n_ctx": 8192,
        "n_ctx_train": 40960,
        "n_embd": 2560,
        "n_params": 4021774336,
        "size": 4273711264,
        "ftype": "Q8_0"
      }
    }
  ],
  "object": "list"
}
```

## 3. Load and unload

| Call | Status | Time | Body |
| --- | --- | --- | --- |
| `POST /models/load` `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` (first load) | 200 | 3.453 s for the POST, 5.223 s to `loaded` | `{"success": true}` |
| `POST /models/load` `Qwen/Qwen3-4B-GGUF:Q8_0` | 200 | 0.001 s for the POST, 4.466 s to `loaded` | `{"success": true}` |
| `POST /models/load` again for a loaded model | 400 | 0.0 s | `{"error": {"code": 400, "message": "model is already running", "type": "invalid_request_error"}}` |
| `POST /models/load` unknown name | 404 | 0.0 s | `{"error": {"message": "File Not Found", "type": "not_found_error", "code": 404}}` |
| `POST /models/unload` `Qwen/Qwen3-4B-GGUF:Q8_0` | 200 | 0.0 s for the POST, 0.108 s to `unloaded` | `{"success": true}` |
| `POST /models/unload` unknown name | 400 | 0.0 s | `{"error": {"code": 400, "message": "model is not found", "type": "invalid_request_error"}}` |
| `POST /models/unload` model not running | 400 | 0.0 s | `{"error": {"code": 400, "message": "model is not running", "type": "invalid_request_error"}}` |

Request bodies are `{"model": "<name>"}`. Load times are warm (model files in the page cache).

**Surprise 1: the first `POST /models/load` blocked 3.453 s.** At start the router measures every model's memory, one model at a time: router log `measure_next: measuring memory for model name=Qwen/Qwen3-4B-GGUF:Q8_0` at 0.092 s, its result at 3.292 s, then `measure_next ... name=Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` at 3.349 s and its result at 3.561 s. The embedding load POST arrived at about 0.1 s and logged `make_room: waiting for the memory measurement of model name=Qwen/Qwen3-Embedding-4B-GGUF:Q8_0`; the router spawned the embedding model at 3.561 s and only then answered the POST. So a load waits for its own model's measurement, which can queue behind other models' measurements. Later load POSTs returned in about 1 ms. A loader must not treat a slow `POST /models/load` as a failure; the design's 300 s load timeout covers it. The 3.2 s measurement of Qwen3-4B looks like a cold file read; it was 0.19 s after the reload.

**Surprise 2: measure children.** With a non-zero memory margin, the router spawns a short-lived child `llama-server ... --offline` per unmeasured model at start, after a reload that changes or adds a section. They share the router's process group, have the router binary path in the command line, and have RSS about 1 MB. All direct children right after the edit reload, then right after the add reload (`offline: true` marks a measure child; the other row is the loaded embedding model):

```json
[
  {
    "pid": 36805,
    "ppid": 36787,
    "pgid": 36787,
    "rss_kib": 5367920,
    "alias": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
    "offline": false
  },
  {
    "pid": 37039,
    "ppid": 36787,
    "pgid": 36787,
    "rss_kib": 1008,
    "alias": "Qwen/Qwen3-4B-GGUF:Q8_0",
    "offline": true
  },
  {
    "pid": 36805,
    "ppid": 36787,
    "pgid": 36787,
    "rss_kib": 5367920,
    "alias": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
    "offline": false
  },
  {
    "pid": 37067,
    "ppid": 36787,
    "pgid": 36787,
    "rss_kib": 1008,
    "alias": "Qwen/Qwen3-4B-GGUF:Q8_0",
    "offline": true
  }
]
```

**Unknown name on load gives 404 with message `File Not Found`**, while unknown names on unload and on a proxied POST give 400 with a message naming the model. Treat both as `model-not-listed`.

### Requests naming an unknown or unloaded model

- `POST /v1/embeddings` with an unknown model: 400, `{"error": {"code": 400, "message": "model 'no-such/model:Q8_0' not found", "type": "invalid_request_error"}}`.
- `POST /v1/chat/completions` with no `model` field: 400, `{"error": {"code": 400, "message": "model name is missing from the request", "type": "invalid_request_error"}}`.
- `--models-autoload` default: **enabled** (`llama-server --help`: "automatically load models (default: enabled)"; `GET /props` shows `"models_autoload": true`). A request can override it with the query parameter `?autoload=false` or `?autoload=true` (`is_autoload()` in `server-models.cpp`).
- `POST /v1/chat/completions?autoload=false` naming the unloaded text model: 400, `{"error": {"code": 400, "message": "model is not loaded", "type": "invalid_request_error"}}`.
- The same POST with the default (autoload on): **200 in 0.786 s**; the router loaded the model, then answered. Status after: `loaded`.
- `POST /v1/embeddings` naming the text model (loaded, no `--embeddings`): 501, `{"error": {"code": 501, "message": "This server does not support embeddings. Start it with `--embeddings`", "type": "not_supported_error"}}`. The router forwards by name; the child refuses.

## 4. Routing by `model`: one embedding and one chat request

Embedding: vector length **2560**, first request 0.103 s, second request 0.022 s.

`POST /v1/embeddings` -> **200** in 0.103 s

Request body:

```json
{
  "model": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
  "input": "The harbour stays closed in strong wind."
}
```

Response body:

```json
{
  "model": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
  "object": "list",
  "usage": {
    "prompt_tokens": 9,
    "total_tokens": 9
  },
  "data": [
    {
      "embedding": "<2560 floats, first 4: [-0.00017485486750956625, -0.04093626141548157, 0.02217918448150158, -0.01703106425702572]>",
      "index": 0,
      "object": "embedding"
    }
  ]
}
```

Chat (0.147 s):

`POST /v1/chat/completions` -> **200** in 0.147 s

Request body:

```json
{
  "model": "Qwen/Qwen3-4B-GGUF:Q8_0",
  "max_tokens": 32,
  "temperature": 0,
  "chat_template_kwargs": {
    "enable_thinking": false
  },
  "messages": [
    {
      "role": "user",
      "content": "Reply with one word: the colour of the sky on a clear day."
    }
  ]
}
```

Response body:

```json
{
  "choices": [
    {
      "finish_reason": "stop",
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Blue."
      }
    }
  ],
  "created": 1793982766,
  "model": "Qwen/Qwen3-4B-GGUF:Q8_0",
  "system_fingerprint": "b11941-19ff817fb",
  "object": "chat.completion",
  "usage": {
    "completion_tokens": 3,
    "prompt_tokens": 27,
    "total_tokens": 30,
    "prompt_tokens_details": {
      "cached_tokens": 0
    }
  },
  "id": "chatcmpl-CRMjbQDFjxyBtvSHejTrAi8R8R9x3Ek5",
  "timings": {
    "cache_n": 0,
    "prompt_n": 27,
    "prompt_ms": 108.666,
    "prompt_per_token_ms": 4.024666666666667,
    "prompt_per_second": 248.4677820109326,
    "predicted_n": 3,
    "predicted_ms": 35.643,
    "predicted_per_token_ms": 17.8215,
    "predicted_per_second": 56.111999551104006
  }
}
```

## 5. Reload rule

Both models loaded before the reload tests. Model processes (not measure children): embedding pid 36805, text pid 37034.

| Test | `GET /models?reload=1` | Status after | Embedding pid after | Notes |
| --- | --- | --- | --- | --- |
| Identical file rewritten | 200, 0.001 s | `{'Qwen/Qwen3-4B-GGUF:Q8_0': 'loaded', 'Qwen/Qwen3-Embedding-4B-GGUF:Q8_0': 'loaded'}` | 36805 | text pid 37034: nothing unloaded |
| Sections reordered, comment line added | 200, 0.001 s | `{'Qwen/Qwen3-4B-GGUF:Q8_0': 'loaded', 'Qwen/Qwen3-Embedding-4B-GGUF:Q8_0': 'loaded'}` | 36805 | text pid 37034: nothing unloaded (the router compares parsed options, not text) |
| Text section `ctx-size` 8192 to 4096 | 200, 0.126 s | `{'Qwen/Qwen3-4B-GGUF:Q8_0': 'unloaded', 'Qwen/Qwen3-Embedding-4B-GGUF:Q8_0': 'loaded'}` | 36805 | only the text model unloaded; a measure child for it ran |
| Load the edited model | `POST /models/load` 200, 0.642 s to `loaded` | `{'Qwen/Qwen3-4B-GGUF:Q8_0': 'loaded', 'Qwen/Qwen3-Embedding-4B-GGUF:Q8_0': 'loaded'}` | 36805 | text `status.args` `--ctx-size 4096`; embedding still `--ctx-size 8192`; new text pid 37064 |
| Text section removed | 200 | `{'Qwen/Qwen3-Embedding-4B-GGUF:Q8_0': 'loaded'}` | 36805 | text model unloaded and dropped from the list; a chat naming it then gives 400 `model 'Qwen/Qwen3-4B-GGUF:Q8_0' not found` |
| Text section added back | 200 | `{'Qwen/Qwen3-4B-GGUF:Q8_0': 'unloaded', 'Qwen/Qwen3-Embedding-4B-GGUF:Q8_0': 'loaded'}` | 36805 | listed as `unloaded`; no model process, one measure child |

The reload GET returns the normal model list after the reconcile ends. It waits for each unload to finish first (`cv.wait` in `load_models()`), so the response already shows the new state.

Router log lines for the edit and the removal:

```text
I srv   load_models: (reload) unloading model name=Qwen/Qwen3-4B-GGUF:Q8_0 (source updated or removed)
I srv        unload: stopping model instance name=Qwen/Qwen3-4B-GGUF:Q8_0
I srv           run: instance name=Qwen/Qwen3-4B-GGUF:Q8_0 exited with status 0
I srv  measure_next: measuring memory for model name=Qwen/Qwen3-4B-GGUF:Q8_0
...
I srv   load_models: (reload) removing model name=Qwen/Qwen3-4B-GGUF:Q8_0 (no longer in source)
```

Edited preset text:

```ini
[Qwen/Qwen3-Embedding-4B-GGUF:Q8_0]
model = ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf
embeddings = true
pooling = last
ctx-size = 8192
batch-size = 8192
ubatch-size = 8192
parallel = 1

[Qwen/Qwen3-4B-GGUF:Q8_0]
model = ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf
ctx-size = 4096

```

Raw reload response after the edit:

`GET /models?reload=1` -> **200** in 0.126 s

Response body:

```json
{
  "data": [
    {
      "id": "Qwen/Qwen3-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982767,
      "status": {
        "value": "unloaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--port",
          "52859",
          "--alias",
          "Qwen/Qwen3-4B-GGUF:Q8_0",
          "--ctx-size",
          "4096",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf"
        ],
        "preset": "[Qwen/Qwen3-4B-GGUF:Q8_0]\nlog-colors = off\nctx-size = 4096\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "measuring",
        "min": null,
        "max": null,
        "effective": null
      }
    },
    {
      "id": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982767,
      "status": {
        "value": "loaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--embeddings",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--pooling",
          "last",
          "--port",
          "52703",
          "--alias",
          "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
          "--batch-size",
          "8192",
          "--ctx-size",
          "8192",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf",
          "--parallel",
          "1",
          "--ubatch-size",
          "8192"
        ],
        "preset": "[Qwen/Qwen3-Embedding-4B-GGUF:Q8_0]\nembeddings = true\nlog-colors = off\npooling = last\nbatch-size = 8192\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf\nparallel = 1\nubatch-size = 8192\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "measured",
        "min": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 940179520
            }
          ]
        },
        "max": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 940179520
            }
          ]
        },
        "effective": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 48754049024
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 470089760
            }
          ]
        }
      },
      "meta": {
        "vocab_type": 2,
        "n_vocab": 151665,
        "n_ctx": 8192,
        "n_ctx_train": 40960,
        "n_embd": 2560,
        "n_params": 4021774336,
        "size": 4273711264,
        "ftype": "Q8_0"
      }
    }
  ],
  "object": "list"
}
```

Raw `GET /v1/models` after loading the edited model:

`GET /v1/models` -> **200** in 0.0 s

Response body:

```json
{
  "data": [
    {
      "id": "Qwen/Qwen3-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982768,
      "status": {
        "value": "loaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--port",
          "52868",
          "--alias",
          "Qwen/Qwen3-4B-GGUF:Q8_0",
          "--ctx-size",
          "4096",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf"
        ],
        "preset": "[Qwen/Qwen3-4B-GGUF:Q8_0]\nlog-colors = off\nctx-size = 4096\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "measured",
        "min": {
          "n_ctx": 4096,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4274448384,
              "context": 603979776,
              "compute": 336347136,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 413265920,
              "context": 0,
              "compute": 50372608
            }
          ]
        },
        "max": {
          "n_ctx": 4096,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4274448384,
              "context": 603979776,
              "compute": 336347136,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 413265920,
              "context": 0,
              "compute": 50372608
            }
          ]
        },
        "effective": {
          "n_ctx": 4096,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4274448384,
              "context": 603979776,
              "compute": 86329376,
              "total": 55662788608,
              "free": 50697273344
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 413265920,
              "context": 0,
              "compute": 25184288
            }
          ]
        }
      },
      "meta": {
        "vocab_type": 2,
        "n_vocab": 151936,
        "n_ctx": 4096,
        "n_ctx_train": 40960,
        "n_embd": 2560,
        "n_params": 4022468096,
        "size": 4274448384,
        "ftype": "Q8_0"
      }
    },
    {
      "id": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982768,
      "status": {
        "value": "loaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--embeddings",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--pooling",
          "last",
          "--port",
          "52703",
          "--alias",
          "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
          "--batch-size",
          "8192",
          "--ctx-size",
          "8192",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf",
          "--parallel",
          "1",
          "--ubatch-size",
          "8192"
        ],
        "preset": "[Qwen/Qwen3-Embedding-4B-GGUF:Q8_0]\nembeddings = true\nlog-colors = off\npooling = last\nbatch-size = 8192\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf\nparallel = 1\nubatch-size = 8192\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "measured",
        "min": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 940179520
            }
          ]
        },
        "max": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 940179520
            }
          ]
        },
        "effective": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 48754049024
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 470089760
            }
          ]
        }
      },
      "meta": {
        "vocab_type": 2,
        "n_vocab": 151665,
        "n_ctx": 8192,
        "n_ctx_train": 40960,
        "n_embd": 2560,
        "n_params": 4021774336,
        "size": 4273711264,
        "ftype": "Q8_0"
      }
    }
  ],
  "object": "list"
}
```

Raw reload response after removing the section:

`GET /models?reload=1` -> **200** in 0.101 s

Response body:

```json
{
  "data": [
    {
      "id": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982768,
      "status": {
        "value": "loaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--embeddings",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--pooling",
          "last",
          "--port",
          "52703",
          "--alias",
          "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
          "--batch-size",
          "8192",
          "--ctx-size",
          "8192",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf",
          "--parallel",
          "1",
          "--ubatch-size",
          "8192"
        ],
        "preset": "[Qwen/Qwen3-Embedding-4B-GGUF:Q8_0]\nembeddings = true\nlog-colors = off\npooling = last\nbatch-size = 8192\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf\nparallel = 1\nubatch-size = 8192\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "measured",
        "min": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 940179520
            }
          ]
        },
        "max": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 940179520
            }
          ]
        },
        "effective": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 48754049024
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 470089760
            }
          ]
        }
      },
      "meta": {
        "vocab_type": 2,
        "n_vocab": 151665,
        "n_ctx": 8192,
        "n_ctx_train": 40960,
        "n_embd": 2560,
        "n_params": 4021774336,
        "size": 4273711264,
        "ftype": "Q8_0"
      }
    }
  ],
  "object": "list"
}
```

Raw reload response after adding the section back:

`GET /models?reload=1` -> **200** in 0.019 s

Response body:

```json
{
  "data": [
    {
      "id": "Qwen/Qwen3-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982768,
      "status": {
        "value": "unloaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--port",
          "0",
          "--alias",
          "Qwen/Qwen3-4B-GGUF:Q8_0",
          "--ctx-size",
          "4096",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf"
        ],
        "preset": "[Qwen/Qwen3-4B-GGUF:Q8_0]\nlog-colors = off\nctx-size = 4096\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "measuring",
        "min": null,
        "max": null,
        "effective": null
      }
    },
    {
      "id": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
      "aliases": [],
      "tags": [],
      "object": "model",
      "owned_by": "llamacpp",
      "created": 1793982768,
      "status": {
        "value": "loaded",
        "args": [
          "<scratch>/llama-b11941/mac/llama-b11941/llama-server",
          "--embeddings",
          "--host",
          "127.0.0.1",
          "--log-colors",
          "off",
          "--pooling",
          "last",
          "--port",
          "52703",
          "--alias",
          "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
          "--batch-size",
          "8192",
          "--ctx-size",
          "8192",
          "--model",
          "~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf",
          "--parallel",
          "1",
          "--ubatch-size",
          "8192"
        ],
        "preset": "[Qwen/Qwen3-Embedding-4B-GGUF:Q8_0]\nembeddings = true\nlog-colors = off\npooling = last\nbatch-size = 8192\nctx-size = 8192\nmodel = ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf\nparallel = 1\nubatch-size = 8192\n\n"
      },
      "architecture": {
        "input_modalities": [
          "text"
        ],
        "output_modalities": [
          "text"
        ]
      },
      "source": "preset",
      "can_remove": false,
      "context_length": 40960,
      "memory": {
        "status": "measured",
        "min": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 940179520
            }
          ]
        },
        "max": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 55662329856
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 940179520
            }
          ]
        },
        "effective": {
          "n_ctx": 8192,
          "devices": [
            {
              "kind": "device",
              "name": "MTL0",
              "model": 4273711264,
              "context": 1207959552,
              "compute": 1426325536,
              "total": 55662788608,
              "free": 48754049024
            },
            {
              "kind": "host",
              "name": "Host",
              "model": 412528800,
              "context": 0,
              "compute": 470089760
            }
          ]
        }
      },
      "meta": {
        "vocab_type": 2,
        "n_vocab": 151665,
        "n_ctx": 8192,
        "n_ctx_train": 40960,
        "n_embd": 2560,
        "n_params": 4021774336,
        "size": 4273711264,
        "ftype": "Q8_0"
      }
    }
  ],
  "object": "list"
}
```

## 6. Stop

SIGTERM to the router process group (pgid 36787): router gone in {'36787': 0.121} s, no SIGKILL needed. A scan for any process running the spike binary after the stop found: `[]`.

## Verdict (repeated)

**D7 met on b11941: yes.** Evidence: section 5 table. Only the edited model unloaded; the embedding child kept pid 36805; the reloaded text model shows `--ctx-size 4096`. Removal and addition behave per model. Notes for the design: (1) the first load can block while memory is measured; (2) measure children exist alongside model children; (3) with the real `HOME` the router also lists the Hugging Face cache.
