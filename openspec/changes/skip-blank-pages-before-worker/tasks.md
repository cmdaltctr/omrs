# Tasks

## 1. Blank test module

- [x] 1.1 Write failing tests in `tests/unit/test_blank_pages.py` first. Fixtures are small generated images: an empty grain-noise page, an empty sheet on a dark border, a page with one dark 12 pt word, a page with an 11-character header near the top, a page of faint pencil-like strokes, and a dense text page. Add a mutation check: a page with one dark 12 pt word must never score below the threshold. Verify: the tests fail because the module does not exist.
- [x] 1.2 Add `src/omrs/integrations/pdf/blank_pages.py` with the score from design.md (1000 px long side, 9 x 9 closing, depth 40, speck removal, border-connected marks removed, threshold 1.5e-4), `BLANK_PAGE_TEST_VERSION = 1`, batched LiteParse renders of 16 pages, and "not blank" on any render or score error with one warning for each file. Add the module's row to the integration inventory in `docs/guides/architecture.md`. Verify: `uv run pytest tests/unit/test_blank_pages.py tests/test_strategy_registration_inventory.py -q` passes, and the blank tests fail again when the border removal step is deleted (the dark-border fixture turns "not blank").

## 2. Page unit and the fifth count

- [x] 2.1 Write failing tests in `tests/unit/test_page_unit_seam.py` and `tests/unit/test_page_merge.py`: a blank flagged page reaches neither `local_ocr` nor `_escalated_worker_text`; it counts `ocr_pages_blank`; the five counts sum to `page_count`; a render error routes the page as today; the `document` unit emits no blank count. Update the existing four-count assertions to five. Verify: the new tests fail on the current code.
- [x] 2.2 Add `PAGE_SOURCE_BLANK` and `ocr_pages_blank` to `page_routing.py`, and call the blank test in `ocr_routing.py` after `flagged` and before `split_page_routes`, keeping the file at 500 lines or fewer. Verify: the tests from 2.1 pass and `uv run pytest tests/test_file_size_ceiling.py -q` passes.
- [x] 2.3 Update the count table and the count paragraph in `docs/guides/ingestion.md` to five counts, and state the page-number and faint-single-word limits. Verify: `grep -n "ocr_pages_blank" docs/guides/ingestion.md` shows both places.

## 3. Index identity

- [x] 3.1 Write failing tests: under the `page` unit the identity changes and the routing payload carries `blank_page_test`; under the `document` unit the identity equals the pinned baseline in `tests/unit/test_index_identity_baseline.py`. Verify: the page-unit test fails on the current code and the document-unit test passes.
- [x] 3.2 Add `ocr_pages_blank` to `EXCLUDED_EMBED_METADATA_KEYS` and `PAGE_ROUTING_ONLY_EMBED_KEYS`, and add `blank_page_test` to the page-unit block of `ocr_routing_payload`. Verify: the tests from 3.1 pass and `_INDEX_IDENTITY_SCHEMA` is still 6.

## 4. Measurement after build

- [x] 4.1 Rerun the 10-page `rf06` extract (original pages 20, 29, 33, 40, 46, 50, 60, 70, 80, 86; blank sheets 20, 40, 70, 80) in page mode with the PyTorch `dots-mocr` engine on `v3`. Record a same-engine baseline of the extract (page texts and engine calls) before the change lands. Verify after: 4 pages count `ocr_pages_blank`, 0 pages count unresolved, the engine log shows no call for the 4 blank pages, the text of the other 6 pages is identical to the baseline, and the report states the engine seconds saved.
- [x] 4.2 Run the blank test through the real module on all 40 Experiment 33 documents (render and score only, no OCR model). Verify: every skipped page has an empty frozen reference transcription or a reference of at most 2 characters, no page with 3 or more reference characters or `illegible` legibility is skipped, and the counts match design.md (37 skipped of 701 flagged).
- [ ] 4.3 Run `./scripts/local_ci.sh` and `openspec validate skip-blank-pages-before-worker --strict`. Verify: both pass, with no `SKIPPED` step.

## Workflow follow-up

- Open a pull request from `feat/skip-blank-pages-before-worker` into `v3`. Do not merge; wait for the operator.
- Watch CI until every check ends, and answer every review thread.
- Note the fifth count in the ADR-069 counts paragraph through a follow-up ADR amendment, if the operator wants one.
- Archive the change after merge and verification.
