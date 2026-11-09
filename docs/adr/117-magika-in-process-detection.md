# ADR-117: Run Magika Detection In Process

- **Date:** 2026-11-09
- **Status:** Accepted (gate passed 2026-11-09)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-068](068-pin-magika-content-detection.md),
  [ADR-037](037-architecture-v2-conformance.md)

## Context

A profile of a 200-file FreshStack ingest (2026-11-08) measured the Magika
subprocess at 0.071 s per `ingest_path_async` call. That is 8.3% of the
0.849 s mean per-file time. Profile artefacts live under
`~/Development/DATA/omrs/experiments/pre-exp35-ingest-profile-2026-11-08/`.

The subprocess spawns `magika -r <dir> --jsonl` once per call. Every call
pays the CLI model startup again.

ADR-068 decision 2 chose the subprocess when the in-process alternative was
hypothetical. The Python API is now stable. `magika==1.0.3` is already a
pinned base dependency, so this adds no new dependency.

## Decision

This ADR supersedes decisions 2 and 6 of ADR-068. Every other decision stays
governed by ADR-068: the pin (1), validation strictness (3 and 4), boundary
normalisation (5), and index identity (7).

1. Construct `magika.Magika()` once per process, lazily, through a
   module-level `functools.lru_cache(maxsize=1)` wrapper in
   `src/omrs/integrations/magika.py`. The lazy import of the magika package
   stays inside that wrapper so importing the module never loads ONNX Runtime.
2. `scan_with_magika` walks the directory itself, skipping `_EXCLUDED_DIRS`
   during the walk. A single-file root yields the `.` key. It then calls
   `m.identify_paths(files)` once for the whole scan, where `m` is the cached
   instance. A failed status, or a result with an empty or non-string
   `group`/`label` or a non-boolean `is_text`, raises `ValueError` for the
   whole scan, exactly as one invalid JSONL row did under ADR-068 decisions 3
   and 4. The caller falls back to suffix detection. No partial results.
3. Label equality with the CLI is test-verified on the frozen 16-file
   acceptance corpus from ADR-068. Paths were updated after the omrg to omrs
   rename. A mismatch blocks the release of the change.
4. The boundary normalisation of ADR-068 decision 5 is unchanged and now
   applied to Python API results. That covers the binary rule plus the
   `text/markdown -> document/markdown` and `text/txt -> document/text`
   aliases.
5. `_is_magika_available` still checks the `magika` program via
   `MAGIKA_BINARY` injection
   ([TDR-025](../tdr/025-magika-content-type-detection-settings-injection.md)
   stays). The bundled CLI remains the availability signal and the smoke
   tool's ground truth. If `Magika()` construction or `identify_paths`
   raises, detection degrades to the warned suffix fallback. This supersedes
   decision 6's subprocess failure modes. The 30-second subprocess timeout
   disappears with the subprocess.

## Consequences

### Positive

- About 0.07 s saved per call on the Mac profile.
- One model load per process instead of one per call.
- The JSONL parsing layer is gone.

### Negative

- The ONNX model now loads inside the application process on the first
  detection call. That adds one-time latency and resident memory.
- A hung ONNX call can no longer be timed out.

### Neutral

- The CLI binary remains shipped. It is still used for availability checks
  and by the smoke tool.
- The pod-only 0.79 s per-file cost is measured separately in the change's
  pod step. This ADR does not assume the in-process switch fixes it.

## Alternatives Considered

| Option | Rejected because |
| --- | --- |
| Keep the subprocess | Measured at 0.071 s per call on the Mac profile. |
| One batched subprocess per directory | Still pays process spawn and keeps the parsing layer. |
| A worker thread pool around the CLI | Complexity for no measured need. |

## Gate evidence

BEFORE (Mac profile, 2026-11-08):

- Magika subprocess: 0.071 s per `ingest_path_async` call.
- Share of the 0.849 s mean per-file time: 8.3%.

Gate results (2026-11-09, task 2.4 and 2.5):

- Label-equality test: PASSED. All 16 ADR-068 corpus files produce equal
  `(group, label, is_text)` triples from the Python API path and the CLI
  ground truth, with identical path sets.
- Cache test: PASSED. Two scans in one process construct `magika.Magika()`
  exactly once and the cached instance serves both scans.
- Mutation checks: removing the `lru_cache` fails the cache test; skipping
  boundary normalisation fails the label-equality test.
- Mac bench (FreshStack slice, `magika_bench.py`): CLI subprocess
  52.2 ms/file; in-process 1.86 ms/file after a 6 ms one-time model load.
- Pod before/after: recorded separately in the change's pod step.

## References

- `openspec/changes/ingest-per-file-overhead-reduction/proposal.md`
- `openspec/changes/ingest-per-file-overhead-reduction/design.md`
- [ADR-068](068-pin-magika-content-detection.md)
- `scripts/magika_label_smoke.py`
- `src/omrs/integrations/magika.py`
- `~/Development/DATA/omrs/experiments/pre-exp35-ingest-profile-2026-11-08/`
