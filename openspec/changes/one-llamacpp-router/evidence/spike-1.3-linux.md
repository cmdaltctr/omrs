# Spike 1.3, Linux half: router children and stop behaviour

Date: 2026-11-06. Change: `one-llamacpp-router`. Design: D9.

## Setup

- Host: Mac (Apple silicon), Docker Desktop 29.9.2. Native `linux/arm64` container, `ubuntu:24.04`, run with `--init` (docker-init is PID 1), `--memory 4g --cpus 4`.
- Build: `llama-b11941-bin-ubuntu-arm64.tar.gz`, SHA-256 `38709fdb072c1df76cb3cf54b5bf56b22d6b0ac77ff9d41e60b41da177f7f77a` (matches the release API digest). Mounted read only at `/opt/llama`.
- `llama-server --version`: `version: 0.7.0-dev (build 11941, commit 19ff817fb)`, `built with GNU 14.2.0 for Linux aarch64`.
- Extra apt packages: `libgomp1` (needed: `ldd` showed `libgomp.so.1 => not found` without it), `python3`, `procps`, `curl`, `ca-certificates`.
- Models (read only mounts of the Hugging Face cache folders): `Qwen3-0.6B-Q8_0.gguf` and `Qwen3-Embedding-0.6B-Q8_0.gguf`.
- Driver: `<scratch>/spikes/linux/scripts/spike13.py`, run as `python3 -I`. It starts the router with `subprocess.Popen(argv, stdin=DEVNULL, start_new_session=True, close_fds=True)`, as `process.py` `launch()` does.
- Raw output: `<scratch>/spikes/linux/spike13-run1.jsonl`, `<scratch>/spikes/linux/spike13-run2-subreaper.jsonl`, router log `<scratch>/spikes/linux/spike13-router.log`.

Router command:

```
/opt/llama/llama-server --models-preset /work/models.ini --models-max 4 --models-memory-margin 1024 --host 127.0.0.1 --port 18080
```

Preset (`/work/models.ini`):

```
[Qwen/Qwen3-0.6B-GGUF:Q8_0]
model = /models/.../Qwen3-0.6B-Q8_0.gguf
ctx-size = 2048

[Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0]
model = /models/.../Qwen3-Embedding-0.6B-Q8_0.gguf
embeddings = true
pooling = last
ctx-size = 2048
```

`POST /models/load` returned `200 {"success": true}` for both. `GET /models` showed both `loaded`. Smoke test: embeddings returned 1024 dimensions; chat completion returned (`finish_reason: length`, 8 tokens).

## Process facts (run 1, before case A)

| Process | pid | ppid | pgid | sid | VmRSS |
| --- | --- | --- | --- | --- | --- |
| router | 2070 | 2060 (driver) | 2070 | 2070 | 18000 kB |
| child, Qwen3-0.6B | 2099 | 2070 | 2070 | 2070 | 1555588 kB |
| child, Qwen3-Embedding-0.6B | 2128 | 2070 | 2070 | 2070 | 1393388 kB |

Run 2 (before case B) gave the same shape: router 2196 (pgid 2196, sid 2196, 17672 kB), children 2225 (1552676 kB) and 2254 (1393092 kB), both ppid 2196, pgid 2196, sid 2196.

- Children share the router's process group and session. The b11941 spawn code (`vendor/sheredom/subprocess.h`, `posix_spawn`) sets no `posix_spawnattr` flags, so no new group.
- `/proc/<router>/task/*/children`: run 1 `{"2077": [2099], "2078": [2128]}`; run 2 `{"2203": [2225], "2204": [2254]}`. Each child sits under a different router thread. Reading only `/proc/<pid>/children` of the main thread would miss both. Reading all `task/*/children` gives the same set as `ps --ppid <router>` in both runs.
- `/proc/<child>/cmdline` argv[0] is `/opt/llama/llama-server` (the router binary path) for every child. `/proc/<child>/exe` is the same path.
- Child command lines (run 1):
  - `/opt/llama/llama-server --host 127.0.0.1 --log-colors off --port 38861 --alias Qwen/Qwen3-0.6B-GGUF:Q8_0 --ctx-size 2048 --model /models/.../Qwen3-0.6B-Q8_0.gguf`
  - `/opt/llama/llama-server --embeddings --host 127.0.0.1 --log-colors off --pooling last --port 57923 --alias Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --ctx-size 2048 --model /models/.../Qwen3-Embedding-0.6B-Q8_0.gguf`
- Each child port is random. The model id is the `--alias` value.
- RSS note: each 0.6B Q8_0 child shows about 1.4 to 1.5 GB VmRSS on this aarch64 CPU build. The router itself is about 18 MB.
- The router log shows a memory measurement step before each spawn (`make_room: waiting for memory measurement`, then lines tagged `[    0]` reporting `memory measured ... n_ctx=2048`). I did not capture a pid for that step.

## Case A: SIGTERM to the router process group

`os.killpg(router_pid, SIGTERM)` in run 1.

| pid | gone after |
| --- | --- |
| 2099 (child) | 0.020 s |
| 2128 (child) | 0.020 s |
| 2070 (router) | 0.083 s |

- All three exited within 0.083 s. Router exit code 0.
- Router log shows `exit command received, exiting...` from both children, so the router also sent its stdin exit command on SIGTERM.
- No survivor. `ps` after the run showed only docker-init, `sleep`, and the driver.

Router restarted (run 2) and both models loaded again.

## Case B: SIGKILL to the router pid only

`os.kill(router_pid, SIGKILL)` in run 2. Polled up to 30 s.

| pid | gone after |
| --- | --- |
| 2225 (child) | 0.03 s |
| 2254 (child) | 0.03 s |

- Router exit status -9. Both children exited within 0.03 s. No survivor.

Case C (repeat of case B with the driver set as child subreaper, `prctl(PR_SET_CHILD_SUBREAPER)`, to read exit statuses): router 2324 killed by signal 9; children 2353 and 2382 both exited normally with exit code 1, 0.012 s after the kill.

Mechanism: stdin end of file, not `PR_SET_PDEATHSIG`.

- b11941 `tools/server/server-common.cpp` `server_role::setup()` runs a thread that reads stdin. On end of file it logs `EOF on stdin detected, forcing shutdown...` and calls `exit(1)`. On the line `cmd_router_to_child:exit` it calls the shutdown handler.
- The router holds the write end of each child's stdin pipe. When the router dies, the kernel closes it, the child reads end of file and exits with code 1. Case C exit code 1 matches this path.
- `server-models.cpp`, `common/subproc.cpp` and `vendor/sheredom/subprocess.h` at b11941 contain no `prctl`, `PR_SET_PDEATHSIG`, `setsid` or `setpgid`.
- The pipes are created with `O_CLOEXEC` (`subprocess.h`, `pipe2(fds, O_CLOEXEC)`), so one child does not hold another child's stdin open. This is what lets each child see end of file.

## Verdict for design D9 on Linux

No child survived case A (group SIGTERM, all gone in 0.083 s) or case B (SIGKILL of the router pid alone, children gone in 0.03 s, exit code 1 from stdin end of file). The per-child stop of D9's stop condition is not needed on Linux for b11941. The direct-children read must walk every `/proc/<pid>/task/*/children` file, because each child hangs under a different router thread.
