# Spike 1.4, GPU part (2026-11-06)

Build b11941 (commit 19ff817fb), `ubuntu-cuda-12.8-x64` plus `cudart`. RunPod Secure Cloud pod, RTX A6000 48 GB, EU-SE-1, $0.59/hr, image `nvidia/cuda:12.8.1-base-ubuntu24.04`. Pod created 17:01:53 UTC and deleted after the run (about 2 minutes, about $0.02). The RTX 4000 Ada and L4 had no capacity at create time.

| Check | Result |
| --- | --- |
| OS, glibc | Ubuntu 24.04.1, glibc 2.39 |
| Driver | 595.91.07, CUDA 13.2 (newer than 12.8 needs) |
| SHA-256 of both archives | `sha256sum -c`: OK, OK |
| `llama-server --version` | build 11941, commit 19ff817fb, GNU 13.3.0, Linux x86_64 |
| `llama-server --list-devices` | `CUDA0: NVIDIA RTX A6000 (45490 MiB, 45219 MiB free)`, exit 0 |
| Load Qwen3-0.6B Q8_0, `-ngl all` | `/health` 200 after 1 s; completion answered |
| Speed | prompt 658.6 tokens/s, generation 350.6 tokens/s |

Library note: `cudart` files were unpacked beside `llama-server` (strip 1 folder). `libcublas` and `libcublasLt` resolved from that folder. `libcudart.so.12` resolved from `/usr/local/cuda/lib64`, because this CUDA image already ships it and the loader found it first. The Docker run (`spike-1.4-nogpu.md`) showed the beside-binary file resolves on a host without CUDA. The `libgomp1` package was installed by the script; the base image lacks it.

Verdict: the CUDA 12.8 build runs on a RunPod GPU with a CUDA 13.2 driver. The stop condition did not fire. The `cuda-device-missing` check (design D12) has a positive case: the device line starts with `CUDA0:`.
