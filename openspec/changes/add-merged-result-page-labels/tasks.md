# Tasks

## 1. Assembly

- [x] 1.1 Write failing tests in `tests/` for the four `retrieval-context-assembly` scenarios (two pages, one page, no labels, not merged), calling assembly on prepared rows. Confirm they fail on the current code.
- [x] 1.2 In `assembly.py` `_merge_unit`, set `page_labels` from each constituent's `page_label` (row, then metadata), in chunk order, each once, only when merged and at least one label exists (design D1–D3). Tests pass.

## 2. Answer citations

- [x] 2.1 Write failing tests for the two `grounded-answer-synthesis` scenarios (citation spans two pages; single-chunk citation has no `page_labels`).
- [x] 2.2 Carry `page_labels` in `evidence._evidence_rows` as its own key (not in `_EVIDENCE_FIELDS`), only when present, and copy it into citation entries in `citations.py` only when present. Tests pass.

- [x] 2.3 Remove the unused node conversion (design D7): `SearchRetriever` stops subclassing `BaseRetriever`; `retrieve(query)` returns the search rows; delete `_LINEAGE_FIELDS` and `_row_to_node`; fix the `evidence.py` comment that names `_LINEAGE_FIELDS`. Run `tests/test_answer_core.py` and `tests/unit/test_retrieval_embedding_identity.py`; both pass unchanged.
- [x] 2.4 Amend ADR-057 point 2: keep "no second retrieval path", drop the `BaseRetriever` and node-metadata wording, and add a dated amendment note naming this change.

## 3. HTTP contract and MCP

- [x] 3.1 Declare optional `page_labels` (array of strings) on `SearchResult`, `AnswerCitation` and `AnswerEvidence` in `src/omrs/transports/api/openapi.yaml`.
- [x] 3.2 Run the OpenAPI conformance tests and the MCP search and answer tests; update any fixture that holds a merged PDF row.

## 4. Display

- [x] 4.1 CLI: `transports/cli/search.py` shows "5–6" in the page column for a row with two or more `page_labels`. Add a test.
- [x] 4.2 Web: add `page_labels?: string[]` to the result and citation types in `web/src/api/documents.ts`; show "Pages 5–6" in `knowledge-base/ResultList.tsx` and in the citation popover Lineage section (`ChunkMetadata.tsx` / `CitationPopover.tsx`). Write the tests first, including the `workspace-chat` scenario.

## 5. Experiment 35 plan

- [ ] 5.1 Use `openspec-update-change` on `experiment-35-full-document-rag-benchmark`: its Hit@page rule reads `page_labels` with `page_label` as fallback, and its tasks gain a scorer unit test with a merged two-page row (gold on the second page counts as a hit). Validate that change strictly.

## 6. Verification

- [ ] 6.1 Re-pin the clean-base tripwire by test-ID diff against `v3`.
- [ ] 6.2 Update `docs/guides/` where search results or citations list their fields (grep `chunk_ids`).
- [ ] 6.3 Run `./scripts/local_ci.sh` and `openspec validate --all --strict`; both pass.
- [ ] 6.4 Live check on a scratch server: search a PDF collection for text that spans a page break and see "Pages n–m" in the Knowledge Base and in a chat citation, at 1280 px and 390 px.
