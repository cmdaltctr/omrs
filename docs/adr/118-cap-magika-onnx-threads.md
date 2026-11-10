# ADR-118: Cap Magika ONNX Threads

- **Date:** 2026-11-09
- **Status:** Proposed (pod gate passed 2026-11-09)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-117](117-magika-in-process-detection.md),
  [ADR-068](068-pin-magika-content-detection.md)

## Context

ADR-117 moved Magika detection in process. A 12-vCPU pod exposed all 96 host
CPUs without a cgroup quota. Its default ONNX session cost 108.8 ms per file
for individual detection and 49.9 ms per file for batched detection. The same
work took 1.86 ms per file on a 10-core Mac. See issue #201.

Magika 1.0.3 constructs `InferenceSession` without `SessionOptions`. Its Python
constructor has no thread-count argument. ONNX Runtime interprets a zero thread
count as automatic allocation. The container's CPU APIs cannot report the
purchased vCPU allocation.

## Decision

1. Override Magika 1.0.3's private `_init_onnx_session()` in a private subclass
   at the existing `_get_magika_instance()` seam. Supply `SessionOptions` to
   `InferenceSession` with the same model path and `CPUExecutionProvider`.
   Keep telemetry disabled and retain the lazy, lock-guarded process cache.
2. Set `intra_op_num_threads` to `min(visible CPUs, 8)`. Use
   `len(os.sched_getaffinity(0))` when available and `os.cpu_count() or 1`
   otherwise. Set `inter_op_num_threads` to one.
3. Add no setting. The measured container does not expose its purchased CPU
   allocation, and twelve threads offered no material advantage over eight.
   The ceiling is a resource policy, not a claim about pod entitlement.
4. Keep model selection, detection labels, normalisation, availability checks
   and suffix fallback unchanged. The reranker and OCR ONNX paths retain their
   existing construction because this issue supplies no measurements for them.
5. Record the pod evidence under the existing pre-Experiment-35 profile. The
   comparison uses Magika 1.0.3, ONNX Runtime 1.28.0 and ten fixed input files.
   The 2026-11-09 pod exposed 32 CPUs, unlike the earlier 96-CPU observation.

## Consequences

### Positive

- Individual detection improved from 5.05 ms to 1.74 ms per file at eight
  threads on the verification pod: 2.9 times faster.
- Batched detection improved from 2.24 ms to 1.89 ms per file: 16% faster.
- The production scanner used the measured options: eight intra-operation
  threads, one inter-operation thread and the CPU provider.
- Smaller hosts retain their visible CPU count rather than receiving extra
  worker threads.

### Negative

- The integration depends on a private construction hook in the pinned Magika
  package. A future Magika upgrade must check that hook before changing the
  pin.
- Hosts with a genuine allocation above eight CPUs cannot use more than eight
  threads for Magika without a new measured decision.
- The earlier 96-CPU pod was unavailable for a direct A/B rerun. The new
  32-CPU pod confirms the mechanism and improvement, with a smaller baseline.

### Neutral

- The new unit tests verify constructor options, not timing. Portable tests
  do not depend on host CPU speed.
- No new dependency, settings key or public API is introduced.

## Alternatives Considered

| Option | Rejected because |
| --- | --- |
| Keep automatic ONNX allocation | The uncapped control was slower and the thread count follows visible host CPUs rather than the pod allocation. |
| Set `OMP_NUM_THREADS` | It is process-wide, depends on import order and does not explicitly bind the Magika session. |
| Construct Magika then replace its session | Pays for the uncapped session first and creates an unnecessary second session. |
| Use twelve threads | It matched eight-thread latency within measurement noise, while increasing the resource ceiling and load time. |
| Add a user setting | No operator can derive a useful pod allocation from the exposed container metrics. A fixed measured ceiling needs no configuration. |
| Cap every ONNX path | Reranker and OCR sessions have no matching failure evidence in issue #201. |

## Gate evidence

Before this change, on the earlier 96-CPU pod: individual detection 108.8 ms
per file; batched detection 49.9 ms per file. The new 32-CPU pod comparison,
2026-11-09:

| Configuration | Individual mean per file | Batched per file | Model load |
| --- | ---: | ---: | ---: |
| Uncapped, automatic intra/inter | 5.05 ms | 2.24 ms | 29.7 ms |
| Eight intra, one inter | 1.74 ms | 1.89 ms | 13.6 ms |
| Twelve intra, one inter | 1.73 ms | 1.85 ms | 50.3 ms |

Each configuration ran in a fresh process. Thirty individual predictions and
one ten-file batch returned identical labels. The real production scanner used
the eight/one options on all ten files. Raw JSON, environment facts, scripts,
patch and verified checksums are in
`~/Development/DATA/omrs/experiments/pre-exp35-ingest-profile-2026-11-08/pod/onnx-thread-cap-2026-11-09/`.
Pod `2bdjprmfnv46x4` ran at a quoted $0.89/hour and was deleted after the
verified outputs were copied. The account's temporary SSH key was removed.
The billing API had not posted the final amount when checked.

## Addendum 2026-11-10: the reranker gets the same cap

The Experiment 35 smoke run on a 96-CPU RTX 4090 pod showed the ONNX
cross-encoder reranker had no cap. A search with the reranker on took about
20 s; with the reranker off it took 0.2 s. On the same pod, 50 query-passage
pairs of `cross-encoder/ms-marco-MiniLM-L-6-v2` took 24.1 to 26.7 s with the
default session and 1.2 to 1.3 s with eight intra-op threads and one inter-op
thread.

The cap now has one source, `src/omrs/integrations/onnx_threads.py`
(`capped_session_options`). Magika and the reranker both build their CPU
session options there. Test: `tests/unit/test_reranker_thread_cap.py`.

## References

- [ADR-117](117-magika-in-process-detection.md)
- [ADR-068](068-pin-magika-content-detection.md)
- `src/omrs/integrations/magika.py`
- `src/omrs/integrations/onnx_threads.py`
- `tests/unit/test_magika_thread_cap.py`
- `openspec/changes/onnx-pod-thread-cap/`
- [ONNX Runtime threading management](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)
