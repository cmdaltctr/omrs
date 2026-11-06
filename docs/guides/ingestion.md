# Ingestion Guide

## How ingestion works

Each file passes through a four-stage pipeline:

```
Source file (PDF, DOCX, TXT, ...)
      |
      v
[1] Load & parse  -----> Metadata extraction (optional)
      |                      |
      |                      +-- keyword:    regex (instant, no model)
      |                      +-- local:      chat model via METADATA_LLM_PROVIDER (~2s/file)
      |                      +-- llamaindex: per-chunk pipeline (~5–30s/file)
      |
      v
[2] Split into chunks (SentenceSplitter)
      |  chunk_size = 512 chars (default)
      |  chunk_overlap = 100 chars
      |
      v
[3] Embed each chunk --> Ollama embedding model (EMBED_MODEL)
      |                     Produces a fixed-dimension vector (768, 1024, etc.)
      |
      v
[4] Store in the selected vector store
      |  LanceDB is the base-install default
      |  collection = "documents" (or --collection value)
      |  Each record: vector + text + metadata + file_path
      v
[Done] Collection ready for search
```

Re-ingesting a file is an **upsert** — old chunks are removed before new ones are written. There is no duplication.

## Ingestion stages as graph operations

`ingest_path_async` and the ingestion graph operations call the same per-source functions. The standard path did not change when the graph operations were added.

| Stage | Shared function | Module | Graph operation |
|---|---|---|---|
| Find eligible files | `gather_supported_files`, `iter_source_units` | `src/omrs/core/ingestion/loader.py`, `src/omrs/core/ingestion/sources.py` | `source.discover` |
| Source identity and reuse check | `prepare_source`, `check_source_state` | `src/omrs/core/ingestion/sources.py` | `source.identify` |
| Read | `read_document` | `src/omrs/core/ingestion/backends/orchestrator.py` | `read.document` |
| Normalise reader output | `normalise_backend_read` | `src/omrs/core/ingestion/chunker.py` | `prepare.normalise` |
| Metadata enrichment | `enrich_documents` | `src/omrs/core/ingestion/chunker.py` | `prepare.enrich` |
| Split | `split_documents` | `src/omrs/core/ingestion/chunker.py` | `prepare.chunk` |
| Embed | `prepare_source_embeddings` | `src/omrs/core/ingestion/replacement.py` | `embed.chunks` |
| Protected commit | `commit_prepared_source` | `src/omrs/core/ingestion/commit.py` | `commit.source` |

The adapters live in `src/omrs/core/ingestion/graph_adapters.py`. The descriptors and the canonical ingestion graph live in `src/omrs/core/ingestion/graph_adapters_catalogue.py`. The canonical `ingestion` template is that graph. It processes one source at a time and writes the same rows as `Engine.ingest` on the fixtures in `tests/fixtures/pipeline_parity/ingestion/`.

A graph cannot write to the vector store directly. `commit.source` keeps the lineage checks, the embedding write contract below, the source write lock and the stale-row clean-up. `src/omrs/core/ingestion/graph_fingerprint.py` adds the graph's index-shaping operations and parameters to the source identity. A changed chunker setting in a graph therefore makes the next explicit ingest rebuild the affected sources. A layout change or a query-only change does not.

These values and behaviours are unchanged:

- `chunking.chunk_size` defaults to `512` and `chunking.chunk_overlap` defaults to `100`.
- Each file keeps its own failure handling. A failed file does not undo the files committed before it.
- `ingest_path_async` and `Engine.ingest` return the same dictionary keys as before: `status`, `files_indexed`, `files_skipped_unchanged`, `files_skipped_binary`, `chunks_created`, `chunks_removed`, `collection`, `file_details`, `metadata_degraded`, `timings` and `peak_rss_bytes`, plus `error_type`, `message` and `warnings` when they apply.

## Embedding write contract

Stage 4 is fail-closed
([ADR-051](../adr/051-fail-closed-embedding-write-contract.md)): the store
adapter validates the complete embedding batch before any backend
mutation. The shared validator rejects a batch that contains:

- no identifiers or no vectors (empty batch)
- a count of identifiers that differs from the count of vectors
- a value that is not a sized vector, or an empty vector
- a non-numeric element (booleans are rejected)
- a non-finite element (NaN or infinity)
- mixed vector dimensions within one batch
- a dimension that conflicts with the existing collection

The model stamp is checked first. Before it embeds or checks vector shape,
the store compares the collection's stamped model with the active model. A
mismatch raises the identity-mismatch error that names both models, whatever
the vector size. The ingestion graph makes the same read-only check before
`embed.chunks`, so a refused source is not embedded and a paid provider is not
billed for it. The commit step repeats the check, because another run can
stamp the collection while a source is embedded.

A rejected batch writes nothing: no rows, no collection recreation, and no
generation change. The error names the collection, the embedding
provider/model, and each affected node or row identifier. Vectors are
never normalised, truncated, or repaired — the validator reports the
fault and stops the write. Norm policy is enforced separately by the
embedding norm guard ([ADR-053](../adr/053-embedding-norm-guard.md)): a
vector outside the unit-norm tolerance aborts the file replacement at the
embed stage, before the store validator runs.

## Source and chunk lineage

Every production-ingested chunk carries stable identity metadata
([ADR-052](../adr/052-stable-source-chunk-lineage.md)). The identifiers are
deterministic hashes: the same inputs always produce the same value.
`core/ingestion/source_state.py` owns the formulas and stamps them after
parsing, chunking, and metadata extraction but before embedding, so no
identifier ever changes a vector or the text an LLM sees.

### The identity hierarchy

| Field                 | Formula                                                                                            | Stability                                                                                        |
| --------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `file_path`           | canonical absolute path                                                                            | Human-readable locator for display and diagnostics                                               |
| `source_id`           | `"src_" + SHA-256("file\0" + canonical path)`                                                      | Stable while the file is edited in place; new after a move or copy; identical across collections |
| `source_content_hash` | SHA-256 of the original file bytes                                                                 | New when bytes change; shared by equal bytes at two paths                                        |
| `source_version`      | SHA-256 of `source_content_hash` + NUL + `source_index_identity`                                   | New when bytes or any index-shaping setting (parser, chunker, metadata, embedding) changes       |
| `source_chunk_index`  | zero-based ordinal within the version                                                              | Orders membership in the chunk set                                                               |
| `source_chunk_count`  | N, the chunk total for the version                                                                 | Declares the size of the complete set                                                            |
| `chunk_id`            | `"chk_" + SHA-256(source_id + NUL + source_version + NUL + decimal index + NUL + chunk text hash)` | Stable for the same text at the same ordinal in one version                                      |
| vector row ID         | SHA-256 of `source_id` + NUL + `source_attempt` + NUL + `chunk_id`                                 | Attempt-specific; never a store primary key                                                      |

All digests are lower-case hexadecimal over UTF-8 input joined with NUL
separators. `source_id` excludes the collection name, so one file indexed
into two collections carries one identity. The vector row ID stays internal:
a forced re-ingestion reproduces the same `chunk_id` values but writes fresh
row IDs, so candidate and durable attempts coexist until verification
([ADR-048](../adr/048-bounded-failure-safe-ingestion.md)). Ordinary public
results never expose the row ID.

### Ordered reconstruction

One `source_id` plus one `source_version` is a complete ordered chunk set:

```text
rows    = all rows with source_id = "src_…" and source_version = "…"
assert  every row has source_chunk_count == N and N == len(rows)
ordered = rows sorted by source_chunk_index   # indices are 0, 1, …, N-1
```

Sorting by `source_chunk_index` rebuilds the indexed chunk sequence. This
reconstructs the INDEXED representation only. It does not recover the
original file bytes, PDF layout, or parser input. The source file and
`source_content_hash` remain authoritative for the original content.

### Moving or copying a file

Identity follows the path. A new canonical path is a new logical source, so:

1. Delete the old path from the collection.
2. Ingest the destination path.

The watcher applies both steps automatically for a rename inside the watch
tree (`on_moved`: delete the old path first, then ingest the destination). A
failed cleanup is retried and reported; the destination is never ingested
while the old path still holds rows. Manual moves outside a watch tree still
need the two steps above. Equal bytes at two paths share
`source_content_hash` but keep different `source_id` values; content is never
deduplicated.

### Pre-lineage rows fail before mutation

If a collection holds rows for a canonical path that lack, or disagree on,
the derived `source_id`, ingestion stops before any parse, embedding, or
store write. The error names the path and instructs you to rebuild the
affected data by deleting the source or collection and re-ingesting it. The
stored rows are never migrated, upgraded, or deleted. This is a deliberate
clean boundary: no production documents predate this change.

## Upgrading to this release

This release changes two things every stored vector depends on:

1. The embedding-text contract
   ([ADR-055](../adr/055-embedding-text-is-a-declared-contract.md)). Parser
   telemetry and filesystem bookkeeping no longer enter embedding text.
2. Index identity schema 3. The identity now records the exclusion set and
   the reader's declared text format.

Both changes alter `source_index_identity`. The result is one full re-ingest.

### What you will see

- Every previously ingested source re-processes on the next corpus ingest.
- `files_skipped_unchanged` drops to zero on the first run after upgrade.
  Later runs resume normal incremental skipping.
- Search results are unchanged in shape. No tool or CLI call changes.

### Interrupted re-ingests resume

The re-ingest is per source, not one atomic collection rebuild. An
interrupted run may leave old-era and new-era sources in one collection.
This is safe. The next run re-processes each old-era source; it does not
skip it. Each replacement stays failure-safe per source
([ADR-048](../adr/048-bounded-failure-safe-ingestion.md)).

### Rows the lineage guard rejects

Pre-lineage rows, or rows from an incompatible mixed state, still fail
`assert_source_lineage_compatible()` before any mutation. Those rows keep
the explicit delete-and-rebuild path described above. This release neither
weakens nor replaces that guard.

## PDF reader configuration

The PDF parser is a pluggable factory controlled by the `PDF_READERS` list
(comma-separated in the environment). The single-value `PDF_READER` key still
works and expands to a list. Accepted names and values:

| Value           | Description                                                         | Install                      |
| --------------- | ------------------------------------------------------------------- | ---------------------------- |
| `pdf_inspector` | Default. Rust markdown extractor. Emits one document per page.      | Base dependency              |
| `pypdf`         | Always available via `llama-index-readers-file`. Terminal fallback. | Base (transitive)            |
| `liteparse`     | Column-aware reading order + bounding-box metadata.                 | Base dependency              |
| `pypdfium2`     | Same PDFium engine as LiteParse, no bbox. Fallback tier.            | `[pdf-pypdfium2]` extra      |
| `auto`          | Probes in order: liteparse → pypdfium2 → pypdf.                     | Depends on what is installed |

The packaged default is `pdf_inspector`, a base dependency selected through
configuration after Experiment 14
([ADR-050](../adr/050-configure-pdf-inspector-as-default-reader.md)).
`auto` keeps the LiteParse-first capability policy, as the single value
`PDF_READER=auto`. Set `PDF_READERS` to an ordered list of registered names to
override the default. The first installed reader of the list reads each file.
A listed reader that is not installed is skipped with an error. When no listed
reader is installed, pypdf reads the files. See
[PDF reading](configuration.md#pdf-reading) for the full rule.

`pdf_inspector` emits one document for each page that has text, in page
order. Each document carries `page` (integer, from 1) and `page_label` (the
same number as a string), the format that LiteParse and pypdfium2 use. Every
page document also carries the whole-PDF evidence keys (`pdf_type`,
`pdf_confidence`, `page_count`, `pages_needing_ocr`). Markdown chunking splits
each page document on its own, so a chunk never crosses a page break and chunk
overlap stays inside one page. The chunker carries the open heading path from
one page to the next page of the same PDF, so the first chunks of a page keep
the section heading that an earlier page opened.

One case gives one document without `page` or `page_label`:

- The per-page call fails, or gives no text while the whole-document Markdown
  has text. The adapter then emits the whole-document Markdown and logs a
  warning.

When the extraction-fallback chain recovers the text, it also keeps one
document per page. LiteParse pages keep their own numbers. pypdf pages get the
physical page number from their position, not the PDF's own label.

PDF sources indexed before page documents rebuild once on their next ingest,
because the reader output revision is part of the index identity. Re-ingest
each PDF folder after the upgrade. Until then, the old chunks stay searchable
without a page.

LiteParse captures bounding-box metadata (`page`, `column`,
`section_bbox`, `bbox_schema_version`) on every emitted Document for
future spatial RAG capabilities. OCR is disabled by default
(`LITEPARSE_OCR_ENABLED=false`) — enable it only for scanned PDFs.

See [ADR-020](../adr/020-use-liteparse-as-pdf-reader.md) for the factory
adoption rationale and [ADR-050](../adr/050-configure-pdf-inspector-as-default-reader.md)
for the default-selection decision and Experiment 14 results.

## Reader-output normalisation

PDF readers and OCR engines put HTML into their Markdown: pdf-inspector wraps
links and some headers in `<u>`, and the OCR worker wraps pictures in
`<div><img></div>` blocks and styles its tables. Ingestion removes this markup
from PDF text right after the reader returns it and before chunking, so
stored chunks, embeddings and BM25 carry document text, not tags.

The rules are a closed list (unknown tags pass through unchanged):

| Input | Result |
| --- | --- |
| `<u>`, `<span>`, `<font>`, `<center>` | Tag removed, text kept |
| `<b>`/`<strong>`, `<i>`/`<em>` | `**text**`, `*text*` |
| `<div>` (with or without an image) | Tag removed, text kept. Text an engine read inside a picture stays |
| `<img>` | Removed. No placeholder |
| `<br>` | Line break |
| `<table>` | Kept as HTML; only structural tags and `colspan`/`rowspan` remain |
| Code, links, LaTeX maths | Unchanged |

No visible character is lost: Experiment 36 checked 215 pages across five
engines. Only PDF sources are normalised; a `.md` file is left as written.

Set `INGESTION__NORMALISE_READER_OUTPUT=false` to index raw reader text, for
example in a reader comparison. The setting and the normaliser version are
part of the index identity (schema 7), so changing either reprocesses every
source once on its next ingest. See
[TDR-028](../tdr/028-normalise-reader-markdown-before-chunking.md).

## OCR fallback for scanned PDFs

`pdf-inspector` reads text out of a PDF. It cannot read text that is only
an image. A scanned page therefore comes back empty or nearly empty, and
that content never reaches the index. The OCR fallback sends those PDFs
to isolated OCR engines: dots-mocr is the default primary engine, with
PaddleOCR-VL as fallback when the primary is unavailable before dispatch.

**Routing is on by default**
([ADR-065](../adr/065-ocr-fallback-gate-promoted-to-packaged-default.md)),
and it judges every page
([ADR-069](../adr/069-page-level-ocr-routing-and-the-pdfium-runtime.md)).
The document-level gate that ADR-065 promoted, with its `0.5` confidence
and `0.10` page-fraction thresholds, is gone. Experiment 29 validated that
gate on an operator-approved 17-PDF collection.

OCR is expensive. Earlier PaddleOCR-VL measurements took 34–106 seconds
per page against roughly one second per file on the fast path.
dots.mocr on llama.cpp took 9 to 48 seconds per page (median 35) on Apple
silicon in the cut-over check of change `dots-mocr-llamacpp-backend`.
Time depends on the page and hardware.
Page routing exists so that cost lands only on pages
that need it. With no OCR route available, a flagged page
degrades to its native text plus an actionable warning rather
than failing the file. Set `OCR_FALLBACK_ENABLED=false` to opt out entirely.

The earlier prevalence concern is on record: on a library of 79 real
academic PDFs, only 2 documents genuinely lacked a text layer — but with
79 documents the 95% interval on that rate still runs from 0.7% to 8.8%,
so "rare" is supported and "negligible" is not. See
[ADR-064](../adr/064-input-quality-promotion-decisions.md) and experiment 28.

The same measurement identified a limitation in the original policy: it
sent a 991-page `mixed` document to OCR in full, despite extracting 1,127
characters per page with only 10 of 991 pages flagged. That defect was
fixed on 2026-09-10 and is now closed for good: page routing sends only
the flagged pages to OCR, whatever the document type.

Workers live under `ocr-workers/`. The shared `core/` package owns the
protocol, framing loop, validation and capability command. Each project
under `engines/<engine>/` has its own environment and lockfile.
Paddle packages stay in the PaddleOCR-VL environment, and the llama.cpp
binary and model files stay in the dots-mocr engine cache. The OMRS main
install does not install them.

### Routing policy

On the `pdf_inspector` path, the routing seam uses `pdf_type`,
`pdf_confidence`, the count of pages flagged for OCR, and the page count.
When maths routing is enabled, it also reads the PDF's font resources.

With OCR enabled and a route available, OMRS judges every page. A page
goes to OCR when pdf-inspector flags it as needing OCR. With maths routing
enabled, a page that uses a recognised maths font goes to OCR too. A
scanned or image-based PDF flags all its pages. A `mixed` PDF flags only
the pages that carry no text. The 991-page document from experiment 28
motivated this design; see
[ADR-064](../adr/064-input-quality-promotion-decisions.md).

`OCR_FALLBACK_ENABLED=true` is the packaged default (ADR-065). With no
worker provisioned and no local runtime, a flagged page keeps its native
text and the batch continues with an actionable warning.

Layout complexity is not a rule. Multi-column and table-heavy PDFs stay
on the fast path when their text extracts cleanly and no maths condition
applies. Experiment 24 confirmed the fast-path Markdown is byte-identical with the fallback
enabled and disabled.

Only flagged pages go to OCR. A page that the local tier or the worker
reads carries `page` and `page_label` like any other page document. The
routing seam stamps the OCR diagnostics on each page document.

### Maths pages and engine selection

The maths detector uses a closed, versioned font list. It recognises
Computer Modern and Latin Modern maths, AMS and Euler symbols, and
OpenType maths fonts such as Cambria Math and STIX. A Unicode map does
not prevent a match: correct characters alone do not preserve equation
structure. The detector reads font resources without rendering pages or
calling a model. Unreadable resources flag no pages. Equations drawn as
images or vector paths without recognised fonts are outside its scope.

Maths pages skip the local tier and join locally escalated pages
in one request. A page in both groups is sent once. Maths pages keep
native text and count as unresolved if no route supplies usable text.

Set `OCR_MATHS_ROUTING_ENABLED=false` to disable this detector and its
routing. The master OCR switch still applies. OMRS removed
`OCR_MATHS_PAGE_FRACTION`: a maths page routes on its own, so no page
fraction applies.

Every worker request selects the primary route first. The fallback is
selected only when the primary is unavailable before dispatch. A failure
after dispatch is a per-file error and never retries on the other route.
If both routes resolve to the same command and working directory, they
share one client. Startup logs name the resolved routes and availability.

### Page rules

A page rule decides what happens to flagged pages before any OCR tier reads
them. Rules run in ascending order. Each built-in rule has a descriptor in
`core/reading_parts.py`. See [Reading parts](reading-parts.md).

| Order | Rule | Setting | What it does |
|---|---|---|---|
| 10 | `blank` | None (always on) | Drops a flagged page that the blank test finds blank. The page keeps its native text. |
| 20 | `maths` | `OCR_MATHS_ROUTING_ENABLED` | Sends a page with a maths font direct to the OCR engines. |
| 30 | `non_latin` | `OCR_NON_LATIN_ROUTING` | Sends non-Latin pages direct, and checks the output of the local backends under `detect`. |

Four fixed rules combine the results:

1. A page that an earlier rule dropped leaves the page set of every later rule.
2. The direct set of a rule loses the pages that earlier rules dropped.
3. The direct pages are the union of every direct set. The local backends read
   the flagged pages that are neither dropped nor direct.
4. A direct page that no OCR engine read goes to the degrade hook of the first
   rule that sent it direct. The `non_latin` rule sends such a page to the
   local backends with one warning.

A built-in rule that raises an error fails the file. A rule from another
package runs only when its `reading_part_options` entry holds
`"enabled": true`. If that rule fails to load or raises an error, OMRS skips it
for the file, logs one warning and switches it off until the server restarts.

### Page-level routing

OMRS routes per page. `OCR_ROUTING_UNIT=page` is the default and the only
legal value; `OCR_ROUTING_UNIT=document` fails start-up with a message that
names `page`
([ADR-069](../adr/069-page-level-ocr-routing-and-the-pdfium-runtime.md)).
Every page is scanned; the flagged pages that no [page rule](#page-rules) dropped or sent
direct run through the local OCR backends in the order of `OCR_LOCAL_BACKENDS`. The default
backend, `pp-ocrv6-small`, is pdf-inspector's local OCR (PP-OCRv6 Small on ONNX Runtime, CPU,
no PyTorch) at roughly 0.75 s
median per page; pages the local tier cannot read escalate to the
worker in **one** request with any directly routed maths pages. The seam
emits one document for each page that has text, in page order, with `page`
and `page_label`. This includes pages that local OCR or the worker read.

A page escalates when the local attempt returns empty or
whitespace-only text, reports confidence below
the cut of the backend that read it (default 0.92 for `pp-ocrv6-small` and 0.94 for
`indra`, from Experiment 46a, which re-read the saved results of Experiment 46 on 229
pages from 9 documents) or flags `hosted_recommended`. Confidence is the only test. No
backend filters pages by script.
Unreported confidence escalates too. With the default
`OCR_NON_LATIN_ROUTING=off` there is no script or typography pre-check:
the failure classes announce themselves after the attempt. Under `detect`,
a flagged page with a non-Latin text layer skips the local tier, and a
non-Latin local result of any backend, Indra included, escalates with reason
`non_latin_output`. When `indra` is in the list, set `OCR_NON_LATIN_ROUTING` to
`off`.

`OCR_LOCAL_CUTS` sets the cut of a backend. It is a JSON object keyed by backend name,
for example `{"indra": 0.96}`. A backend with no entry uses its default cut.

With more than one backend listed, the first backend reads every page the local tier takes.
The next backend reads, in one call, the pages that the backend before it did not keep.
The OCR engines read the pages that no listed backend kept. An escalated page reports the
reasons of the last backend that read it and carries the text of the first backend that
returned non-empty text. A backend that raises an error is skipped for the call, with one
warning per process. See
[Local OCR backends](configuration.md#local-ocr-backends).

Every emitted page document carries the same five scalar counts for the
whole PDF. They sum to `page_count`:

| Key | Meaning |
|---|---|
| `ocr_pages_native` | Pages whose text is the native pdf-inspector extraction |
| `ocr_pages_local` | Pages whose text is local OCR |
| `ocr_pages_worker` | Pages whose text is the worker's |
| `ocr_pages_blank` | Flagged pages the blank test removed before any OCR tier; they keep their native text |
| `ocr_pages_unresolved` | Flagged, non-blank pages no tier produced text for: an escalation came back empty, or no OCR route was available. They keep their best available text |

Before local OCR runs, the blank test renders each flagged page and
measures stroke ink. A page below the fixed threshold (1.5e-4 of its
pixels, version 1 of the test) is blank: it skips both OCR tiers and
counts `ocr_pages_blank`, so `unresolved` means only "an escalation
produced no text" or "no OCR route was available". Three known limits,
accepted: a page whose only mark is a page number counts blank (the
number stays in the text when the native layer read it, otherwise it is
lost; `page_label` still carries it), a page whose only mark is one
faint short word counts blank, and a page whose only mark is a lone
one-pixel stroke counts blank, because the speck guard removes it
before the score. On all 1,123 Experiment 33 pages no page with three
or more reference characters was skipped, with a 5.3-times margin. A
page the test cannot render or score is not blank and follows the route
above.

`ocr_backend` names a backend only when it alone produced the text
(`pdf_inspector`, `pdf_inspector_ocr`, `indra_ocr`, `dots_mocr`, `paddleocr_vl`); anything else
is `mixed`. A local page names the producer of the backend that kept it. A 200-page document whose worker read one page reports
`mixed`, not `paddleocr_vl` — naming the higher tier would be false.

Degradation never fails the file. A missing worker, a reply that
cannot be attributed per page, or an empty per-page entry keeps the
best available text (local, then native) and counts the page
unresolved; no marker is inserted into retrieval text. A missing local
runtime (for example no PDFium) sends the flagged pages to the worker
engine in one page-listed request. They never fall back to native text
for that reason (issue #161). Only when no OCR route exists either do
the pages keep native text and count unresolved, with one warning that
names both missing tiers. A worker failure after a complete request was
flushed still fails the file. When page routing finds no text on any page and the
reader's fallback chain rescued the document, the rescued text is
emitted with all-native counts.

The local tier's runtime comes from existing base dependencies and is
configured with process-level variables. OMRS sets `PDFIUM_LIB_PATH` and
`ORT_DYLIB_PATH` itself from the bundled libraries when they are unset or
empty. To use other libraries, set them in the shell or in `.env`, which is
exported before any read. A value you set is never replaced.

| Variable | Where the library lives |
|---|---|
| `PDFIUM_LIB_PATH` | The LiteParse-bundled `libpdfium.dylib`, inside the `liteparse` package directory of the environment |
| `ORT_DYLIB_PATH` | ONNX Runtime's dylib, in `onnxruntime/capi/` of the environment |
| `PDF_INSPECTOR_MODEL_CACHE` | Optional model cache directory; the default is a user-level cache |

The `pp-ocrv6-small` model (`pp-ocrv6-small@oar-ocr-v0.7.0`, about 31 MB) downloads on
first use unless `OCR_LOCAL_OFFLINE=true`; with offline mode and no
cached model, the tier degrades. `OCR_LOCAL_MODEL_DIRECTORY`, when
set, points at the artifact leaf directory (`<name>/<revision>`), not
the cache root.

The `indra` backend needs the `local-ocr-indra` extra and its weights in the
folder that `INDRA_OCR_MODEL_DIR` names. Under `OCR_LOCAL_OFFLINE=true`, it reads
only that folder and never downloads.

The routing unit and the blank-page test are part of the identity of every
source. The effective cut of each listed backend and the resolved local model
identity are part of the identity of PDF sources only, in the `parser` block,
because a different cut or model changes which engine reads each page. An entry
in `OCR_LOCAL_CUTS` that equals the default cut gives the same digest as no
entry. A change to a cut, a list or a local model re-indexes PDF sources only.
Markdown and code sources keep their digest. Identity schema 8 reindexes every
source once, as described under
[Routing identity](#routing-identity-and-existing-indexes). The local
tier's quality residual is accepted and named in ADR-069; the deferred
retrieval experiment gates any future default change.

### Configuration

| Variable                      | Default | Meaning                                                          |
| ----------------------------- | ------- | ---------------------------------------------------------------- |
| `OCR_FALLBACK_ENABLED`        | `true`  | Switches OCR routing on and off. Off means no page reaches OCR. |
| `OCR_ROUTING_UNIT`            | `page`  | Only legal value. `document` fails start-up.                      |
| `OCR_LOCAL_BACKENDS`          | `pp-ocrv6-small` | Ordered list of local OCR backends (`pp-ocrv6-small`, `indra`). Comma-separated; a JSON array in `omrs.jsonc`. See [Local OCR backends](configuration.md#local-ocr-backends). |
| `OCR_LOCAL_CUTS`              | `{}`    | JSON object that sets the escalation cut of a backend by name. A backend with no entry uses its default cut (0.92 for `pp-ocrv6-small`, 0.94 for `indra`). |
| `OCR_LOCAL_OFFLINE`           | `false` | Forbid the model download.                                        |
| `OCR_LOCAL_MODEL_DIRECTORY`   | empty   | Model artifact leaf directory; empty means the default cache.     |
| `OCR_WORKERS_DIR`             | empty   | Absolute path to `ocr-workers`; empty disables folder-based routes. |
| `OCR_ENGINES`                 | `dots-mocr,paddleocr-vl` | Ordered engine list. The first available engine serves every worker request. A later engine serves only when every engine before it is unavailable before dispatch. A list of one engine means no fallback. |
| `OCR_ENGINE_PRIMARY`, `OCR_ENGINE_FALLBACK` | `dots-mocr`, `paddleocr-vl` | The older single-value form of the first two entries. Still valid; see [OCR fallback and isolated engines](configuration.md#ocr-fallback-and-isolated-engines). |
| `OCR_WORKER_REQUEST_TIMEOUT`  | `300.0` | Minimum parse-response timeout in seconds. |
| `OCR_WORKER_SECONDS_PER_PAGE` | `120.0` | Timeout allowance per requested page in seconds. |
| `OCR_MATHS_ROUTING_ENABLED`   | `true`  | Detect maths fonts and route affected pages. |
| `READING_PART_OPTIONS`        | `{}`    | JSON object of options per reading part. See [Reading part options](configuration.md#reading-part-options). |
| `OCR_NON_LATIN_ROUTING`       | `off`   | `always` sends every flagged page past the local tier. `detect` sends a flagged page past it only when its text layer is non-Latin, and escalates a non-Latin local result of any backend. See [Non-Latin page routing](configuration.md#non-latin-page-routing). |

The timeout is `max(OCR_WORKER_REQUEST_TIMEOUT, requested_pages * OCR_WORKER_SECONDS_PER_PAGE)`.
With the defaults, a 14-page request gets 1,680 seconds.

OMRS removed three settings with the document routing unit:
`OCR_FALLBACK_MIN_CONFIDENCE`, `OCR_FALLBACK_PAGE_FRACTION` and
`OCR_MATHS_PAGE_FRACTION`. OCR routing judges every page, so the
document-level threshold is gone. Each name in the environment fails
start-up. Each lower-case key in `omrs.jsonc` is listed as retired and
ignored.

### Routing identity and existing indexes

Source identity includes the OCR routing payload `{enabled, routing_unit,
blank_page_test}`, both route fingerprints, and the maths block
`{enabled, detector_version}`. These fields apply to every source,
including non-PDF sources and sources with OCR disabled. The page-source
counts are excluded for every source. The identity schema is 8.

The local OCR cuts and the resolved local model identity are not in the routing
payload. They are in the `parser` block of PDF sources: one entry for each listed
backend, in list order, with its effective cut and its resolved model identity.
This holds for the default list too. A cut change therefore reads PDF sources
again and leaves Markdown and code sources unchanged. The same holds for a cut
that a Read document step sets (see
[Local OCR cuts on Read document step](pipelines.md#local-ocr-cuts-on-read-document-step)).

The move to schema 8 reindexes every existing source once on its next ingestion. After that,
a second ingest with the same settings processes no source. Later
changes to either engine fingerprint or maths-routing input also change
identity. Reading an index does not rebuild it. Keep preserved experiment
databases out of ingestion and migration tests.

<a id="provision-the-worker"></a>

### Provision the engines

Run from the intended feature worktree root after approving the package
installation and model downloads:

```bash
python3 ocr-workers/provision.py paddleocr-vl                 # Python 3.12
python3 ocr-workers/provision.py paddleocr-vl --python 3.11   # or 3.13
python3 ocr-workers/provision.py paddleocr-vl --dry-run       # install nothing
```

Read [the dots.mocr licence notes](../../ocr-workers/engines/dots-mocr/LICENCE-NOTES.md)
before provisioning dots-mocr. Its terms cover permission to digitise
publications, sensitive personal data, revised terms and dispute resolution.
Only an operator who accepts those terms should run:

```bash
python3 ocr-workers/provision.py dots-mocr --accept-model-licence
```

dots-mocr runs on llama.cpp ([ADR-113](../adr/113-dots-mocr-runs-on-llama-cpp.md)).
Provisioning downloads three pinned items and checks the SHA-256 of each:

- the model `dots-mocr-Q8_0.gguf` (1.9 GB);
- the image projector `dots-mocr-mmproj-bf16.gguf` (2.5 GB);
- the llama.cpp release `b11941` for macOS on Apple silicon or Linux on
  x86-64 (16 to 22 MB).

The two model files come from a private Hugging Face repository. Log in
with `hf auth login`, or set `HF_TOKEN`, before you provision. A parse
needs no token and no network. OMRS starts the pinned `llama-server`
itself (see [Runtime block](../../ocr-workers/README.md#runtime-block)).

A `dots-mocr` engine provisioned before the move to llama.cpp stops
working until you provision it again. The engine fingerprint also
changes, so the next ingest re-indexes each document once.

The script syncs each engine's `uv.lock` with `uv sync --locked` and runs
its fetch command when one is declared. It rejects Python outside
3.11–3.13 and never changes the OMRS environment. A root-level `uv sync`
installs OMRS; it does not provision engines.

Set the route configuration in `.env`:

```dotenv
OCR_WORKERS_DIR=/absolute/path/to/ocr-workers
OCR_ENGINES=dots-mocr,paddleocr-vl
```

Each engine starts from `engines/<engine>/` using its `.venv` interpreter
and `python -m omrs_ocr_worker_core`. An empty `OCR_WORKERS_DIR` makes
every route unavailable.

The web app can set the folder: Integrations › OCR engines shows each
engine, whether it is provisioned, and the provision command. A Read
document step of a user profile can choose its own OCR engines and
routing; each step value enters the source identity, so a changed value
reprocesses the source on the next ingest (ADR-105).

**Migration from the single worker:**

1. Preserve existing model caches before removing an old worker directory.
2. Provision the required engines under the new layout.
3. Set `OCR_WORKERS_DIR` to the absolute `ocr-workers` path.
4. Remove `OCR_WORKER_COMMAND` and `OCR_WORKER_ENV_DIR`. Start-up refuses either one.
5. Check the startup line `OCR routes: …` for each engine and whether it is provisioned.

Each engine uses `<engine folder>/.model-cache/` by default. Set
`OMRS_OCR_MODEL_CACHE` consistently during provisioning and execution to
use `$OMRS_OCR_MODEL_CACHE/<engine>/` outside the worktree. See the
[Paddle cache record](../../ocr-workers/engines/paddleocr-vl/DATA_LOCATIONS.md)
for preserved weights.

Experiment 41 measured a peak of 17.3 GiB for dots.mocr on llama.cpp
(worker plus server) on Apple silicon over 257 pages. The earlier backend
peaked at 22.2 GiB. Plan for 17.3 GiB. The Linux build runs on the CPU and
is slower. For limited memory, set
`OCR_ENGINES=paddleocr-vl,dots-mocr` (PaddleOCR-VL first). Leave dots-mocr unprovisioned if you
do not accept its licence; a provisioned Paddle fallback can serve every
worker request.

### Worker lifecycle

Each route has a lazy, long-lived worker owned by the OMRS engine or
by the standalone ingestion operation. Identical routes share one client.

1. Building an engine starts nothing. A metadata-only capability probe
   runs at the composition boundary. It reads versions and identities
   only: it does not initialise a model runtime or load weights.
2. A PDF that no OCR condition selects starts no parsing worker.
3. The first dispatch starts the selected route's subprocess.
4. Later requests reuse that subprocess, with one request in flight per client.
5. Owner shutdown closes every distinct route client.
6. A timeout, crash, closed output stream, or protocol violation
   discards the handle. The next OCR request starts a fresh process. The
   failed request is never replayed automatically.

### Protocol and diagnostics

The two processes speak UTF-8 JSON Lines. OMRS writes one request per
line to the worker's standard input; the worker writes one terminal
response per line to standard output. Nothing else goes to standard
output. All worker logs go to standard error, which OMRS drains
separately and forwards through its own logging, so a noisy worker can
never corrupt the protocol stream or block on a full pipe.

Protocol versions `1.0` and `1.1` are accepted. A request that
carries a `pages` list speaks `1.1`; a request without one speaks
`1.0`, so an un-upgraded worker keeps serving document-level requests
during a rolling upgrade. Successful parse responses declare the output
schema `omrs.ocr.parse_output` version `1`. A version or schema mismatch
is a protocol failure, not a silent downgrade.

The capability probe reports availability, protocol version, every
worker package with its exact version, pipeline identity and revision,
model identity and revision, output-schema identity and version, and
`backend_id`. Diagnostics use the answering engine's `backend_id`.
A legacy worker without that field reports the generic `ocr_worker`.
Missing, unusable, malformed, and incompatible workers all collapse to
ONE stable unavailable fingerprint. The reason lives in the log, never
in the fingerprint.

### When the worker is not there

If flagged pages need OCR but no usable route exists **before dispatch**,
ingestion keeps the pages' native text, marks the result
degraded through the OCR metadata, logs an actionable warning naming
`OCR_WORKERS_DIR`, and continues
the batch. Nothing is fabricated and no other file fails.

If the worker fails **after** a complete request was written and
flushed, that file returns a structured error instead. The partial
Markdown is not substituted for a success, the failed source version is
not marked current, any prior current version survives, and the batch
continues with the next file.

### OCR metadata on every PDF

Four base keys are stamped on both branches, so an operator can tell
what happened by reading a retrieval result:

| Key                 | Meaning                                   |
| ------------------- | ----------------------------------------- |
| `ocr_required`      | At least one page was flagged for OCR or maths routing. |
| `ocr_used`          | The worker actually parsed it.            |
| `ocr_backend`       | `pdf_inspector`, `dots_mocr` or `paddleocr_vl`; legacy workers can report `ocr_worker`. |
| `pages_needing_ocr` | Scalar count of flagged pages.            |

When maths routing is enabled, `pages_maths_font` also records the
number of pages with recognised maths fonts. It is separate from
`pages_needing_ocr`, which counts pages flagged by pdf-inspector.
Disabling maths routing omits `pages_maths_font`.

Two of these generalise to pages: `ocr_used` is
true when OCR produced the text of at least one page, local or worker;
`ocr_backend` also takes `pdf_inspector_ocr` or `indra_ocr` (one local backend alone
produced the text) and `mixed` (more than one backend did). Five
further scalar keys — `ocr_pages_native`, `ocr_pages_local`,
`ocr_pages_worker`, `ocr_pages_blank`, `ocr_pages_unresolved` — sum to
`page_count` and carry the per-page provenance; see
[page-level routing](#page-level-routing).
Like every key in this section they are excluded from embedding text.

Read them together:

| `ocr_required` | `ocr_used` | `ocr_backend`   | What happened                                    |
| -------------- | ---------- | --------------- | ------------------------------------------------ |
| `false`        | `false`    | `pdf_inspector` | Fast path. Clean text extraction.                |
| `true`         | `true`     | `dots_mocr`     | Primary engine output.                           |
| `true`         | `true`     | `paddleocr_vl`  | Paddle engine output, including fallback use.     |
| `true`         | `false`    | `pdf_inspector` | Degraded. Worker unavailable; partial text only. |

`pages_needing_ocr` is stored as a count, never as the page list
`pdf-inspector` returns internally: no vector store accepts a list-valued
metadata field. All these keys are in `EXCLUDED_EMBED_METADATA_KEYS`, so
they are stored and returned but never embedded and never sent to an LLM.

pdf-inspector decides which pages need OCR from a sample of at most 8
pages. For a `text_based` PDF longer than 8 pages, the adapter scans every
page (`extract_pages_markdown`) so `pages_needing_ocr` also counts scanned
pages outside the sample. The full scan can also count illustration pages
in healthy books (TDR-026).

Two further keys appear only when the extraction-fallback guard fired —
pdf-inspector classified the file `text_based` yet extracted nothing, so
the adapter retried through the tiered fallback chain and recovered the
text (ADR-066, TDR-024):

| Key                                 | Meaning                                                    |
| ----------------------------------- | ---------------------------------------------------------- |
| `extraction_fallback_backend`       | `liteparse` or `pypdf` — the reader that produced the text. |
| `pages_needing_ocr_before_fallback` | The flagged count before the guard zeroed it.              |

The retry is tiered. pdf-inspector stays the primary classifier and
extractor, because it alone emits the routing evidence the OCR gate
reads. On the contradiction the adapter retries with liteparse first,
in self-contained extraction-only mode: OCR is forced off whatever
`LITEPARSE_OCR_ENABLED` says, and `num_workers=None` lets LiteParse
choose automatically without requiring global settings. When liteparse
is not installed, or its retry raises or yields no text, pypdf retries
last. It is the always-available registered plain-text reader, which
preserves the previous coverage.

When recovery succeeds, the adapter sets `pages_needing_ocr` to `0`.
The page routing unit then replaces it with the full-scan count, so
pages the scan flags still go to OCR (see
[page-level routing](#page-level-routing)). When both tiers find no text,
the original flagged count stands and neither key is stamped.
Both keys are parser telemetry and sit in
`EXCLUDED_EMBED_METADATA_KEYS` alongside the OCR keys.

### Re-ingestion consequence

The OCR routing configuration and the resolved worker fingerprint both
participate in the index identity. See
[Index identity and re-ingestion](configuration.md#index-identity-and-re-ingestion).

## Document backends

Document reading dispatches through a registry selected by `DOCUMENT_BACKEND`.

| Value   | Reads                            | Install                 |
| ------- | -------------------------------- | ----------------------- |
| `local` | All supported formats (default)  | Base dependency         |
| `azure` | `.pdf`, `.docx`, and `.doc` only | `uv sync --extra azure` |

Files outside azure's list read through the local backend even when
`DOCUMENT_BACKEND=azure`. An unknown value fails server start-up and
lists the registered names.

Azure needs credentials (`AZURE_DOC_INTELLIGENCE_ENDPOINT`,
`AZURE_DOC_INTELLIGENCE_KEY`) and the optional package. Either piece
missing degrades azure to local before any file is read; each warning
names what is missing. At read time a failed azure attempt retries once
after a 5-second delay, then falls back to local exactly once. Every
step logs a diagnostic naming what happened, so a local-served file is
never silent.

Both backends run their blocking parser work in worker threads, so a
long parse never blocks the MCP event loop.

## Document chunking strategy contract

The chunker (`core/ingestion/chunker.py`) first routes code and
configuration files by content type. All other files are documents. Both
document branches use the same strategy:

- **Structured reads** (cloud parsers that return paragraphs or tables).
- **Unstructured reads** (the local reader chain, with file-level
  metadata extraction).

For each document read, the chunker resolves `sentence` through
`core/chunking/registry.py` and awaits the registered callable. The
chunker does not call private sentence helpers. A replacement that you
register under `sentence` therefore runs during ordinary ingestion.

The chunker calls the strategy with these arguments:

```python
nodes = await strategy(
    documents,  # LlamaIndex Documents from the document backend
    str(file_path),  # used for logging only
    is_markdown,  # `.md` suffix OR reader-declared Markdown
    chunk_size=...,  # markdown_chunk_size for Markdown, else chunk_size
    chunk_overlap=...,  # resolved overlap, or the caller override
    settings=resolved,  # the injected EffectiveSettings
    markdown_chunking=...,  # resolved Markdown chunking value, else None
)
```

The strategy owns splitting. For Markdown, it also owns the shared
post-processing (heading metadata, heading prepend, small-chunk drop).
The chunker applies post-processing exactly once, through the strategy.
A replacement strategy must apply its own Markdown post-processing.

The chunker keeps these responsibilities:

- Reading the file once through the document backend.
- PDF text normalisation before the strategy call.
- The `content_type` metadata on every node.
- File-level metadata attachment (unstructured reads only).
- The metadata-degradation marker on the returned chunk list.

The chunker accepts an optional keyword-only `store`. The ingestion
pipeline passes the vector store that it writes to. The chunker forwards
that store to metadata extraction, so category lookup reads the owning
store. When `store` is omitted, metadata extraction uses only the seed
categories.

## Supported file formats

`.pdf` `.docx` `.pptx` `.txt` `.md` `.html` `.csv`

For directories, the server recursively finds all supported files.

The set is the **documents-profile default**. It is profile-scoped, not a
global constant: the `codebase` profile collects the seven above plus
source extensions for the languages the AST extractor maps to tree-sitter
grammars (`.py`, `.ts`, `.go`, and more — see `config/profiles/codebase.yaml`),
so those files reach the AST-aware code chunker. Override per machine with
`INGESTION__INGEST_EXTENSIONS` (comma-separated). Binary files are skipped
under every profile — content-type detection rejects them even when the
extension is admitted.

## Embedding models

Set `EMBED_MODEL` in `.env` to any Ollama embedding model:

| Model                    | Params | Dims  | Context | MTEB | Pull command                       | Notes                                                                    |
| ------------------------ | ------ | ----- | ------- | ---- | ---------------------------------- | ------------------------------------------------------------------------ |
| **qwen3-embedding:0.6b** | ~600M  | 1,024 | 32,768  | —    | `ollama pull qwen3-embedding:0.6b` | **Default** — 100% Hit@1 in experiments, practical ingest times          |
| nomic-embed-text         | 137M   | 768   | 8,192   | 62.4 | `ollama pull nomic-embed-text`     | Fastest query latency (~36ms), but lower retrieval quality (94.1% Hit@1) |
| mxbai-embed-large        | 334M   | 1,024 | 512     | 64.7 | `ollama pull mxbai-embed-large`    | Highest MTEB score for short chunks                                      |
| all-minilm               | 23M    | 384   | 256     | ~58  | `ollama pull all-minilm`           | Blazing fast, tiny footprint                                             |

See [ADR-009](../adr/009-switch-to-qwen3-embedding-0-6b.md) for the full evidence behind the default model choice.

> **llama.cpp provider:** When `EMBED_PROVIDER=local` and `LOCAL_BACKEND=llamacpp`, set `LLAMACPP_EMBED_MODEL` to the GGUF filename instead of `EMBED_MODEL`. The same models are available in GGUF format from HuggingFace. When `EMBED_PROVIDER=cloud` and `CLOUD_BACKEND=openrouter`, set `OPENROUTER_EMBED_MODEL` to a cloud embedding model (e.g., `text-embedding-3-small`). See [Providers](providers.md) for setup.

### How long will ingestion take?

Practical timings on Apple Silicon (M-series) with `qwen3-embedding:0.6b`, default settings (`INGESTION__EMBED_CONCURRENCY=2`, `INGESTION__EMBED_BATCH_SIZE=100`, `CHUNKING__CHUNK_SIZE=512`):

| Scenario                                     | Time        |
| -------------------------------------------- | ----------- |
| 1 PDF (~117 chunks)                          | ~14 seconds |
| 5 PDFs (~585 chunks)                         | ~70 seconds |
| 20 PDFs (~2,340 chunks)                      | ~5 minutes  |
| Full Zotero library (57 PDFs, ~6,600 chunks) | ~13 minutes |

For comparison, the larger `qwen3-embedding:8b` model (4,096-dim vectors) takes ~3 hours for the same Zotero library — the 0.6b model is **13× faster** with identical retrieval quality in our tests.

> **Apple Silicon note:** Ollama serialises `/api/embed` requests internally on Apple Silicon, so `INGESTION__EMBED_CONCURRENCY > 2` yields diminishing returns. Setting it to 2 overlaps network round-trips with embedding computation; beyond that, requests queue up in Ollama's internal pipeline.

File reading is sequential. Tune throughput with `INGESTION__EMBED_BATCH_SIZE` and `INGESTION__EMBED_CONCURRENCY` rather than file-reader worker settings.

Run `uv run omrs benchmark` to measure throughput on your own hardware.

### Switching models

```bash
# 1. Pull the new model
ollama pull mxbai-embed-large

# 2. Update .env
EMBED_MODEL=mxbai-embed-large

# 3. Re-index your documents into a fresh collection
omrs ingest /path/to/docs/
```

> **Why re-index?** The selected vector store locks the vector dimension at collection creation time. Each model produces a different dimension (nomic=768, mxbai=1024, minilm=384). Switching models requires a fresh collection.

## Chunk size guide

Two budgets apply, depending on the source.

### Non-Markdown sources: character budget

`--chunk-size` controls how many **characters** go into each chunk for plain text and other
non-Markdown sources. The embedding model has a **context length** in **tokens**. A rough guide:
~4 characters ≈ 1 token for English.

| Model                | Context (tokens) | Max safe chunk-size | Default 512 safe? |
| -------------------- | ---------------- | ------------------- | ----------------- |
| qwen3-embedding:0.6b | 32,768           | ~130,000 chars      | Yes               |
| nomic-embed-text     | 8,192            | ~32,000 chars       | Yes               |
| mxbai-embed-large    | 512              | ~1,500 chars        | Yes               |
| all-minilm           | 256              | ~1,000 chars        | Yes               |

The default 512-character chunk size is safe for all models. For models with large context windows:

```bash
# 2048-char chunks are fine (2048 × 0.25 = 512 tokens)
omrs ingest /path/to/docs/ --chunk-size 2048
```

### Markdown sources: token budget (default since ADR-063 promotion)

Markdown files (`.md`, or any reader that declares its output as Markdown, such as the PDF
text path) are chunked by the Rust-backed `semantic-text-splitter` using the configured
embedding tokenizer — real token units, not a characters-per-token guess
([ADR-063](../adr/063-model-token-aware-markdown-chunking.md); promoted to the packaged
default after [experiment 25](../../experiments/25-token-chunking-ablation-2026-09-08/results.md)
passed all four frozen gates: retrieval neutral, embedded tokens −2.5%, largest chunk
halved).

| Setting                                 | Default                                    | Meaning                                                                                          |
| --------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| `EMBEDDING__TOKENIZER_MODEL`            | `Qwen/Qwen3-Embedding-4B`                  | Tokenizer identity for the budget                                                                |
| `EMBEDDING__TOKENIZER_REVISION`         | `5cf2132abc99cad020ac570b19d031efec650f2b` | Pinned revision; must be in the local Hugging Face cache                                         |
| `CHUNKING__MARKDOWN_CHUNK_SIZE`         | `1024`                                     | Maximum chunk size in tokenizer units                                                            |
| `CHUNKING__MARKDOWN_HEADING_PREPEND`    | `false`                                    | Prepend the heading path to each chunk. When on, the prepended text counts against the token cap |
| `CHUNKING__MARKDOWN_MIN_CHUNK_FRACTION` | `0.0`                                      | Filter chunks below this fraction of the cap (measured in real tokens on this path)              |

The contract, in short:

- The splitter prefers structural boundaries — headings, sections, tables, lists, paragraphs —
  and only then splits smaller. Nothing is emitted over the cap.
- The cap governs the finalised chunk text. A heading prefix that would push a chunk over the
  cap reduces the space for content instead of being dropped or overflowing; a Markdown
  structure that cannot fit at all fails that one file (`status="failed"`), never the batch.
- The tokenizer is a **local cache artefact** and is independent of the embedding inference
  provider: whether embeddings run through Ollama, llama.cpp, or OpenRouter, the budget uses
  the pinned Hugging Face tokenizer, never an inference-server alias.

Cache the tokenizer once (offline thereafter):

```bash
hf download Qwen/Qwen3-Embedding-4B tokenizer.json \
  --revision 5cf2132abc99cad020ac570b19d031efec650f2b
```

If the revision is not cached, ingestion logs a warning naming the failure and falls back to
the legacy character-budgeted splitter for that run. Setting both `EMBEDDING__TOKENIZER_*`
fields empty makes the legacy path permanent (explicit opt-out).

The resolved tokenizer identity and splitter participate in the source index identity, so
changing the identity, revision, or cache availability re-chunks every Markdown source on
the next ingest — by design, so one collection never mixes chunking strategies.

## Progress and interruption

Progress bars appear automatically in TTY terminals (Rich). In non-TTY contexts (pipes, CI) plain text is emitted to stderr. Press Ctrl+C once for graceful shutdown (finishes the current file, skips the rest). Press again to force quit.

## Which model runs when

| Stage                              | Model type                                  | What it does                 | Speed impact            |
| ---------------------------------- | ------------------------------------------- | ---------------------------- | ----------------------- |
| Metadata extraction (local mode)   | Chat/LLM (e.g. qwen3:0.6b)                  | Classifies document category | ~2s per file            |
| Metadata extraction (keyword mode) | None (regex)                                | Pattern matching             | Instant                 |
| Embedding                          | Embedding model (e.g. qwen3-embedding:0.6b) | Converts text to vectors     | ~50–500ms per chunk     |
| Search (rerank)                    | Cross-encoder (ms-marco-MiniLM-L-6-v2)      | Re-scores top results        | ~10–50ms per query pair |

The embedding model and chat/classification model are **separate** — each pulled independently via Ollama.
