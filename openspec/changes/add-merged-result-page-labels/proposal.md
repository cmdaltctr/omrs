# Proposal

## Why

Context assembly merges adjacent chunks of one source into one search result. The merged row takes its `page_label` from its first chunk only. Chunks never cross a page break, but adjacent chunks can sit on adjacent pages, so a merged row can hold text from pages 5 and 6 and report only page 5. A reader then looks on the wrong page, and a page-level metric scores the row as a miss. Experiment 35 plans a FinanceBench Hit@page metric that would read the wrong page today.

## What Changes

- A merged search result carries `page_labels`: the page label of each constituent chunk, in chunk order, with repeats removed. A row that was not merged, or whose chunks carry no page label, gains nothing. `page_label` keeps its present meaning (the first chunk's page) so no reader breaks.
- Answer evidence rows and citations carry the same `page_labels`, so a citation names every page it spans.
- `SearchRetriever` drops its unused LlamaIndex node conversion (`_LINEAGE_FIELDS`, `_row_to_node`). The answer pipeline never read those nodes, so answers, citations and lineage do not change. ADR-057 gets a dated amendment.
- The HTTP contract declares `page_labels` on search results and citations.
- The Knowledge Base result list, the chat citation popover and the CLI search table show the page range ("Pages 5–6") when a row spans pages.
- The Experiment 35 change (`experiment-35-full-document-rag-benchmark`) scores Hit@page from `page_labels`, with `page_label` as the fallback. This is a planning edit to that change, made through `openspec-update-change`; it is not built here.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `retrieval-context-assembly`: a merged row reports the page label of every constituent chunk.
- `grounded-answer-synthesis`: a citation of a merged row carries every constituent page label.
- `workspace-chat`: the citation popover shows the page range of a citation that spans pages.

## Impact

- Code: `src/omrs/core/retrieval/assembly.py` (`_merge_unit`), `src/omrs/core/answer/citations.py`, `evidence.py` and `retriever.py`, `src/omrs/transports/cli/search.py`, `src/omrs/transports/api/openapi.yaml`.
- Web: `web/src/api/documents.ts`, `web/src/knowledge-base/ResultList.tsx`, `web/src/components/ChunkMetadata.tsx`, `web/src/chat/CitationPopover.tsx`.
- API: additive optional field only. Existing clients keep working. The OpenAPI conformance tests need the new field declared, because `test_openapi_conformance.py` checks that result and citation schemas declare the fields the code returns.
- Data: none. No re-ingest; page labels already sit in each chunk's metadata.
- Experiments: none already run read `page_label` from merged search results (checked on 2026-10-29), so no recorded result changes.
