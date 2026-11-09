# Proposal: ONNX Pod Thread Cap

## Why

Magika in-process detection costs 49.9 to 108.8 ms per file on a 12-vCPU pod, versus 1.86 ms on a 10-core Mac. The container exposes 96 host CPUs without a cgroup quota, so its default ONNX session creates too many inference threads. Resolve this before Experiment 35a.

## What Changes

- Construct Magika's ONNX session with explicit thread limits at the existing lazy, process-wide construction seam.
- Derive the limit from visible CPUs, with an upper bound selected by a pod measurement. Add no user-facing setting because the affected container cannot report its purchased CPU allocation.
- Keep Magika's model, prediction mode, detection results, availability check and suffix fallback unchanged.
- Measure uncapped, eight-thread and twelve-thread sessions on one short pod session. Record the selected cap and evidence in ADR-118.
- Leave the reranker and local OCR ONNX paths unchanged; they have no matching measurement.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `type-aware-ingestion`: add bounded Magika ONNX inference threads without changing content labels.
- `content-type-detection`: add the same bounded-session requirement at the in-process detector seam.

## Impact

Affected code: `src/omrs/integrations/magika.py` and its unit tests. The pinned Magika dependency stays at 1.0.3. No settings schema, GUI, dependency, embedding or retrieval change is required. A local subclass is necessary because the pinned Python constructor does not accept ONNX `SessionOptions`.
