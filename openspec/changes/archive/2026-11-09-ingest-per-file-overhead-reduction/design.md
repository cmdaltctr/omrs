# Design: ingest-per-file-overhead-reduction

## Context

`pre-exp35-harness-and-answer-fixes` profiled a 200-file FreshStack ingest and found:

- The Markdown splitter was rebuilt per document: fixed by `lru_cache` in that PR.
- Magika's subprocess starts on every `ingest_path_async` call: 0.071 s per call on the Mac, 8% of the per-file time. Unconfirmed on the pod but a leading suspect for the 0.79 s unexplained cost the Mac cannot reproduce.
- LanceDB reopens the collection 12 times per ingested file: 0.022 s, touches five modules.

Profile artefacts: `~/Development/DATA/omrs/experiments/pre-exp35-ingest-profile-2026-11-08/`.

## D1. Replace the Magika subprocess with the Python API

`integrations/magika.py` today calls `magika -r <dir> --jsonl` via `subprocess.run`. ADR-068 decision 2 chose the subprocess to keep "model lifecycle outside the application process". That choice was made when the in-process alternative was hypothetical; the profile now gives a measured cost and the in-process API is stable.

New ADR (supersedes ADR-068 decisions 2 and 6):

- `magika.Magika()` is constructed once per process, lazily, via a module-level `functools.lru_cache(maxsize=1)` wrapper. The instance is kept alive; ONNX Runtime loads the model once.
- `scan_with_magika` walks the directory itself (skipping `_EXCLUDED_DIRS`) and calls `m.identify_paths(files)` once for all files under the root; a single-file root yields the `.` key (the existing suffix-based fallback if Magika is unavailable stays in place). The JSONL parsing contract is replaced by reading `.output.label`, `.output.group`, `.output.is_text`, and `.status` from each `MagikaResult`. Label equality with the CLI is verified by a test that runs both paths on the ADR-068 frozen acceptance corpus (same labels required).
- The `MAGIKA_BINARY` injectable is still read for the existing `_is_magika_available` check (ADR-068 decision 7 boundary normalisation stays in the Python path).
- File size: `magika.py` is 257 lines. The JSONL parsing block removed and `identify_paths` added keeps it under 500 lines.

Expected saving: 0.071 s removed per call on the Mac. The pod measurement (D2) will say whether it also removes the 0.79 s pod cost.

## D2. Pod measurement step (operator-gated)

A short pod session — same shape as D9 from `pre-exp35-harness-and-answer-fixes` (RTX 4090 secure, $0.89/h, live price at create time) — runs the profile script from `experiments/pre-exp35-ingest-profile-2026-11-08/scripts/` on Linux. Steps:

1. `nproc` and `os.cpu_count()` to check whether ONNX Runtime binds to all 56 vCPUs of the host rather than the 12 vCPU floor.
2. `time magika -r <file> --jsonl` (one file) to measure the subprocess cost in the same Linux environment.
3. The profile control pass (spans only, 10 FreshStack files) under both the old code (subprocess) and the new code (Python API) on the same pod to give a before/after on Linux.
4. Copy outputs, verify checksums, delete the pod in the same turn.

Outputs go under `~/Development/DATA/omrs/experiments/pre-exp35-ingest-profile-2026-11-08/pod/`. The step is gated: the operator approves the quoted hourly price before `create-pod`. The operator does not have to merge or approve anything else before this step runs.

## D3. LanceDB store reopens (assessment)

The profile showed 12 collection opens and 3 `count_where` calls per file (0.022 s). A fix would need a per-operation table handle shared across the five modules that open the collection (`store.py`, `meta.py`, `paged.py`, `fts.py`, `epoch.py`) while respecting the cross-process BM25 cache invalidation rule (root gotcha 14, ADR-BM25). That is not small or local: it requires a handle-sharing protocol and a careful cache invalidation boundary. The saving (~4 ms/file) is not worth that risk before the 35a freeze. A proposed issue is filed instead; this change does not implement D3.

## Risks

- [Python API labels differ from CLI on a few file types] → the label-equality test on the frozen acceptance corpus (16 files) will catch it. A mismatch blocks the PR.
- [ONNX Runtime model load time adds to the first call] → the cache ensures it is one-time per process. The profile control pass measures this.
- [Pod pod-only cost is something other than Magika] → D2 step 2 (`time magika`) confirms or refutes the hypothesis. If another cause is found, D2 names a follow-up issue.
