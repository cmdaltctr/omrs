# Spike 1.2 addendum: Hugging Face cache listing (2026-11-06)

Build b11941 (commit 19ff817fb), macOS arm64. Router on 127.0.0.1:18432, no model loaded.

Setup: scratch `HOME` whose `~/.cache/huggingface/hub` holds one model folder (`Qwen/Qwen3-Embedding-0.6B-GGUF`). Preset `models.ini` names one other entry, `test/only:Q8_0`. Script: `<scratch>/spikes/cache-test/probe.py`.

| Child environment | `GET /v1/models` ids |
| --- | --- |
| `HOME`, `PATH` only | `Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0`, `test/only:Q8_0` |
| plus `LLAMA_CACHE=<empty folder>` and `XDG_CONFIG_HOME=<empty folder>` | `test/only:Q8_0` |

Source: `common/hf-cache.cpp` lines 40 to 45 read the cache path from `LLAMA_CACHE` first, then `HF_HUB_CACHE`, `HF_HOME`, `XDG_CACHE_HOME`, then `HOME`. `tools/server/server-models.cpp` line 730 always adds cached models (`load_from_cache`). No flag turns it off.

Verdict: setting `LLAMA_CACHE` to an empty folder in the router environment removes every cache model from the router list. With autoload on (the default), this also stops a stray request from loading a cache model.
