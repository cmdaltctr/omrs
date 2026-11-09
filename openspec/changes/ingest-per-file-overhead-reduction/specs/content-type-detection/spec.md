## ADDED Requirements

### Requirement: Detection runs in-process, once per call, with the same labels

When Magika is available, content-type detection SHALL use the Python API (`magika.Magika`) to detect all files in one call, rather than spawning a subprocess for each `ingest_path_async` call. The Python API object SHALL be cached at the process level and initialised at most once. The labels, groups and `is_text` values returned SHALL equal those from the CLI path on the same files.

#### Scenario: In-process detection produces the same label as the CLI

- **WHEN** a Python file is detected via the Python API and via the CLI on the same machine
- **THEN** the group, label and is_text values MUST be equal

#### Scenario: Process-level cache used

- **WHEN** two separate `detect_content_types` calls run in the same process
- **THEN** `magika.Magika()` MUST be constructed at most once (no second initialisation)

#### Scenario: Subprocess fallback path still works

- **WHEN** the Python API raises during initialisation
- **THEN** the detection MUST fall back to the suffix map, as before this change

### Requirement: Pod-overhead measurement runs before the 35a freeze

A short pod session SHALL run the profile script from `experiments/pre-exp35-ingest-profile-2026-11-08/scripts/` on a Linux RTX 4090 pod (same shape as D9) and record: `nproc`, `os.cpu_count()`, `time magika -r <file> --jsonl`, and per-stage spans for a 10-file FreshStack ingest. The session SHALL stop the pod as soon as outputs are copied back. This task is operator-gated: the operator quotes and approves the pod price before any `create-pod` call.

#### Scenario: Pod measurement names the pod-only cost

- **WHEN** the pod profile script finishes
- **THEN** the summary MUST name the largest per-file cost and its source (Magika subprocess, ONNX thread count, or other), or state that the 0.79 s could not be reproduced

#### Scenario: Pod deleted after outputs are copied

- **WHEN** the profile outputs are copied back and their checksums verified
- **THEN** the pod MUST be deleted in the same turn
