# Spike 1.3 (macOS half): router child processes

| Item | Value |
| --- | --- |
| llama.cpp build | b11941, commit 19ff817fb (`llama-server --version`: `version: 0.7.0-dev (build 11941, commit 19ff817fb)`) |
| Binary | `<scratch>/llama-b11941/mac/llama-b11941/llama-server` (official macOS arm64 asset, SHA-256 checked earlier) |
| Date | 2026-11-06 |
| Machine | `sysctl hw.model` = Mac17,9, `hw.memsize` = 68719476736 bytes (64 GiB), Apple M5 Pro, macOS 27.2 |
| Raw record | `<scratch>/spikes/mac/out/spike-1.3-macos.json, spike-1.3c-macos.json` |
| Script | `<scratch>/spikes/mac/spike_1_3.py and spike_1_3c.py` (helpers in `common.py`) |
| Run command | `cd <worktree> && uv run --no-sync python <scratch>/spikes/mac/spike_1_3.py and spike_1_3c.py` |

Paths: `<scratch>` is the session scratchpad. `<worktree>` is the `omrs-feat-one-llamacpp-router` worktree. `~` is the real home folder (model files only).

## Verdict

**D9 on macOS: no child survives case A or case B.** Case A (SIGTERM to the router group): all three processes gone in 0.134 s, no SIGKILL needed. Case B (SIGKILL to the router pid only): both children gone at the first poll, 0.004 s after the kill. An extra case C (router killed while one child was loading and one measure child was running) also left no survivor (last exit 0.357 s). The per-child stop of the D9 stop condition is not needed on macOS. The Linux half is still open.

Mechanism: each child is spawned with a pipe on its standard input and runs a thread that waits for end of file on it (child log: `child server monitoring thread started, waiting for EOF on stdin...`). When the router dies, the pipe closes and the child exits.

## Setup

Same preset and router argument list as spike 1.2 (embedding 4B with `embeddings = true`, `pooling = last`, `ctx-size`, `batch-size`, `ubatch-size` 8192, `parallel = 1`; Qwen3-4B with `ctx-size = 8192`). Started as `process.py` does: new session, stdin `/dev/null`, output to a log file, minimal environment with scratch `HOME` and `TMPDIR`. Both models loaded with `POST /models/load`, then the script waited until every model's `memory.status` was `measured`, so no measure child was running at the snapshot.

```text
<scratch>/llama-b11941/mac/llama-b11941/llama-server --models-preset <scratch>/spikes/mac/state/runtimes/router/models.ini --models-max 4 --models-memory-margin 8192 --host 127.0.0.1 --port 18431
```

## Case A start: router and children with both models loaded

Router pid 41493, pgid 41493, sid 41493. The router leads its own session and process group (from `start_new_session=True`). Each child has ppid = router pid and the same pgid and sid.

| pid | ppid | pgid | sid | RSS (KiB) | stat | command |
| --- | --- | --- | --- | --- | --- | --- |
| 41493 | 41490 | 41493 | 41493 | 105456 | Ss | `<scratch>/llama-b11941/mac/llama-b11941/llama-server --models-preset <scratch>/spikes/mac/state/runtimes/router/models.ini --models-max 4 --models-memory-margin 8192 --host 127.0.0.1 --port 18431` |
| 41497 | 41493 | 41493 | 41493 | 5498448 | S | `<scratch>/llama-b11941/mac/llama-b11941/llama-server --embeddings --host 127.0.0.1 --log-colors off --pooling last --port 53939 --alias Qwen/Qwen3-Embedding-4B-GGUF:Q8_0 --batch-size 8192 --ctx-size 8192 --model ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf --parallel 1 --ubatch-size 8192` |
| 41499 | 41493 | 41493 | 41493 | 5500336 | S | `<scratch>/llama-b11941/mac/llama-b11941/llama-server --host 127.0.0.1 --log-colors off --port 53947 --alias Qwen/Qwen3-4B-GGUF:Q8_0 --ctx-size 8192 --model ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf` |

(`ps -o sess` prints 0 on macOS; `sid` is from `os.getsid`, all equal 41493.)

Direct children lookup with libproc `proc_listchildpids(router_pid, buf, sizeof buf)` through ctypes (`/usr/lib/libproc.dylib`):

- Return value **2** (a count of pids, not bytes), pids `[41499, 41497]`.
- A sizing call with a NULL buffer returned 1046: an upper bound, not the child count. Use a fixed buffer and the return value.
- Full `ps -ax` scan, children with ppid = router: `[41497, 41499]`. Same set as libproc: **True**.
- Command line of each child holds the router binary path: `{'41497': True, '41499': True}`.
- Memory as D9 defines it (router RSS plus direct children whose command holds the binary): 105456 KiB + children = **11104240 KiB** (10.59 GiB).

`memory` field per model from `GET /v1/models` at the same moment (bytes):

```json
{
  "Qwen/Qwen3-4B-GGUF:Q8_0": {
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
  "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0": {
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
  }
}
```

## Case B start: router and children with both models loaded

Router pid 41526, pgid 41526, sid 41526. The router leads its own session and process group (from `start_new_session=True`). Each child has ppid = router pid and the same pgid and sid.

| pid | ppid | pgid | sid | RSS (KiB) | stat | command |
| --- | --- | --- | --- | --- | --- | --- |
| 41526 | 41490 | 41526 | 41526 | 104768 | Ss | `<scratch>/llama-b11941/mac/llama-b11941/llama-server --models-preset <scratch>/spikes/mac/state/runtimes/router/models.ini --models-max 4 --models-memory-margin 8192 --host 127.0.0.1 --port 18431` |
| 41546 | 41526 | 41526 | 41526 | 5499072 | S | `<scratch>/llama-b11941/mac/llama-b11941/llama-server --embeddings --host 127.0.0.1 --log-colors off --pooling last --port 53978 --alias Qwen/Qwen3-Embedding-4B-GGUF:Q8_0 --batch-size 8192 --ctx-size 8192 --model ~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B-GGUF/snapshots/f4602530db1d980e16da9d7d3a70294cf5c190be/Qwen3-Embedding-4B-Q8_0.gguf --parallel 1 --ubatch-size 8192` |
| 41560 | 41526 | 41526 | 41526 | 5500000 | S | `<scratch>/llama-b11941/mac/llama-b11941/llama-server --host 127.0.0.1 --log-colors off --port 53991 --alias Qwen/Qwen3-4B-GGUF:Q8_0 --ctx-size 8192 --model ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q8_0.gguf` |

(`ps -o sess` prints 0 on macOS; `sid` is from `os.getsid`, all equal 41526.)

Direct children lookup with libproc `proc_listchildpids(router_pid, buf, sizeof buf)` through ctypes (`/usr/lib/libproc.dylib`):

- Return value **2** (a count of pids, not bytes), pids `[41560, 41546]`.
- A sizing call with a NULL buffer returned 1052: an upper bound, not the child count. Use a fixed buffer and the return value.
- Full `ps -ax` scan, children with ppid = router: `[41546, 41560]`. Same set as libproc: **True**.
- Command line of each child holds the router binary path: `{'41546': True, '41560': True}`.
- Memory as D9 defines it (router RSS plus direct children whose command holds the binary): 104768 KiB + children = **11103840 KiB** (10.59 GiB).

`memory` field per model from `GET /v1/models` at the same moment (bytes):

```json
{
  "Qwen/Qwen3-4B-GGUF:Q8_0": {
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
  "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0": {
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
  }
}
```

## Case A: SIGTERM to the router process group

`os.killpg(41493, SIGTERM)`, then polled every 50 ms (`kill(pid, 0)` and `ps -o stat`, zombie counts as gone) for up to 30 s.

- Exit time per pid (seconds after the signal): `{'41499': 0.072, '41497': 0.075, '41493': 0.134}`. Router pid 41493.
- Survivors: `[]`. SIGKILL needed: **False**.
- Scan for any process running the spike binary afterwards: `[]`.

Router log at stop (`server-1.3a.log`):

```text
I srv    operator(): operator(): cleaning up before exit...
I srv    unload_all: stopping model instance name=Qwen/Qwen3-4B-GGUF:Q8_0
I srv    unload_all: stopping model instance name=Qwen/Qwen3-Embedding-4B-GGUF:Q8_0
I srv    operator(): exit command received, exiting...   (each child)
I srv           run: instance name=Qwen/Qwen3-4B-GGUF:Q8_0 exited with status 0
I srv           run: instance name=Qwen/Qwen3-Embedding-4B-GGUF:Q8_0 exited with status 0
```

The router was restarted and both models loaded again for case B (new pids below).

## Case B: SIGKILL to the router pid only

`os.kill(41526, SIGKILL)`, children `[41560, 41546]`, polled at once and then every 50 ms for up to 30 s.

- Exit time per pid: `{'41560': 0.004, '41546': 0.004, '41526': 0.004}`.
- Survivors: `[]`. Manual kill needed: **False**.
- Scan afterwards: `[]`.

## Case C (extra): SIGKILL to the router while a child loads and a measure child runs

Router started fresh, two `POST /models/load` sent in background threads, router killed 0.2 s later. Status at the kill: `{'Qwen/Qwen3-4B-GGUF:Q8_0': ['loading', 'measured'], 'Qwen/Qwen3-Embedding-4B-GGUF:Q8_0': ['unloaded', 'measuring']}`.

| pid | ppid | pgid | RSS (KiB) | measure child (`--offline`) | exit after kill (s) |
| --- | --- | --- | --- | --- | --- |
| 41995 | 41993 | 41993 | 103536 | False | 0.357 |
| 41996 | 41993 | 41993 | 16976 | True | 0.123 |

Router exit 0.008 s. Survivors `[]`, scan afterwards `[]`.

A second run killed the router 3.6 s after the load posts; both models had already loaded (warm page cache), so it repeats case B: exits `{'42016': 0.005, '42013': 0.005, '42011': 0.005}`, survivors `[]`.

## Notes for design D9 and task 3.6

1. Children share the router's process group and session, so the existing group stop reaches them.
2. `proc_listchildpids` gives exactly the direct children, matching a full scan. Its return value is a pid count on this macOS (27.2).
3. Measure children (`llama-server ... --offline`, about 1 MB RSS) also appear as direct children with the binary path in their command line. They live for well under a second, but a memory read can count them. Their RSS is negligible.
4. Model children's RSS (about 5.2 GiB each here) is far above the router's (about 100 MiB). The router's own `memory.effective` figures are per device in bytes and do not equal RSS (Metal buffers are not all resident).

## Verdict (repeated)

**No child survives case A or case B on macOS (b11941).** D9 needs no per-child stop for macOS.
