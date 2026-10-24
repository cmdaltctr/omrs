# Timing

All runs use the CI environment variables from `scripts/local_ci.sh`, on the same Mac (15 cores). The fast suite runs with `-n auto --maxprocesses=8`.

## Before (2026-10-24, base `0e2e3aee`)

| Step | Wall time | Result |
|---|---|---|
| Fast suite | 231 s (3 min 51 s) | 8,051 passed, 152 skipped |
| Clean-base tripwire | 217 s (3 min 37 s) | 5 passed |

The 25 slowest tests:

| Time | Test |
|---|---|
| 120.1 s | `test_ocr_error_boundary.py::test_post_dispatch_timeout_is_a_structured_error` |
| 44.1 s | `test_retrieval.py::TestListCollections::test_list_collections_scans_multiple_metadata_pages` |
| 30.1 s | `test_ingestion_stage3.py::test_reader_normalisation_identity_reprocesses_then_skips[lancedb-schema]` |
| 30.0 s | `test_watcher.py::TestShutdownTimeout::test_stop_timeout_on_hung_ingestion` (out of scope) |
| 30.0 s | `test_ingestion_stage3.py::test_reader_normalisation_identity_reprocesses_then_skips[chroma-toggle]` |
| 29.9 s | `test_ingestion_stage3.py::test_reader_normalisation_identity_reprocesses_then_skips[lancedb-version]` |
| 29.7 s | `test_ingestion_stage3.py::test_reader_normalisation_identity_reprocesses_then_skips[chroma-schema]` |
| 29.6 s | `test_document_backends.py::TestLocalMetadataParity::test_supported_types_txt_and_md` |
| 29.5 s | `test_ingestion_stage3.py::test_reader_normalisation_identity_reprocesses_then_skips[chroma-version]` |
| 29.5 s | `test_ingestion_stage3.py::test_reader_normalisation_identity_reprocesses_then_skips[lancedb-toggle]` |
| 28.9 s | `test_core_coverage_v2.py::TestAzureDocumentBranch::test_markdown_uses_the_markdown_chunk_size` |
| 24.3 s | `test_ingestion.py::TestListDocuments::test_list_documents_scans_multiple_metadata_pages` |
| 24.1 s | `test_engine_isolation.py::test_source_replacement_uses_engine_embedder` |
| 23.9 s | `test_engine_isolation.py::test_close_engine_a_leaves_engine_b_functional` |
| 23.8 s | `test_engine_isolation.py::test_interleaved_operations_never_observe_the_other_model` |
| 22.9 s | `test_engine_isolation.py::test_two_engine_full_path_isolation` |
| 15.4 s | `test_magika_settings_injection.py::test_binary_transition_removes_previously_indexed_rows` |
| 14.9 s | `test_markdown_chunking.py::test_heading_prepend_enabled_adds_heading_prefix` |
| 14.7 s | `test_core_coverage_v2.py::TestAzureDocumentBranch::test_azure_failure_degrades_to_local` |
| 14.5 s | `unit/test_ingestion_embedding_identity.py::test_ingest_reaches_write_nodes_with_the_supplied_identity` |
| 14.4 s | `unit/test_ingestion_embedding_identity.py::test_ingest_without_identity_keeps_the_composed_identity` |
| 8.2 s | `test_async_ingest_responsiveness.py::TestResponsivenessRegression::test_blocking_call_causes_responsiveness_failure` (out of scope) |
| 6.1 s | `test_ingestion_stage3.py::test_generated_corpus_retains_only_one_source_node_set[40]` |
| 5.3 s | `unit/test_dotenv_isolation.py::test_a_dotenv_in_the_working_folder_does_not_leak_into_tests[...]` |
| 5.1 s | `unit/test_process_launcher.py::test_ready_timeout_stops_the_process` (out of scope) |

## Guard mutation check (task 3.5)

The metadata default was removed from the factory for one run, and the tests that were slow before were run again. Result: 21 failed in 4.96 s.

- 19 tests failed with `Unplanned LLM metadata strategy 'llamaindex' dispatched through omrs.core.metadata.extractor`, each in 0.05 to 0.07 s (12 to 46 s before):
  - the 2 `scans_multiple_metadata_pages` tests and the 2 `TestAzureDocumentBranch` tests
  - the 4 `test_engine_isolation.py` tests
  - `test_reader_normalisation_identity_reprocesses_then_skips`, all 6 parameters
  - `TestLocalMetadataParity::test_supported_types_txt_and_md`
  - `test_binary_transition_removes_previously_indexed_rows`
  - the 2 `unit/test_ingestion_embedding_identity.py` tests
  - `test_heading_prepend_enabled_adds_heading_prefix`
- 2 failures were the factory-default tests of task 2.1, as expected.

The default was restored after the run.

## Tripwire mutation check (task 5.4)

| Mutation | Tripwire result |
|---|---|
| One fast test marked `skip`, report written after the edit | Fails: `base executed count drifted: 8064` (expected 8065 on this machine) |
| Same report, test file restored after the report was written | Fails: `JUnit report ... is stale: tests/unit/test_settings_factory_defaults.py changed after it was written` |

## After (2026-10-24, feature branch)

| Step | Before | After | Result after |
|---|---|---|---|
| Fast suite (wall) | 231 s | 55 s | 8,065 passed, 152 skipped |
| Clean-base tripwire, report mode | 217 s | 8 s | 5 passed |
| Clean-base tripwire, own-run mode (no report) | 217 s | 63 s | 5 passed |

The fast suite has 14 more tests than before (8,051 + 14 = 8,065).

The 12 slowest tests after the change:

| Time | Test |
|---|---|
| 30.1 s | `test_watcher.py::TestShutdownTimeout::test_stop_timeout_on_hung_ingestion` (out of scope) |
| 8.3 s | `test_async_ingest_responsiveness.py::...::test_blocking_call_causes_responsiveness_failure` (out of scope) |
| 6.0 s | `test_ingestion_stage3.py::test_generated_corpus_retains_only_one_source_node_set[40]` |
| 5.1 s | `unit/test_process_launcher.py::test_ready_timeout_stops_the_process` (out of scope) |
| 4.2 s | `test_ocr_error_boundary.py::test_post_dispatch_failures_are_structured_per_file_errors[close-stdout-...]` |
| 4.1 s | `test_ocr_worker_managed.py::test_fatal_modes_invalidate_and_respawn[close-stdout]` |
| 4.0 s | `unit/test_mcp_no_process_defaults.py::test_every_tool_works_with_process_defaults_cleared` |
| 3.8 s | `test_ingestion_stage3.py::test_replacement_over_one_hundred_rows_removes_all_stale_rows` |
| 3.1 s | `test_mcp_tools.py::test_search_after_ingest_returns_results` |
| 3.0 s | `test_metadata_extractor.py::TestOllamaExtraction::test_ollama_unreachable` (mocked; retry back-off sleeps) |
| 2.6 s | `test_bm25_validity_token.py::test_separate_process_mutation_during_build_is_not_cached` |
| 2.6 s | `test_bm25_validity_token.py::test_separate_process_recreation_during_build_is_not_cached` |

No test from the old metadata or OCR waits is left in the list. The OCR timeout test now takes 1.1 s (120.1 s before).

## CI (PR #126, run 40132303145)

All 23 jobs passed (Tier 2 is skipped on pull requests). Step times compared with the last `v3` run before this change:

| Job | Step | Last `v3` run | PR #126 |
|---|---|---|---|
| `test (ubuntu-latest)` | fast suite | 767 s | 398 s |
| `test (ubuntu-latest)` | tripwire | 712 s | 20 s |
| `test (macos-latest)` | fast suite | not measured | 315 s |
| `test (macos-latest)` | tripwire | not measured | 23 s |
| `Floor resolution` (base) | fast suite | not measured | 311 s |
| `Floor resolution` (base) | tripwire | not measured | 19 s |
