# Tasks

## 1. New ADR and spec gate

- [x] 1.1 Write the new ADR superseding ADR-068 decisions 2 and 6. Use `s-adr`. Record the label-equality test requirement, the process-level cache, and the profile evidence. Set status Proposed. Verify `openspec validate --strict` passes.
- [x] 1.2 Create the feature worktree from the current `v3` HEAD: `omrs-v3-feat-ingest-per-file-overhead-reduction`, branch `feat/ingest-per-file-overhead-reduction`.

## 2. Replace Magika subprocess with the Python API

- [x] 2.1 Write a label-equality test first (`tests/test_magika_api_label_equality.py`). It runs both paths on the frozen acceptance corpus from ADR-068 (`scripts/magika_label_smoke.py` fixture set or a small inline copy). Verify it fails when the API path is not yet wired.
- [x] 2.2 Add a process-level cache test: two `detect_content_types` calls in the same process construct `magika.Magika()` at most once. Verify it fails before the change.
- [x] 2.3 Implement: in `integrations/magika.py`, add a module-level `_get_magika_instance()` using `functools.lru_cache(maxsize=1)`. Replace the `subprocess.run` block in `scan_with_magika` with `m.identify_paths(files)`, keeping the suffix fallback, the `_EXCLUDED_DIRS` filter, and the boundary normalisation from ADR-068 decision 5. Remove the JSONL parsing block. Keep `_magika_binary` and `_resolve_magika` for `_is_magika_available` only.
- [x] 2.4 Run the label-equality test and the cache test; confirm both pass. Run the existing Magika tests (`tests/test_magika*.py` if any). Mutation check: remove the `lru_cache`; the cache test must fail. Mutation check: skip the suffix normalisation; the label-equality test must catch it.
- [x] 2.5 Update the ADR status to Accepted, record the gate evidence (label-equality test pass, profile before/after), and commit.

## 3. Pod measurement (operator-gated)

Do not start this group until group 2 is merged, the operator has seen the quoted price and said go.

- [ ] 3.1 Live reads at create time: `get-gpu-type` and `get-capacity` for the RTX 4090 (secure cloud). Quote the hourly price. Wait for the operator's go.
- [ ] 3.2 Create a pod. On the pod, in one chained script: run `nproc`, `os.cpu_count()`, `time magika -r <file> --jsonl` (one FreshStack file). Then run the profile control pass (10 FreshStack files, spans only) with the subprocess code, then reinstall with the new Python API code and run the same 10-file pass again. Write outputs atomically to `/workspace/pod-profile/`. Copy outputs back, verify checksums, delete the pod in the same turn. Never end a turn while the pod runs.
- [ ] 3.3 Save outputs under `~/Development/DATA/omrs/experiments/pre-exp35-ingest-profile-2026-11-08/pod/` with SHA-256. Write a one-page `pod-summary.md` naming the largest per-file cost on Linux, before and after.
- [ ] 3.4 If ONNX thread count is confirmed as the pod-only cause, open a GitHub issue: "ONNX Runtime on pod uses all host vCPUs instead of the floor (affects ingestion time)" and record it in the PR.

## 4. LanceDB proposed issue

- [ ] 4.1 Open a GitHub issue: "LanceDB store reopens the collection about 12 times per ingested file (0.022 s each)". Link to the profile artefacts. Record score likelihood 10 x impact 1 = 10.

## 5. Close

- [ ] 5.1 `./scripts/local_ci.sh` passes. `openspec validate --all --strict` passes.
- [ ] 5.2 PR into `v3`; CI green; CodeRabbit handled. Do not merge without the operator's word.
