# Proposal: Ingest Per-file Overhead Reduction

## Why

A profiled 200-file FreshStack ingest (task 2.1 of `pre-exp35-harness-and-answer-fixes`,
2026-11-08) found three per-file costs in OMRS code and a fourth on the pod that cannot
be diagnosed from the Mac. The splitter rebuild (0.085 s/file) was already fixed.
Three items remain: Magika's subprocess startup per call (0.071 s, 8% of each call),
the pod-only 0.79 s of unknown origin, and the LanceDB store reopening the collection
12 times per file (0.022 s). Together, fixing what can be fixed now and measuring what
cannot will reduce ingestion time and verify the 35a benchmark run is as fast as it can
be before the freeze.

## What Changes

- **New ADR (supersedes ADR-068 decisions 2 and 6):** run Magika in-process via the
  Python API (`magika.Magika`) instead of spawning a subprocess per call. Preserves
  the JSONL parsing contract, label equality (test-verified), and the suffix fallback.
  The ONNX Runtime model loads once per process (lazy, cached). Saves ~0.07 s per
  `ingest_path_async` call.
- **Pod measurement step (operator-gated):** a short pod session running the profile
  script from the Mac (`experiments/pre-exp35-ingest-profile-2026-11-08/scripts/`) on
  the Linux RTX 4090 to measure `nproc`, `time magika`, per-stage spans, and cProfile.
  No experiment runs. The output names the cause of the 0.79 s or proves it is not
  Magika. This session is short (<1 h) and uses the same pod shape as D9 ($0.89/h).
- **LanceDB store reopens** (score 10, optional): reduce the 12 per-file collection
  opens and 3 `count_where` calls if the fix is small and local (one module, no change
  to the cross-process cache rule of gotcha 14). If it is not small, this becomes a
  proposed issue only.

## Scope

- Non-breaking. Detection labels and behaviour are unchanged; the suffix fallback is
  unchanged. Existing callers (`ingest_path_async`, the watcher, the MCP ingest tool,
  the CLI `omrs ingest`) keep their interface.
- The Magika Python API is already a base dependency (`magika==1.0.3` in `pyproject.toml`).
  No new dependency is added.
- No change to the experiment protocol, the benchmark harness, or the 35a plan.
  The profile artefacts live in `~/Development/DATA/omrs/experiments/` only.

## Breaking Changes

None.

## Open Questions

1. Does the pod's 0.79 s come from Magika or from ONNX Runtime thread count (binding to
   `os.cpu_count()` on a 56-vCPU host rather than the 12 vCPU floor)? The pod step
   answers this. If Magika is the cause, the in-process fix also removes the pod cost.
   If it is ONNX thread count, a separate `OrtEnvironment` thread-cap fix is needed.
2. Is the LanceDB reopen fix small enough to include here? Assessed in task 3.2.
