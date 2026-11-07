# Spike 1.4, no-GPU part: Linux x86-64 builds of b11941

Date: 2026-11-06. Change: `one-llamacpp-router`. Design: D12.

Host: Mac (Apple silicon), Docker Desktop 29.9.2. Checks ran in a `--platform linux/amd64` `ubuntu:24.04` container (emulated, `/proc/cpuinfo` model `VirtualApple @ 2.50GHz`, flags include `sse4_2 fma avx f16c avx2`). Extra apt packages: `binutils`, `libgomp1`. Archives downloaded with `gh release download b11941 -R ggml-org/llama.cpp` into `<scratch>/spikes/linux/dl`.

## 1. SHA-256 against the release

| Archive | Release digest (GitHub API) | Local `shasum -a 256` | Size (bytes) | Result |
| --- | --- | --- | --- | --- |
| `llama-b11941-bin-ubuntu-x64.tar.gz` | `e8a1ee13aa19c6c78f5651457758160da27410301b179d6ef3505c81c8ea31f1` | `e8a1ee13aa19c6c78f5651457758160da27410301b179d6ef3505c81c8ea31f1` | 22566911 | match |
| `llama-b11941-bin-ubuntu-cuda-12.8-x64.tar.gz` | `9945330f20a35b9a30fbac43f99f5b7f88ae7dd32dc2e5089af5c75310d3acf1` | `9945330f20a35b9a30fbac43f99f5b7f88ae7dd32dc2e5089af5c75310d3acf1` | 182300431 | match |
| `cudart-llama-b11941-bin-ubuntu-cuda-12.8-x64.tar.gz` | `3011ef1b30e73a3059c5a4d3d44446562155aff49035efc49e7e2f1c370524f8` | `3011ef1b30e73a3059c5a4d3d44446562155aff49035efc49e7e2f1c370524f8` | 594373636 | match |
| `llama-b11941-bin-ubuntu-arm64.tar.gz` (spike 1.3) | `38709fdb072c1df76cb3cf54b5bf56b22d6b0ac77ff9d41e60b41da177f7f77a` | `38709fdb072c1df76cb3cf54b5bf56b22d6b0ac77ff9d41e60b41da177f7f77a` | 18314731 | match |

## 2. Unpacked layout

Top folder of each archive:

- `ubuntu-x64` unpacks to `llama-b11941/` (51 files, 10 symlinks).
- `ubuntu-cuda-12.8-x64` also unpacks to `llama-b11941/` (52 files, 10 symlinks). The two flavours use the same folder name, so unpacking both into one parent overwrites one with the other.
- `cudart` unpacks to `cudart-llama-b11941-bin-ubuntu-cuda-12.8-x64/` (3 files, no symlinks).

Libraries in `ubuntu-x64/llama-b11941/`:

- `libggml-base.so` -> `.so.0` -> `.so.0.27.0`; `libggml.so` -> `.so.0` -> `.so.0.27.0`; `libllama.so` -> `.so.0` -> `.so.0.7.0`; `libllama-common.so` -> `.so.0` -> `.so.0.7.0`; `libmtmd.so` -> `.so.0` -> `.so.0.7.0`
- CPU backends: `libggml-cpu-{alderlake,cannonlake,cascadelake,cooperlake,haswell,icelake,ivybridge,piledriver,sandybridge,sapphirerapids,skylakex,sse42,x64,zen4}.so`
- `libggml-rpc.so`
- Tool libraries: `libllama-{batched-bench,bench,cli,completion,fit-params,perplexity,quantize,server}-impl.so`

`ubuntu-cuda-12.8-x64/llama-b11941/` holds the same list plus `libggml-cuda.so` (183247896 bytes).

`cudart` holds `libcudart.so.12` (728800 bytes), `libcublas.so.12` (116388640 bytes), `libcublasLt.so.12` (751775824 bytes).

Executables in both flavours: `llama-server`, `llama`, `llama-cli`, `llama-bench`, `llama-batched-bench`, `llama-completion`, `llama-connect`, `llama-fit-params`, `llama-gemma3-cli`, `llama-gguf-split`, `llama-imatrix`, `llama-llava-cli`, `llama-minicpmv-cli`, `llama-mtmd-cli`, `llama-mtmd-debug`, `llama-perplexity`, `llama-quantize`, `llama-qwen2vl-cli`, `llama-results`, `llama-tokenize`, `llama-tts`, `ggml-rpc-server`, and `LICENSE`.

`readelf -d` RUNPATH and NEEDED:

| File | RUNPATH | NEEDED |
| --- | --- | --- |
| CPU `llama-server` | `$ORIGIN` | `libllama-server-impl.so`, `libstdc++.so.6`, `libgcc_s.so.1`, `libc.so.6` |
| CUDA `llama-server` | `$ORIGIN` | same as CPU |
| CUDA `libggml-cuda.so` | `$ORIGIN` | `libggml-base.so.0`, `libcudart.so.12`, `libcublas.so.12`, `libcuda.so.1`, `libstdc++.so.6`, `libm.so.6`, `libgcc_s.so.1`, `libc.so.6`, `ld-linux-x86-64.so.2` |
| CUDA `libggml-base.so.0.27.0` | `$ORIGIN` | `libgomp.so.1`, `libstdc++.so.6`, `libm.so.6`, `libgcc_s.so.1`, `libc.so.6` |
| CUDA `libllama-server-impl.so` | `$ORIGIN` | `libllama-common.so.0`, `libmtmd.so.0`, `libllama.so.0`, `libggml.so.0`, `libggml-base.so.0`, `libssl.so.3`, `libcrypto.so.3`, `libstdc++.so.6`, `libm.so.6`, `libgcc_s.so.1`, `libc.so.6`, `ld-linux-x86-64.so.2` |
| `libcublas.so.12` | `$ORIGIN` | `libcublasLt.so.12`, `librt`, `libpthread`, `libdl`, `libm`, `libgcc_s`, `libc`, `ld-linux` |
| `libcublasLt.so.12` | `$ORIGIN` | system libraries only |
| `libcudart.so.12` | none | system libraries only |

No file has RPATH. Every llama.cpp file and both cuBLAS files use RUNPATH `$ORIGIN`.

`llama-server` does not link `libggml-cuda.so`. It loads backends with `dlopen` from its own folder at start (`load_backend: loaded CPU backend from <dir>/libggml-cpu-haswell.so`).

`ldd` per layout (CUDA build):

| Layout | `libcudart.so.12` | `libcublas.so.12` | `libcublasLt.so.12` | `libcuda.so.1` |
| --- | --- | --- | --- | --- |
| CUDA folder alone | not found | not found | (not reached) | not found |
| `LD_LIBRARY_PATH=<cudart folder>` | found | found | found | not found |
| cudart files copied beside `llama-server` | found (beside) | found (beside) | found (beside) | not found |

`LD_DEBUG=libs` for the side-by-side layout shows the loader searching `$ORIGIN` first, finding `libcudart.so.12` and `libcublas.so.12` there, then searching the system folders for `libcuda.so.1`.

Answer to the open question: both layouts work. Side by side is the one that needs nothing at run time: `libggml-cuda.so` has RUNPATH `$ORIGIN`, so cudart files in the same folder resolve with no environment variable. With side by side, `ldd` resolves every library except the driver library `libcuda.so.1`. Recommendation for D12: unpack the cudart archive's three files into the same `b11941-cuda/` folder as `llama-server` and set no `LD_LIBRARY_PATH`.

System libraries the builds need from the host (not in the archives): `libgomp.so.1` (Ubuntu package `libgomp1`, not in the `ubuntu:24.04` base image), `libssl.so.3` and `libcrypto.so.3` (`libssl3t64`, in the base image), `libstdc++.so.6`, and glibc.

Minimum glibc (highest symbol versions in `objdump -T`):

| Folder | GLIBC | GLIBCXX |
| --- | --- | --- |
| CPU `llama-b11941/` | 2.34 | 3.4.30 |
| CUDA `llama-b11941/` | 2.38 | 3.4.32 |
| `cudart` | 2.27 | none |

The CUDA build needs glibc 2.38 and `GLIBCXX_3.4.32`: Ubuntu 24.04 or newer. Ubuntu 22.04 has glibc 2.35 and `GLIBCXX` up to 3.4.30, so the CUDA build will not load there. This is read from symbol versions; I did not run a 22.04 container (not an allowed image). The CPU build fits Ubuntu 22.04.

## 3. `--version` and `--list-devices` (emulated amd64, no GPU)

| Build | `--version` | `--list-devices` | Exit |
| --- | --- | --- | --- |
| CPU | `version: 0.7.0-dev (build 11941, commit 19ff817fb)`, `built with GNU 11.4.0 for Linux x86_64` | `Available devices:` `(none)` | 0 |
| CUDA, cudart missing | same version line, `built with GNU 13.3.0 for Linux x86_64` | `Available devices:` `(none)` | 0 |
| CUDA, cudart side by side | same as above | `Available devices:` `(none)` | 0 |
| CUDA, cudart on `LD_LIBRARY_PATH` | not run | `Available devices:` `(none)` | 0 |

- The CPU build reports no CUDA device.
- The CUDA build without a GPU gives no error and exit code 0. With `-v` it logs only the RPC and CPU backend loads; the failed `dlopen` of `libggml-cuda.so` (no `libcuda.so.1`) is silent. Output is the same whether cudart is missing or present. So `--list-devices` cannot tell "cudart missing" from "no driver". OMRS must treat "no CUDA line in `--list-devices`" as the failure sign on a CUDA install, not a non-zero exit.

## 4. What remains for a real GPU pod

1. Use a pod image based on Ubuntu 24.04 or newer (glibc 2.38). Install `libgomp1`.
2. Record `nvidia-smi` driver version and its reported CUDA version. Check it supports CUDA 12.8. If not, stop and ask the operator (13.4 or user path).
3. Unpack CUDA build and cudart side by side; run `ldd libggml-cuda.so` and confirm `libcuda.so.1` now resolves.
4. Run `llama-server --list-devices`; record the CUDA device line (name, memory).
5. Start the router with one tiny model (`Qwen3-0.6B Q8_0`), load it, send one chat request, and confirm the child log shows layers offloaded to CUDA.
