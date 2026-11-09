# Design: ONNX Pod Thread Cap

## Context

ADR-117 constructs `magika.Magika()` once per process in `integrations/magika.py`. The installed Magika 1.0.3 constructor calls its own `_init_onnx_session()` with no `SessionOptions`. The installed ONNX Runtime defaults both thread counts to zero, which means automatic allocation. The pod exposes 96 CPUs but its purchased 12-vCPU allocation is absent from `os.cpu_count()`, `sched_getaffinity` and cgroup configuration.

## Goals / Non-Goals

**Goals:**

- Give the Magika ONNX session explicit worker counts.
- Derive the count without adding a setting or machine-specific configuration.
- Measure the hypothesis and retain evidence.
- Preserve the process cache, CPU provider and detection results.

**Non-Goals:**

- Change the reranker or OCR ONNX sessions.
- Infer a purchased CPU allocation that the container does not expose.
- Add a timing assertion to the portable unit suite.
- Change Magika's dependency version or its availability check.

## Decisions

### D1. Override only Magika's ONNX session factory

Define a private Magika subclass in `integrations/magika.py`. Its `_init_onnx_session()` constructs `onnxruntime.SessionOptions`, sets `intra_op_num_threads` and `inter_op_num_threads`, and passes the options to `InferenceSession` with the existing model path and CPU provider. The existing `_get_magika_instance()` lock constructs this subclass. Imports remain lazy inside those functions.

This is a small override of the pinned library's construction hook. The subclass does not replace model loading, feature extraction or result handling. A construction failure follows the existing warned suffix fallback.

Alternatives:

- `OMP_NUM_THREADS`: ONNX Runtime documents per-session options as the control for its own thread pools. Environment state is process-wide and cannot reliably change an existing runtime.
- Replace Magika's session after construction: builds the uncapped pool first and adds a second session.
- Vendor or fork Magika: unnecessary for one session factory.

### D2. Start with a ceiling of eight visible CPUs

Use `min(len(os.sched_getaffinity(0)), 8)` where affinity is available, otherwise `min(os.cpu_count() or 1, 8)`. Use one inter-operation worker because Magika executes a small sequential model. The value of eight is a conservative resource ceiling, not an inferred pod entitlement. The pod compares uncapped, eight and twelve workers before the final ADR records the choice.

A fixed ceiling protects ordinary large hosts as well as the measured pod. Eight is the handover's candidate value. Twelve is measured because it matches the pod's purchased allocation. If twelve is materially faster and does not over-allocate a smaller host, update the specification and this design before changing the implementation.

### D3. Test construction, not local speed

A unit test injects fake Magika and ONNX modules, drives the real lazy constructor, and records the options and provider. Parameterised cases cover 4, 8 and 96 visible CPUs plus the affinity fallback. Existing cache and label-equality tests cover reuse and unchanged outputs. A mutation check removes the explicit options and proves the new test fails.

### D4. Measure the real session on one pod

Use the existing ten-file slice and environment pattern. Install the already locked base dependencies; no model download or GPU inference is needed. Run each thread configuration in a fresh process with the same Magika model. Record environment facts, model load, repeated individual predictions and batched predictions. Include an uncapped control and twelve-worker comparison. One real ingest control pass records the existing Magika detection stage with the selected cap. Copy the results, verify checksums, then delete the pod in the same turn.

## Risks / Trade-offs

- [Magika changes its private session hook] → the dependency stays pinned at 1.0.3; the constructor test fails if the integration stops supplying options.
- [Eight threads underuses a genuinely larger allocation] → this bounds detection CPU use; no measured need justifies a new setting.
- [The subclass drifts from Magika's constructor] → use only its model path and retain its CPU provider; label-equality tests cover the resulting session.
- [Pod timings vary] → compare configurations on one pod with repeated fresh-process runs and preserve raw results.
