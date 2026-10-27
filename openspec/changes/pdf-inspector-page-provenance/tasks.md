# Tasks

## 0. Set up

- [x] 0.1 Create worktree `../omrs-feat-pdf-inspector-page-provenance` on branch `feat/pdf-inspector-page-provenance` from `v3`, and run `uv sync --frozen --extra web` in it. Verify: `git rev-parse --show-toplevel` and `git branch --show-current` name the new worktree and branch.
- [x] 0.2 Save the fast-suite test IDs to `openspec/changes/pdf-inspector-page-provenance/evidence/test-ids-before.txt` (`uv run --no-sync pytest -m "not slow" --collect-only -q`). Verify: the file exists and is not empty.
- [x] 0.3 Confirm the installed pdf-inspector is 1.17.0 and that `extract_pages_markdown` numbers `PageMarkdown.page` from 0 on `tests/fixtures/pdf_baseline/evaluation/eval_mixed.pdf`. Save the output to `evidence/library-check.txt`. Verify: the file shows version 1.17.0 and page indices `0, 1`.

## 1. Registry declarations (design D7, D9)

- [x] 1.1 Write tests first in `tests/test_reader_text_format.py`: `describe("pdf_inspector")["page_provenance"]` is `True`; `describe(name)["output_revision"]` is 2 for `pdf_inspector` and 1 for `liteparse`, `pypdf` and `pypdfium2`; `register()` without `output_revision` gives 1. Change the existing `("pdf_inspector", False)` case to `True`. Verify: the new and changed tests fail on current code.
- [x] 1.2 Add the keyword `output_revision: int = 1` to `register()` and to `describe()` in `src/omrs/integrations/pdf/registry.py`. Set `page_provenance=True` and `output_revision=2` for `pdf_inspector`. Add `declared_output_revision(reader)` to `factory.py`, next to `declared_text_format`, so `auto` resolves first. Verify: 1.1 tests pass.
- [x] 1.3 Change the `pdf_inspector` row of the matrix in `docs/guides/configuration.md` to `Yes: one document per page; the whole-document fallback and worker-read documents have no page`. Verify: `uv run --no-sync pytest tests/test_page_provenance.py::TestDocsAndRegistryAgree -q` passes.

## 2. Adapter emits page documents (design D1, D2, D3)

- [x] 2.1 Write tests first in `tests/unit/test_pdf_inspector_reader.py` with a stubbed `pdf_inspector` module (pages numbered 0, 1, 2): 3 page documents in order; `page` is `1, 2, 3` (int) and `page_label` is `"1", "2", "3"`; each text is only its own page; an empty or whitespace page emits no document; every document carries the same `pdf_reader`, `pdf_type`, `pdf_confidence`, `page_count`, `pages_needing_ocr`, `file_path`, `file_name`; `process_pdf` and `extract_pages_markdown` are each called once. Verify: the tests fail on current code.
- [x] 2.2 Write tests first for the fallbacks (design D3): the per-page call raises, so one document with the `process_pdf` Markdown, no `page` or `page_label`, and a warning naming the file; the per-page call gives no text while `process_pdf` has text, so the same; nothing has text and the file is not `text_based`, so one empty document with the evidence and no page keys; per-page length differs from `page_count`, so a warning and pages numbered from `PageMarkdown.page`. Verify: the tests fail on current code.
- [x] 2.3 Rewrite `PdfInspectorReader.load_data` in `src/omrs/integrations/pdf/pdf_inspector.py`: call `process_pdf` once and `extract_pages_markdown` once; build page documents through one helper that adds 1 to `PageMarkdown.page`, with a comment naming the 0-based source; make `_complete_ocr_pages` read the full-scan count from the result already fetched. Update the module and class docstrings. Keep the file under 500 lines. Verify: 2.1 and 2.2 tests pass.
- [x] 2.4 Mutation check the page conversion: remove the `+ 1`, run 2.1 tests, restore; change it to `+ 2`, run 2.1 tests, restore. Record both failing outputs in `evidence/mutation-page-offset.txt`. Verify: each mutant fails at least one test, and the restored code passes.
- [x] 2.5 Update `tests/unit/test_pdf_inspector_full_scan.py` for the new call count. Keep the spec rule: for `text_based` PDFs longer than 8 pages the count comes from the per-page result; otherwise it stays the `process_pdf` count, also when the per-page result flags more pages (add this case). Verify: tests fail first where the expected call count changed, then pass.
- [x] 2.6 Replace `TestPdfInspectorReportsNoPage` in `tests/test_page_provenance.py` with: `smoke_text.pdf` gives one document with `page` 1 and `page_label` `"1"`; a stubbed per-page failure gives no `page_label`; `page_count` is present in both. Add a real-file test: `eval_mixed.pdf` gives `page` 1 for its text page. Update `test_adapter_metadata_contract_on_text_pdf` in `tests/unit/test_pdf_baseline_fixtures.py` for the two new keys. Verify: the tests fail before 2.3 and pass after it.

## 3. Fallback chain keeps pages (design D4)

- [x] 3.1 Write tests first in `tests/unit/test_pdf_inspector_reader.py`: liteparse recovers pages 1 and 3 of 3, so 2 documents with `page` 1 and 3 and liteparse's `page_label`; pypdf recovers 3 page documents whose own labels are `"i"`, `""` (empty text) and `"iii"`, so 2 documents with `page` 1 and 3 and `page_label` `"1"` and `"3"`; every recovered document carries `extraction_fallback_backend`, `pages_needing_ocr` 0 and `pages_needing_ocr_before_fallback`; a chain that recovers nothing still emits one empty document with the original count. Verify: the tests fail on current code.
- [x] 3.2 Change the rescue branch in `pdf_inspector.py` to keep one document per recovered page as design D4 states. Number pypdf pages by position before empty pages are dropped. Verify: 3.1 tests and the existing rescue tests pass.
- [x] 3.3 Mutation check the pypdf numbering: number after the empty pages are dropped, run 3.1 tests, restore. Append the output to `evidence/mutation-page-offset.txt`. Verify: the mutant fails a test.

## 4. OCR routing keeps pages (design D5)

- [x] 4.1 Write tests first in `tests/test_ocr_routing_seam.py` (document unit): fast path with 3 page documents returns 3, each with `ocr_required` false, `ocr_backend` `pdf_inspector` and its own `page`; degraded path returns the native page documents, each with `ocr_required` true and `ocr_used` false; maths count is on every document; worker path returns one document with no `page` or `page_label` and with `page_count`. Verify: the tests fail on current code.
- [x] 4.2 Write tests first in `tests/unit/test_page_unit_seam.py` (page unit): a 5-page PDF with page 3 local and page 4 worker gives 5 documents, page 3 carries the local text and `page` 3, page 4 the worker text and `page` 4; the four counts sum to `page_count` on every document; a page with no text from any tier emits no document; the last-resort rescue returns the wrapped reader's page documents with all-native counts. Verify: the tests fail on current code.
- [x] 4.3 Change `OcrRoutedPdfInspector` in `ocr_routing.py` to stamp diagnostics on every document, and `_page_unit_documents` to emit one document per page from its `PageResult` list. Keep `merge_pages` for the counts and the backend. If `ocr_routing.py` passes 500 lines, move the page-unit emission into `page_routing.py`. Verify: 4.1, 4.2 and the existing seam, maths and error-boundary tests pass, and `tests/test_file_size_ceiling.py` passes.
- [x] 4.4 Mutation check the page unit: emit `page` from the list position instead of `PageResult.page`, run 4.2 tests, restore. Append the output to `evidence/mutation-page-offset.txt`. Verify: the mutant fails a test.

## 5. Index identity (design D7)

- [x] 5.1 Write tests first in `tests/unit/test_index_identity_baseline.py`: a PDF source under `pdf_inspector` carries `parser.pdf_reader_output_revision` 2; under `pypdf` it carries 1; a `.md` source carries no such key and its digest equals the digest before the change (pin it); `_INDEX_IDENTITY_SCHEMA` is still 6; a monkeypatched revision change gives a different PDF digest. Verify: the tests fail on current code.
- [x] 5.2 Write tests first in `tests/test_ingestion_stage3.py`, next to the schema 5 to 6 test: ingest a PDF and a `.md` file with the revision resolver patched to return `None` (an index built before this change); ingest again unpatched, so the PDF is not `skipped_unchanged` and the `.md` file is; a third run reports both `skipped_unchanged`. Add a case in `tests/unit/test_ingestion_graph_pdf_identity.py`: a Read document step with `pdf_reader=pypdf` gives revision 1 in the identity. Verify: the tests fail on current code.
- [x] 5.3 Add `resolve_pdf_reader_revision(file_path, *, settings)` to `core/ingestion/backends/orchestrator.py` (same backend and suffix test as `_declared_text_format`), pass its value from `prepare_source` in `sources.py`, and add the optional `pdf_reader_revision` argument to `build_index_identity`, which writes the key only when it is not `None`. Update the module docstring note. Verify: 5.1 and 5.2 tests pass, and `uv run --no-sync lint-imports` passes.

## 6. Ingestion end to end and guides

- [x] 6.1 Write a test in `tests/test_page_provenance.py`: ingest a 2-page PDF with `pdf_reader="pdf_inspector"` and `extraction_mode="disabled"`; every stored chunk has `page_label` `"1"` or `"2"`; no chunk text holds text from both pages; a dense search for a page-2 phrase returns `page_label` `"2"`. Create the PDF in `tmp_path` from the existing fixtures or a helper; do not add a large binary. Verify: the test fails on `v3` and passes on the branch.
- [x] 6.2 Check that normalisation runs per page: a test with a page document holding `<u>HEADER</u>` gives a chunk without `<u>`, with its `page` kept. Verify: the test passes. `NORMALISER_VERSION` stays 2.
- [x] 6.3 Update `docs/guides/ingestion.md`: the reader table row and the paragraph under it say `pdf_inspector` emits one document per page with `page` and `page_label`, the whole-document fallback and worker-read documents carry no page, and a chunk never crosses a page break. Add one line on the one-time rebuild of PDF sources. Verify: `grep -n "one document per PDF" docs/guides/ingestion.md` returns nothing, and `uv run --no-sync pytest tests/test_docs_references.py -q` passes.
- [x] 6.4 Check `docs/guides/configuration.md`, `docs/guides/mcp-tools.md` and `docs/guides/architecture.md` for text that says `pdf_inspector` has no page. Fix each hit. Verify: `grep -rn -i "pdf_inspector" docs/guides | grep -i -E "no page|one document per (file|pdf)" | grep -v "Yes: one document per page"` returns nothing (the matrix row of task 1.3 rightly says worker-read documents have no page).

## 6a. Heading context across pages (design D11)

- [x] 6a.1 Write tests first for the shared helper: a page that ends inside `# A` / `## B` passes `A > B` (in the existing `header_path` format) to the next page; a `## C` on the next page closes `B` and keeps `A`; a `# D` closes both; pages from two sources never share a stack; out-of-order pages are sorted first; a gap in page numbers ends the inherited stack. Verify: the tests fail before the helper exists.
- [x] 6a.2 Implement the helper in `src/omrs/core/chunking/` (new module, under 500 lines, Google docstrings). Verify: 6a.1 tests pass.
- [x] 6a.3 Write tests first for both chunking paths (legacy Markdown and model-token): a 3-page PDF whose sections cross pages gives, for every chunk, the same `header_path` as chunking the joined whole-document text. Then wire the helper into `core/chunking/markdown.py` and `core/chunking/model_token.py`. Verify: the tests fail first, then pass; a mutation that drops the inherited stack makes them fail.
- [x] 6a.4 Check that a single-document source (any other reader, any non-PDF file) chunks exactly as before. Verify: the existing chunking and identity tests pass unchanged.

## 7. Decision record

- [x] 7.1 Write `docs/adr/<next>-pdf-inspector-emits-page-documents.md` (next free number, 104 on 27 October 2026; status Proposed). Record design D1 (with the call-count measurements), D4, D5, D7 (with rejected options), D8 (page-break measurements) and the two risks on headings and running headers. Name ADR-050, ADR-066 and ADR-069 as amended. Add the row to `docs/adr/ADR_README.md`. Verify: `uv run --no-sync pytest tests/test_docs_references.py -q` passes.
- [x] 7.2 Add an "Amended by ADR-<next>" status note to ADR-050, ADR-066 and ADR-069 and their rows in `ADR_README.md`. Do not rewrite their decisions. Verify: `grep -n "ADR-<next>" docs/adr/050-*.md docs/adr/066-*.md docs/adr/069-*.md` shows one note in each.

## 8. Integration checks

- [x] 8.1 Run the adapter on Experiment 3's 4 PDFs and 10 PDFs from Experiment 42's corpus with a short script in the scratchpad. Record per file: page documents, empty pages skipped, `page_count`, `pages_needing_ocr` before and after the change. Save to `evidence/real-pdf-check.txt`. Verify: `pages_needing_ocr` and `pdf_type` are equal before and after on every file, and page documents have `page` from 1.
- [x] 8.2 Re-pin the tripwire: collect the fast-suite IDs again, diff them against `evidence/test-ids-before.txt`, save `evidence/test-ids-diff.txt`, and change `_BASE_EXECUTED` (and `_WEB_EXTRA_CASES` if a new test needs fastapi) in `tests/test_clean_base_tripwire.py` by the counted difference, with a dated comment under 100 characters. Verify: `uv run --no-sync pytest tests/test_clean_base_tripwire.py -q` passes.
- [x] 8.3 Run `./scripts/local_ci.sh`. Verify: every step passes and no step prints `SKIPPED`, or the skip is named in the PR body.
- [x] 8.4 Run `openspec validate pdf-inspector-page-provenance --strict` and `openspec validate --all --strict`. Verify: both pass, or a failure in `--all` is also present on `v3` before this change and is named in the PR body.

## Workflow follow-up

- Open the PR against `v3` with `gh pr create --base v3`. Name the one-time rebuild of PDF sources, the heading carry-over and the running-header risk in the body.
- After merge, re-ingest the PDF folders of the live `~/.omrs` app (Critical Gotcha 17 and the live-reinstall memory apply).
- The pipeline sweep, Part A, measures retrieval with per-page output and heading carry-over.
- Archive with `openspec-archive-change`. It merges the deltas into `openspec/specs/pdf-reader/` and `openspec/specs/async-ingestion/`.
