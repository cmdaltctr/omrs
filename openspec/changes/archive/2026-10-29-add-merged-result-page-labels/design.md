# Design

## Context

Context assembly (`src/omrs/core/retrieval/assembly.py`, `_merge_unit`) merges a run of adjacent chunks of one `(source_id, source_version)`. The lowest-index constituent supplies `id`, `metadata`, `chunk_id`, `source_chunk_index` and `page_label`. The merged text holds every constituent, and `chunk_ids` lists every constituent id. Dense (`dense.py`) and sparse (`sparse_dispatch.py`) rows already carry a top-level `page_label` from chunk metadata, so each constituent's page is in hand at merge time; no store read is needed.

Answer evidence (`core/answer/evidence.py`) and citations (`core/answer/citations.py`) copy a fixed set of lineage fields plus `chunk_ids`. The answer pipeline builds evidence from the raw search rows (`pipeline.py`, `result_rows = retriever.rows`), and citations copy from the evidence rows. A new row field reaches a citation when both `evidence.py` and `citations.py` carry it. `retriever._LINEAGE_FIELDS` only fills node metadata that the pipeline discards, so it is not on this path; D7 removes it.

Chunks never cross a page break: the Markdown chunker splits each PDF page document on its own, and chunk overlap stays inside one page (ingestion guide). So a constituent has at most one page label, and a merged row spans the pages of its constituents.

## Goals / Non-Goals

**Goals:**
- A merged search row and a citation of it name every page they span.
- Users see the page range in the Knowledge Base list, the citation popover and the CLI table.
- Experiment 35 scores Hit@page correctly on merged rows.

**Non-Goals:**
- Changing `page_label`. It stays the first constituent's page, so existing readers and recorded experiment outputs keep their meaning.
- Changing when chunks merge, or neighbour expansion.
- Page labels for formats without pages (Markdown, code).

## Decisions

**D1. Additive `page_labels`, present only when a merged row has labels.** Alternatives: (a) change `page_label` to a range string such as "5–6": breaks every reader that treats it as one page and the stored-chunk lookup in the chunk viewer; (b) always emit `page_labels`, even for single rows: adds noise to every result and to the OpenAPI examples. An absent field keeps unmerged rows byte-identical, which the retrieval regression gate relies on.

**D2. Order follows chunk index, each label once.** Constituents are already in ascending `source_chunk_index` order in `_merge_unit`. Deduplicate while keeping first occurrence, so three chunks on page 12 give `["12"]` and chunks on 5, 5, 6 give `["5", "6"]`. No numeric sort: labels are strings and can be roman numerals or "A-3".

**D3. Read each constituent's label from the row, then its metadata.** Use `row["page_label"]`, falling back to `row["metadata"]["page_label"]`, the same order `_mark_expanded` uses. Expanded neighbour rows (opt-in expansion) get `page_label` from metadata in `_mark_expanded`, so they are covered too.

**D4. Carry `page_labels` through evidence and citations.** Set it on evidence rows as its own key next to `chunk_ids`, only when present, and copy it into citation entries only when present. Keep it out of `_EVIDENCE_FIELDS`: `_labelled_nodes` copies those into node metadata, and the model input must not change. Evidence rows are public as `AnswerEvidence`, so the contract declares the field there too. 

**D5. Display a range from first to last label.** UI and CLI show "Pages 5–6" for two or more labels, joining first and last with an en dash, and "Page 5" otherwise. A merged row spans adjacent chunks, so its pages are contiguous in practice; listing every label adds nothing. A page with no text gives no chunk, so pages 5 and 7 can be adjacent; "Pages 5–7" is still a true range.

**D6. Experiment 35 reads `page_labels` with `page_label` as fallback.** Its D2 hit rule ("a chunk that spans pages is a hit when any of its pages is the gold page") then holds for merged rows. The edit goes into the `experiment-35-full-document-rag-benchmark` change through `openspec-update-change`, not into this change's specs, because that change owns its scorer.

**D7. Remove the unused node conversion from `SearchRetriever`.** `SearchRetriever` subclasses LlamaIndex `BaseRetriever` and turns each row into a `NodeWithScore` through `_row_to_node` and `_LINEAGE_FIELDS`. The pipeline calls `retrieve()` only to fill `retriever.rows` and discards the nodes (`pipeline.py`); synthesis gets its nodes from `evidence._labelled_nodes`. The class becomes a plain adapter: `retrieve(query)` calls `search()`, stores the rows on `rows` and returns them. `_LINEAGE_FIELDS`, `_row_to_node` and the `BaseRetriever` base go. Lineage is unaffected: it comes from stored chunk metadata on each search row, through evidence rows into citations. ADR-057 point 2 is amended: "no second retrieval path" stays; the `BaseRetriever` and node-metadata wording goes. Alternative: keep the class and only add `page_labels` to `_LINEAGE_FIELDS` to match `_EVIDENCE_FIELDS`; rejected because the list would keep looking like part of the citation path.

## Risks / Trade-offs

- [A client treats an unknown field as an error] → The field is optional and additive; the OpenAPI contract declares it, and the conformance tests check it.
- [Something outside the answer pipeline calls `SearchRetriever.retrieve()` and expects nodes] → None does today (only `pipeline.py` and two tests that check forwarded keyword arguments). The tests keep passing because they check the arguments `search()` receives.
- [Rows from a reader that sets no page labels] → No `page_labels`; behaviour as today.
- [Retrieval regression gate compares result rows] → Unmerged rows are unchanged (D1). Merged rows gain one key; check the gate's fixtures during apply and update them only if they hold merged PDF rows.
