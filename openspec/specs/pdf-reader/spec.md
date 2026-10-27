## Purpose

Define a pluggable PDF reader architecture with environment-variable-driven backend selection, bounding-box metadata capture, graceful fallback across multiple parser backends, and structured error handling for MCP tool compliance.

## Requirements

### Requirement: PDF reader SHALL be selectable via environment variable

The system SHALL read a `PDF_READER` environment variable at config-load
time into the frozen `Settings.pdf_reader` field. Accepted values SHALL be
`auto`, `pdf_inspector`, `liteparse`, `pypdfium2`, and `pypdf`. Any other
value SHALL log a warning naming the offending value and fall back to
`auto`.

#### Scenario: Explicit pdf-inspector selection via env var

- **WHEN** `PDF_READER=pdf_inspector` is set and the package is importable
- **THEN** the injected `EffectiveSettings.pdf_reader` SHALL equal `"pdf_inspector"` and its adapter SHALL ingest all `.pdf` files

#### Scenario: Explicit override selection via env var

- **WHEN** `PDF_READER=liteparse` is set and the `liteparse` package is importable
- **THEN** the injected `EffectiveSettings.pdf_reader` SHALL equal `"liteparse"` and the LiteParse adapter SHALL be used for all `.pdf` ingestion

#### Scenario: Unknown value falls back to auto with warning

- **WHEN** `PDF_READER=fastparser` (an unsupported value) is set
- **THEN** the system SHALL log a warning naming the offending value and the fallback, and SHALL resolve as if `PDF_READER=auto` had been set

### Requirement: The composition root resolves auto once at startup

The composition root SHALL resolve `auto` to a concrete backend
name exactly once at startup and bake the result into the injected
`EffectiveSettings.pdf_reader`; no module-level resolved constant exists.

#### Scenario: Resolution happens once at the composition root

- **WHEN** the server or CLI entry point starts
- **THEN** `compose.resolve_pdf_reader` SHALL run once over the frozen settings
- **AND** every operation below the entry point SHALL read the concrete name from its injected settings, with no repeated probing

### Requirement: A pipeline step may select its own concrete PDF reader

The resolved value SHALL be the host default reader. A pipeline's Read
document step MAY select another registered concrete reader for that step
only. A step selection SHALL NOT change the environment, the frozen
`Settings.pdf_reader` field or the resolved host default, and SHALL NOT be
`auto`.

#### Scenario: Step selection leaves the host default unchanged

- **WHEN** the host default reader is `pypdf` and one pipeline's Read document step selects `pdf_inspector`
- **THEN** that step SHALL read PDF files with `pdf_inspector`
- **AND** the standard ingest path, other pipelines and steps that inherit SHALL keep reading with `pypdf`
- **AND** the environment and the injected host settings SHALL remain unchanged

#### Scenario: Step selection cannot be auto

- **WHEN** a Read document step sets its reader to `auto`
- **THEN** validation SHALL reject the value before any node runs
- **AND** the message SHALL tell the user to choose a concrete reader or inherit the host reader

### Requirement: Auto resolution SHALL probe backends in preference order with graceful fallback

When the configured reader is `auto`, the system SHALL probe backend imports
in the order `liteparse → pypdfium2 → pypdf` and SHALL select the first
importable backend. PyMuPDF is structurally excluded from accepted values
entirely (AGPL-3 incompatibility). If no optional backend is installed, the
system SHALL fall back to `pypdf` (always available via
`llama-index-readers-file`).

#### Scenario: LiteParse installed and selected by auto

- **WHEN** the configured reader is `auto` and the `liteparse` package is importable
- **THEN** the resolved reader SHALL be `liteparse`

#### Scenario: LiteParse missing, pypdfium2 installed

- **WHEN** the configured reader is `auto`, `liteparse` is not importable, and `pypdfium2` is importable
- **THEN** the resolved reader SHALL be `pypdfium2` and the system SHALL log an informational message that LiteParse was not available

#### Scenario: No optional backend installed

- **WHEN** the configured reader is `auto` and neither `liteparse` nor `pypdfium2` is importable
- **THEN** the resolved reader SHALL be `pypdf` and ingestion SHALL behave identically to the pre-change pipeline

#### Scenario: Explicit backend requested but not installed

- **WHEN** the configured reader is `liteparse` but `liteparse` is not importable
- **THEN** the system SHALL log an error naming the missing package and SHALL fall back to `pypdf` rather than raising

### Requirement: Direct factory callers get the same auto preference order

The composition root resolves `auto` once at startup and injects the concrete
name. Callers that bypass the composition root (direct library use, tests)
SHALL receive the same preference order from the reader factory's local
resolution, so the selected backend is identical on both paths for the same
installed packages.

#### Scenario: Factory-local auto resolution matches composition-root order

- **WHEN** the reader factory resolves `auto` for a caller that bypassed the composition root, `liteparse` is not importable, and `pypdfium2` is importable
- **THEN** the factory SHALL return the `pypdfium2` adapter
- **AND** the selection SHALL match what the composition root would have resolved for the same installed packages

### Requirement: Reader failures SHALL surface as MCP error dictionaries, never exceptions

The ingestion pipeline SHALL catch every per-file reader failure (corrupt
PDF, native failure surfaced as a Python exception, IO failure, encoding
error) around the chunking stage
and convert it into a structured file detail through
`core/ingestion/loader.py:make_file_detail`:
`{"file": "<filename>", "status": "failed", "chunks": 0, "error":
"<human-readable detail>"}`. Reader adapters themselves SHALL NOT be
required to catch their parser's exceptions.

#### Scenario: LiteParse native crash

- **WHEN** the LiteParse native library crashes (segfault wrapper, FFI panic, or Rust panic propagated through `pyo3`)
- **THEN** the ingestion pipeline SHALL catch the resulting Python-visible exception, log it, and append a structured error detail
- **AND** ingestion of subsequent files in the same batch SHALL continue uninterrupted

#### Scenario: Error contract matches make_file_detail shape

- **WHEN** the ingestion pipeline converts any reader failure into a file detail
- **THEN** the dictionary SHALL contain exactly the keys `file` (str), `status` (literal `"failed"`), `chunks` (int `0`), and `error` (str with human-readable detail)
- **AND** the dictionary SHALL be appendable to the `file_details` list in `ingest_path_async` without further transformation

### Requirement: No reader exception escapes ingestion or an MCP tool handler

No exception SHALL propagate
out of `ingest_path_async` or any MCP tool handler, per the project's
"Never raise from MCP tool handlers" gotcha (AGENTS.md).

#### Scenario: Corrupt PDF raises inside adapter

- **WHEN** a `.pdf` file is structurally corrupt and the underlying parser raises an exception
- **THEN** the ingestion pipeline SHALL catch the exception, log it with the filename, and append a structured error detail with `status="failed"` and a descriptive message
- **AND** the exception SHALL NOT propagate to the `ingest_documents` caller

### Requirement: LiteParse adapter SHALL capture bounding-box metadata on emitted Documents

When the LiteParse adapter is in use, every emitted `Document` object SHALL carry a `metadata` dictionary containing spatial information extracted by LiteParse. The metadata SHALL include the keys `pdf_reader="liteparse"`, `page=<int>` (1-indexed), `column=<"left"|"right"|"single"|"multi_column">`, `section_bbox=<[x0, y0, x1, y1]>` (page-coordinate space), and `bbox_schema_version=1`. Retrieval-side consumption of these fields is out of scope for this change.

#### Scenario: Single-column PDF
- **WHEN** a single-column PDF is ingested via the LiteParse adapter
- **THEN** each emitted Document SHALL have `metadata["column"]` set to `"single"`

#### Scenario: Non-LiteParse readers do not emit bbox fields
- **WHEN** a PDF is ingested via the pypdf or pypdfium2 adapter
- **THEN** emitted Documents SHALL NOT carry `section_bbox`, `column`, or `bbox_schema_version` keys (these are LiteParse-specific)
- **AND** `metadata["pdf_reader"]` SHALL be set to the backend name (`"pypdf"` or `"pypdfium2"`) for diagnostics

### Requirement: Pages joined column by column are labelled multi_column

A page the adapter joins column by column SHALL carry `column="multi_column"`, so the label names the order the text is in.

#### Scenario: Two-column academic PDF
- **WHEN** a two-column academic PDF is ingested via the LiteParse adapter
- **THEN** each emitted Document for a page joined column by column SHALL have `metadata["column"]` set to `"multi_column"`
- **AND** a two-column page the classifier does not recognise SHALL keep `"left"` or `"right"`
- **AND** `metadata["page"]` SHALL reflect the 1-indexed source page number

### Requirement: Reader factory SHALL be extensible without modifying ingestion code

New reader adapters SHALL be addable by creating a single module in
`src/omrs/integrations/pdf/` and registering it with one
`registry.register()` call. The shared contract is the duck-typed
`load_data(file) -> list[Document]` method — there is no separate protocol
module. The factory receives the reader name from its
caller: `get_pdf_reader(reader)`.

#### Scenario: Factory returns adapter, not reader instance

- **WHEN** `get_pdf_reader(reader)` is called with a concrete reader name
- **THEN** it SHALL return an adapter instance with a `load_data` method, not a parsed-document instance, so `SimpleDirectoryReader(file_extractor={".pdf": get_pdf_reader(resolved.pdf_reader)})` works at the ingestion call site

#### Scenario: Factory dispatch behaviour unchanged

- **WHEN** the `auto` backend resolution runs after the relocation
- **THEN** backend preference order, graceful fallback, and `PDF_READER` env var handling SHALL be identical to the pre-refactor factory (ADR-020 amended for location only)

### Requirement: Adding a reader leaves the ingestion call sites unchanged

The ingestion call sites SHALL NOT require modification when a new
reader is added; only the accepted values in `config/` and the registry
registration SHALL change.

#### Scenario: Adding a new adapter

- **WHEN** a developer creates `src/omrs/integrations/pdf/spdf.py` with a `load_data` method and adds `"spdf"` to the accepted values in `config/` plus one `register("spdf", "...")` call in the registry
- **THEN** no other source file SHALL require modification to make `PDF_READER=spdf` functional

### Requirement: LiteParse SHALL be a core dependency

Both `liteparse` and `pdf-inspector` SHALL be declared in the main
`[project.dependencies]` list in `pyproject.toml`, not as optional extras.
The base `uv sync` SHALL install both packages and make the configured
default available without an optional dependency extra. The `auto`
resolution order SHALL prefer LiteParse when importable.

#### Scenario: Baseline install includes pdf-inspector
- **WHEN** a user runs `uv sync` without any extras
- **THEN** `pdf_inspector` and `liteparse` SHALL be importable

#### Scenario: Explicit override to LiteParse
- **WHEN** a user sets `PDF_READER=liteparse` in `.env`
- **THEN** the system SHALL use LiteParse regardless of pdf-inspector availability

### Requirement: PDF reader default SHALL be configuration-owned after Experiment 14 validation

The packaged `PDF_READER` default SHALL be `pdf_inspector`. The selected
backend SHALL remain configurable through `PDF_READER`; `auto` SHALL retain
its existing capability-resolution and graceful-fallback behaviour. Experiment
14 validated this promotion with zero parser failures, a 346.7-second ingest
run, and the highest reranked Hit@5 result (0.6250).

#### Scenario: Packaged default selects pdf-inspector

- **WHEN** no `PDF_READER` environment variable is set
- **THEN** the resolved reader SHALL be `"pdf_inspector"`

#### Scenario: Environment override takes precedence

- **WHEN** `PDF_READER=pypdf` is set
- **THEN** the system SHALL use pypdf regardless of the packaged default

#### Scenario: Missing configured backend falls back safely

- **WHEN** `PDF_READER=pdf_inspector` is configured but the package is not importable
- **THEN** the system SHALL log an error naming the missing package and fall back to pypdf rather than raising

### Requirement: Readers declare their emitted text format

Each registered PDF reader SHALL declare the text format it emits and whether
it provides page-level provenance as registry metadata, alongside its existing
import path and dependency probe. Downstream consumers SHALL route on the text
format declaration rather than inferring format from the source file's
extension, and SHALL be able to report the page capability.

#### Scenario: Declared formats

- **WHEN** the PDF reader registry is inspected
- **THEN** `pdf_inspector` MUST declare `markdown`
- **AND** `liteparse`, `pypdf`, and `pypdfium2` MUST declare `plain`

#### Scenario: A new reader must declare a format

- **WHEN** a reader is registered without a text-format declaration
- **THEN** registration MUST fail rather than defaulting silently

### Requirement: Page provenance is honest per reader

Readers that can observe page boundaries SHALL emit `page_label`, the key
retrieval reads. Readers that cannot SHALL emit nothing rather than a
placeholder, and the system SHALL NOT promise the field where it cannot be
produced.

#### Scenario: liteparse emits page_label

- **WHEN** a PDF is parsed by `liteparse`
- **THEN** each emitted document MUST carry `page_label` as a string
  alongside the existing integer `page`
- **AND** a chunk retrieved from that document MUST return a non-null
  `page_label`

#### Scenario: pypdfium2 emits page_label

- **WHEN** a PDF is parsed by `pypdfium2`
- **THEN** each emitted page document MUST carry `page_label` as a string
  alongside the existing integer `page`
- **AND** a chunk retrieved through the `auto` chain MUST preserve it

#### Scenario: pdf_inspector emits page_label

- **WHEN** a PDF is parsed by `pdf_inspector` and its per-page extraction succeeds
- **THEN** each emitted page document MUST carry `page_label` as a string
  alongside the existing integer `page`
- **AND** the reader MUST continue to report `page_count` in metadata so an
  operator can see the document's true length

#### Scenario: pdf_inspector reports no page

- **WHEN** `pdf_inspector` emits the whole-document Markdown as one document,
  because its per-page extraction failed or gave no text
- **THEN** `page_label` MUST be absent rather than fabricated
- **AND** the reader MUST continue to report `page_count` in metadata so an
  operator can see the document's true length

#### Scenario: Page support is discoverable

- **WHEN** an operator or caller inspects the configured reader through the
  registry descriptor
- **THEN** the descriptor MUST report whether page-level provenance is
  available under that configuration
- **AND** `pdf_inspector` MUST report that it is available

### Requirement: pdf-inspector SHALL route OCR-required PDFs to an isolated document-understanding worker

When the configured PDF path uses `pdf_inspector`, the system SHALL use the existing `pdf-inspector` result as both the fast extraction result and the evidence for deciding whether OCR/document understanding is required. Text-based PDFs with acceptable extraction quality SHALL keep the `pdf-inspector` Markdown.

#### Scenario: Clean text-based PDF stays on pdf-inspector without starting the parsing worker

- **GIVEN** `pdf_inspector` is the configured PDF path and the OCR worker is available
- **AND** `pdf-inspector` classifies the PDF as text-based with acceptable extraction quality and no material OCR requirement
- **AND** the PDF has no maths pages
- **WHEN** the PDF is ingested
- **THEN** the `pdf-inspector` Markdown SHALL be used
- **AND** no OCR parse request SHALL be dispatched
- **AND** the long-lived worker and its model SHALL NOT be started

### Requirement: Scanned PDFs always route to OCR and other PDFs route by threshold

When an OCR route is available and OCR is enabled, scanned and image-based PDFs SHALL route unconditionally. Other types, including mixed PDFs, SHALL route only when a positive configured threshold condition is met, or when the maths-page condition is met. A confidence below the minimum or an OCR-page proportion at or above the configured fraction SHALL select OCR. A zero threshold SHALL disable its condition.

#### Scenario: Scanned or image-based PDF uses the OCR worker

- **GIVEN** `pdf-inspector` classifies a PDF as scanned or image-based
- **AND** the capability probe reports that the primary OCR route is available and compatible
- **WHEN** the PDF is ingested
- **THEN** the whole PDF SHALL be parsed by the primary OCR route
- **AND** the worker result SHALL replace the partial `pdf-inspector` extraction as the downstream document text

#### Scenario: Mixed PDF with zero thresholds stays on the fast path

- **GIVEN** OCR is enabled and a PDF is classified as mixed
- **AND** both routing thresholds are zero
- **AND** the PDF has no maths pages
- **WHEN** the PDF is ingested
- **THEN** no OCR parse request SHALL be dispatched
- **AND** the existing extracted Markdown and page diagnostics SHALL be preserved

### Requirement: OCR dispatch uses the primary route before the fallback route

Every dispatch SHALL use the primary OCR route (dots.mocr by default), and the fallback route (PaddleOCR-VL by default) when the primary is unavailable before dispatch.

#### Scenario: OCR required but the worker is unavailable

- **GIVEN** `pdf-inspector` reports that OCR is required
- **AND** both OCR routes are absent, unprovisioned, incompatible, or unusable before dispatch
- **WHEN** the PDF is ingested
- **THEN** the system SHALL retain the available `pdf-inspector` Markdown rather than fabricate missing content
- **AND** the document/file result SHALL report that OCR was required but unavailable
- **AND** ingestion SHALL remain within the existing per-file degradation boundary

### Requirement: Layout complexity alone does not route a PDF to OCR

Layout complexity alone SHALL NOT require OCR. A text-based multi-column or table-heavy PDF that `pdf-inspector` extracts acceptably SHALL remain on the fast path, unless it has maths pages.

#### Scenario: Complex text layout does not imply OCR

- **GIVEN** a text-based PDF containing multiple columns or tables and no maths pages
- **AND** `pdf-inspector` extracts the layout with acceptable quality
- **WHEN** the PDF is ingested
- **THEN** the PDF SHALL remain on the `pdf-inspector` path
- **AND** layout complexity alone SHALL NOT start or invoke the OCR worker

### Requirement: The document routing unit sends the whole PDF to the worker

With the `document` routing unit (the default), the system SHALL route the whole PDF to the worker when the OCR condition is met and SHALL NOT merge page fragments from two PDF engines. With the `page` routing unit, routing SHALL follow the page-level OCR routing requirement instead.

#### Scenario: Mixed PDF with material OCR requirement uses the worker

- **GIVEN** the `document` routing unit is configured
- **AND** `pdf-inspector` reports mixed content or material `pages_needing_ocr`
- **AND** the configured routing gate selects OCR
- **AND** the capability probe reports that the primary OCR route is available and compatible
- **WHEN** the PDF is ingested
- **THEN** the whole PDF SHALL be parsed by the primary OCR route
- **AND** the system SHALL NOT stitch independently parsed page fragments from the two engines

### Requirement: The PaddleOCR-VL fallback SHALL run in an isolated worker environment

The fallback-route OCR engine SHALL be PaddleOCR-VL, and the primary-route engine SHALL be dots.mocr. PaddleOCR-VL SHALL use the supported PaddleOCR-VL document pipeline, including layout/region processing, reading-order handling, recognition, and result assembly. It SHALL NOT treat the VLM checkpoint as a bare whole-page string OCR call when the pipeline can preserve document structure.

#### Scenario: Worker result preserves structured document elements

- **GIVEN** an OCR-required PDF containing headings, paragraphs, and a table
- **WHEN** an isolated engine successfully parses the document
- **THEN** the emitted text SHALL be Markdown
- **AND** structural elements available from the parser SHALL be represented in that Markdown rather than flattened into an undifferentiated text stream

### Requirement: Every OCR engine runs from its own locked environment

Every OCR engine SHALL run as a local subprocess in a separate environment provisioned from its own engine-owned lockfile. Each engine project SHALL declare Python `>=3.11,<3.14` and SHALL own all of its model-runtime packages: PaddleOCR, PaddleX and PaddlePaddle for PaddleOCR-VL; PyTorch and transformers for dots.mocr; and any accelerator packages.

#### Scenario: Worker is provisioned from its own lockfile

- **GIVEN** a Python interpreter in the supported `>=3.11,<3.14` range
- **WHEN** an OCR engine is provisioned
- **THEN** its environment SHALL be resolved from that engine's lockfile
- **AND** provisioning SHALL NOT add the engine's packages to OMRS's main environment

#### Scenario: Worker smoke test is independent of the main environment

- **GIVEN** an engine has been provisioned from its lockfile
- **WHEN** its standalone smoke test runs
- **THEN** the capability probe SHALL return a schema-valid manifest
- **AND** a small OCR fixture SHALL return schema-valid structured Markdown
- **AND** the test SHALL NOT require the engine's packages in OMRS's main environment

### Requirement: The main OMRS environment holds no OCR engine packages

OMRS's main package metadata, root lockfile, and main runtime environment SHALL NOT include any engine's model-runtime packages. OMRS runtime modules SHALL NOT import them. The OMRS side SHALL communicate with every engine only through the subprocess protocol.

#### Scenario: Main OMRS environment remains Paddle-free

- **GIVEN** OMRS is installed from its main package metadata and root lockfile
- **WHEN** the package starts and processes content without any engine environment
- **THEN** no PaddleOCR, PaddleX, PaddlePaddle, PyTorch or transformers package SHALL be required or imported
- **AND** the server SHALL remain usable for every existing non-OCR path

### Requirement: Every OCR engine emits structured Markdown

Every engine SHALL emit structured Markdown suitable for the same downstream Markdown chunking path used by `pdf-inspector` output.

#### Scenario: Engine output suits the Markdown chunking path

- **WHEN** any OCR engine emits a parse result
- **THEN** the result SHALL be structured Markdown suitable for the same downstream Markdown chunking path used by `pdf-inspector` output

### Requirement: The OCR worker SHALL use a versioned JSON Lines protocol

OMRS SHALL send UTF-8 requests as one complete JSON object per line on the worker's standard input. The worker SHALL return one complete JSON object per line on standard output. Every request and response SHALL include a request identifier and protocol version. Every accepted parse request SHALL receive one terminal success or error response with the same request identifier while the worker remains healthy.

#### Scenario: Parse request and response remain correlated

- **GIVEN** the routing gate selects OCR and the worker capability is compatible
- **WHEN** OMRS writes a parse request line to the worker
- **THEN** the worker SHALL return one terminal JSON response line with the same request identifier
- **AND** the response SHALL declare the negotiated protocol and output-schema identities

### Requirement: Worker standard output carries protocol messages only

Standard output SHALL contain protocol messages only. Worker diagnostics and operational logs SHALL use standard error so they cannot corrupt protocol framing. OMRS SHALL drain standard error independently from standard output.

#### Scenario: Worker logging does not contaminate protocol output

- **GIVEN** the worker emits a diagnostic while handling a request
- **WHEN** OMRS reads the worker streams
- **THEN** the diagnostic SHALL be read from standard error
- **AND** standard output SHALL remain parseable as JSON Lines protocol messages only

### Requirement: The capability probe reports the worker fingerprint without loading the model

The capability probe SHALL report worker availability, protocol version, relevant package names and exact versions, pipeline identity and revision, model identity and revision, and output-schema identity and version. It SHALL use metadata and static worker declarations without initialising Paddle, importing model code, loading model weights, or leaving the long-lived parsing worker running.

#### Scenario: Capability probe returns the worker fingerprint without loading the model

- **GIVEN** the isolated worker environment is provisioned
- **WHEN** OMRS performs the capability probe
- **THEN** the probe SHALL report availability and every required worker identity field
- **AND** it SHALL NOT initialise Paddle or import model code
- **AND** it SHALL NOT leave a long-lived parsing worker running

### Requirement: An unusable or incompatible worker is unavailable before dispatch

Missing files, an unusable environment, malformed probe output, or an incompatible protocol SHALL produce a stable unavailable fingerprint before parse dispatch.

#### Scenario: Incompatible worker is unavailable before dispatch

- **GIVEN** the capability probe reports an unsupported protocol or output-schema identity
- **WHEN** an OCR-required PDF reaches the routing seam
- **THEN** OMRS SHALL NOT dispatch the PDF to that worker
- **AND** the unavailable-worker degradation behaviour SHALL apply

### Requirement: A successful parse response conforms to the reported output schema

A successful parse response SHALL contain structured Markdown and metadata that conform to the reported output schema.

#### Scenario: Successful parse response follows the reported schema

- **WHEN** the worker returns a successful parse response
- **THEN** the response SHALL contain structured Markdown and metadata that conform to the output schema the capability probe reported

### Requirement: The OCR parsing worker SHALL be lazy and long-lived

The long-lived parsing subprocess and its model SHALL start only when the first OCR parse request is dispatched. A healthy subprocess SHALL be reused for later OCR requests owned by the same engine. The client SHALL permit one request in flight at a time. The owning engine SHALL close the subprocess during orderly shutdown.

#### Scenario: First OCR dispatch starts the worker

- **GIVEN** the capability probe reports an available worker
- **AND** no OCR parse request has yet been dispatched
- **WHEN** the routing seam dispatches the first OCR-required PDF
- **THEN** the long-lived parsing subprocess SHALL start
- **AND** the OCR model SHALL initialise within that subprocess

#### Scenario: Healthy worker is reused

- **GIVEN** a healthy parsing worker has completed one OCR request
- **WHEN** another OCR-required PDF is dispatched by the same owner
- **THEN** the existing subprocess SHALL handle the request
- **AND** the model SHALL NOT be initialised in a second subprocess

#### Scenario: Owner shutdown closes the worker

- **GIVEN** the owner has a running parsing worker
- **WHEN** the owner shuts down normally
- **THEN** it SHALL close the worker's input and terminate the subprocess within a bounded period

### Requirement: A failed parsing worker is replaced and its request is not replayed

A timed-out, crashed, or protocol-invalid subprocess SHALL be discarded. The failed request SHALL NOT be replayed automatically. A later OCR request SHALL start a fresh subprocess when the capability remains available, but the failed file SHALL retain its structured per-file error result.

#### Scenario: Later request replaces a failed worker

- **GIVEN** a parsing worker timed out or crashed during an earlier request
- **WHEN** a later OCR-required PDF is dispatched
- **THEN** the failed subprocess SHALL NOT be reused
- **AND** a fresh subprocess SHALL be started for the later request

### Requirement: Post-dispatch worker failure SHALL be a structured per-file error

Parse dispatch occurs when OMRS has written and flushed the complete JSON Lines request. If the worker times out, crashes, closes its output, violates the protocol, or returns a structured error after that point, OMRS SHALL return a structured error for that file. It SHALL NOT report the partial `pdf-inspector` result as a successful or degraded extraction for the failed attempt.

#### Scenario: Worker times out after parse dispatch

- **GIVEN** OMRS has written and flushed a complete parse request
- **WHEN** the worker does not return a terminal response within the configured timeout
- **THEN** that file SHALL receive a structured timeout error
- **AND** its source version SHALL NOT be marked current
- **AND** subsequent files in the batch SHALL continue

### Requirement: A failed OCR attempt does not replace the current source version

The failed source version SHALL NOT be marked current. The existing failure-safe replacement boundary SHALL preserve any prior current version. Other files in the same ingestion batch SHALL continue within the existing per-file error boundary.

#### Scenario: Worker crashes after parse dispatch

- **GIVEN** OMRS has written and flushed a complete parse request
- **WHEN** the worker exits before returning the terminal response
- **THEN** that file SHALL receive a structured worker-crash error
- **AND** its source version SHALL NOT be marked current
- **AND** any prior current source version SHALL be preserved
- **AND** subsequent files in the batch SHALL continue

### Requirement: PDF extraction branches SHALL converge on one structured-Markdown contract

Successful `pdf-inspector` extraction and successful extraction by any OCR engine SHALL provide downstream ingestion with Markdown plus honest metadata. Existing source/provenance metadata SHALL be preserved. OCR-specific metadata SHALL be additive and SHALL NOT overwrite more authoritative existing values.

The change SHALL NOT require a new canonical document class or a second chunking pipeline.

#### Scenario: Fast and OCR paths enter the same Markdown chunking branch

- **GIVEN** one PDF succeeds through `pdf-inspector` and another succeeds through an OCR engine
- **WHEN** their reader results reach document chunking
- **THEN** both SHALL declare or otherwise carry Markdown as their emitted text format
- **AND** both SHALL be eligible for the same Markdown chunking strategy

#### Scenario: OCR diagnostics are honest

- **WHEN** a PDF result is emitted
- **THEN** metadata SHALL make it possible to distinguish whether OCR was required and whether OCR was actually used
- **AND** a result produced only by `pdf-inspector` SHALL NOT claim that an OCR engine processed the document
- **AND** a result produced by an OCR engine SHALL name that engine

### Requirement: Source index identity SHALL include the resolved OCR worker fingerprint

The existing source index identity SHALL include the OCR routing configuration, the sorted unconditional routing type set, and a deterministic worker fingerprint for each OCR route: primary and fallback.

The fingerprints SHALL be recorded for every source through the existing index-identity mechanism. A change to any fingerprint field SHALL invalidate the prior identity so byte-identical sources are re-ingested.

#### Scenario: Worker contract or model change triggers re-ingestion

- **GIVEN** a source was indexed with one resolved fingerprint per route
- **WHEN** the protocol version, package versions, pipeline identity, model identity, or output-schema identity of either route changes
- **THEN** the source index identity SHALL change
- **AND** a byte-identical source SHALL be re-ingested rather than reported `skipped_unchanged`

#### Scenario: Unchanged worker fingerprint preserves unchanged-source behaviour

- **GIVEN** the source bytes, OCR routing configuration, and resolved fingerprints of both routes are unchanged
- **WHEN** the source is ingested again
- **THEN** the worker fingerprints SHALL NOT alone prevent the existing `skipped_unchanged` result

### Requirement: Each OCR route fingerprint lists the worker identity fields

Each fingerprint SHALL include worker availability, protocol version, package names and exact versions, pipeline identity and revision, model identity and revision, and output-schema identity and version. It SHALL exclude transient process details such as process identifiers. An unavailable or unconfigured route SHALL contribute a stable unavailable fingerprint rather than an omitted field.

#### Scenario: Provisioning an unavailable worker triggers re-ingestion

- **GIVEN** a source was indexed while a route's fingerprint recorded unavailable
- **WHEN** that route's engine is provisioned and its capability probe succeeds
- **THEN** the source index identity SHALL change
- **AND** a byte-identical source SHALL be re-ingested rather than reported `skipped_unchanged`

### Requirement: The identity schema advances with each payload amendment

The initial payload extension used schema 4. The routing-policy amendment used schema 5 so existing identities cannot silently omit the unconditional routing set. The two-route amendment SHALL advance the schema by one from the schema current when it lands.

#### Scenario: The two-route amendment advances the schema by one

- **WHEN** the two-route amendment lands
- **THEN** the source index identity schema SHALL advance by one from the schema current when it lands

### Requirement: The OCR routing gate SHALL be calibrated evidence expressed as injected configuration

The threshold that selects the OCR fallback SHALL be a calibrated value carried in injected configuration, not a constant in the routing module. It SHALL follow the shape the existing PDF knobs already use: top-level fields on the effective settings beside `pdf_reader` and `liteparse_ocr_enabled`, resolved once at the composition root and passed downstream.

`config/` SHALL NOT probe the worker, and no module SHALL read a settings singleton to obtain the gate.

#### Scenario: Routing threshold is read from injected settings

- **WHEN** the routing seam decides whether a PDF needs OCR
- **THEN** it SHALL read the gate from the injected effective settings
- **AND** the routing module SHALL NOT contain a hardcoded threshold constant

### Requirement: The routing gate is calibrated on fixtures disjoint from evaluation

The gate SHALL be calibrated on a committed fixture set disjoint from the fixtures used to evaluate whether the OCR fallback improves retrieval. Calibration SHALL report routing behaviour — text-based PDFs the gate would route to OCR, and OCR-required PDFs it would leave on the fast path — and SHALL NOT be the same run that measures downstream retrieval quality.

#### Scenario: Calibration and evaluation fixtures are disjoint

- **GIVEN** the committed PDF calibration fixtures and the committed PDF evaluation fixtures
- **WHEN** the OCR routing gate is calibrated
- **THEN** calibration SHALL use only the calibration fixtures
- **AND** the evaluation fixtures SHALL remain unused until the Stage 5 ablation

### Requirement: Packaged routing defaults ship the promoted gate

The packaged default SHALL be the promoted pair validated by the repeat routing study
(`29-pdf-routing-repeat-2026-09-13`): routing enabled, `0.5` minimum
confidence, `0.10` flagged-page fraction. The enable flag and both
thresholds SHALL ship together — enabling routing while leaving
thresholds at the `0.0` sentinels is the bare-enable configuration the
study showed silently misses threshold-flagged documents, and packaged
defaults SHALL NOT present it.

#### Scenario: Packaged default routes OCR-required PDFs

- **GIVEN** a fresh installation whose operator has set no OCR routing configuration
- **AND** the isolated OCR worker is provisioned and compatible
- **WHEN** a scanned PDF is ingested
- **THEN** the OCR fallback SHALL be selected
- **AND** a healthy text-based PDF SHALL stay on the fast path

#### Scenario: Unprovisioned worker degrades deterministically

- **GIVEN** a fresh installation with no OCR worker provisioned
- **WHEN** an OCR-required PDF is ingested
- **THEN** the file SHALL keep the partial pdf-inspector extraction with degraded diagnostics
- **AND** the batch SHALL continue with an actionable warning naming the provisioning step

### Requirement: pdf-inspector silent-empty extraction SHALL recover via a plain-text retry

When the pdf-inspector reader classifies a PDF as `text_based` while its own Markdown extraction is empty and the page count is greater than zero, the adapter SHALL retry the file with the registered `liteparse` reader in extraction-only mode (OCR disabled regardless of operator settings), keeping one document for each recovered page, so a readable text layer is not silently discarded.

#### Scenario: Normal extraction is untouched

- **GIVEN** pdf-inspector returns non-empty Markdown for a `text_based` PDF
- **WHEN** the adapter emits its documents
- **THEN** no retry SHALL occur
- **AND** the metadata SHALL carry no fallback diagnostics

#### Scenario: Scanned classifications are untouched

- **GIVEN** pdf-inspector classifies a PDF as `scanned`, `image_based`, or another non-`text_based` type
- **WHEN** the adapter emits its documents
- **THEN** no retry SHALL occur regardless of extraction emptiness
- **AND** the OCR routing decision SHALL be unchanged

#### Scenario: Recovered pages keep their numbers

- **GIVEN** the liteparse tier recovers text from pages 1 and 3 of a 3-page PDF
- **WHEN** the adapter emits its documents
- **THEN** it SHALL emit 2 documents with `page` 1 and 3 and `page_label` `"1"` and `"3"`
- **AND** each SHALL carry the pdf-inspector evidence and the fallback diagnostics

### Requirement: The rescue retry needs no default settings and falls back to pypdf

The rescue tier SHALL receive concrete OCR and worker settings so it does not require default effective settings. When liteparse is unavailable or its retry yields no text, the adapter SHALL retry with the registered `pypdf` reader, preserving the same page-document contract.

#### Scenario: Bare direct adapter use stays on liteparse

- **GIVEN** no default effective settings were installed
- **WHEN** the contradiction triggers and liteparse can recover text
- **THEN** the liteparse tier SHALL run with OCR disabled and automatic worker selection
- **AND** pypdf SHALL NOT be selected

#### Scenario: liteparse unavailable falls through to pypdf

- **GIVEN** the contradiction triggers and the liteparse package is not installed, or its retry raises or yields no text
- **WHEN** the adapter emits its documents
- **THEN** the retry SHALL proceed with the registered pypdf reader
- **AND** the diagnostic SHALL name pypdf as the fallback backend when it produces the text

#### Scenario: pypdf pages are numbered by position

- **GIVEN** the pypdf tier returns one document per page, in page order
- **WHEN** the adapter emits the recovered documents
- **THEN** `page` SHALL be the 1-based position of the page in the file
- **AND** `page_label` SHALL be that number as a string, not the PDF's own page label

### Requirement: A rescue corrects the routing evidence only when it recovers text

A successful retry SHALL correct the routing evidence it emits: the scalar `pages_needing_ocr` SHALL be set to zero, because the pages were flagged only by the failed extraction, and the pre-fallback flagged count SHALL be preserved under an additive diagnostic key. A retry chain that yields no text from either tier SHALL leave the original pdf-inspector result unchanged so the OCR routing gate still sees the flagged evidence.

#### Scenario: Recovered text corrects the routing evidence

- **GIVEN** a fallback tier recovers text from a file pdf-inspector flagged page-by-page
- **WHEN** the OCR routing seam reads the emitted metadata
- **THEN** `pages_needing_ocr` SHALL be zero
- **AND** the original flagged count SHALL be preserved under a separate diagnostic key

#### Scenario: Failed retry keeps the original evidence

- **GIVEN** both fallback tiers yield no text
- **WHEN** the adapter emits its document
- **THEN** the emitted result SHALL be the unchanged pdf-inspector result with its original flagged count
- **AND** the OCR routing decision SHALL be unchanged from a run without the guard

### Requirement: Rescue diagnostics name the tier that produced the text

Diagnostics SHALL be additive, and `extraction_fallback_backend` SHALL name the tier that produced the text (`liteparse` or `pypdf`); diagnostics SHALL NOT claim the OCR worker or any other backend produced it.

#### Scenario: Contradiction triggers the retry

- **GIVEN** pdf-inspector returns `pdf_type=text_based`, non-zero `page_count`, and empty Markdown
- **WHEN** the adapter emits its documents
- **THEN** the document texts SHALL be the liteparse per-page extraction, one document per recovered page
- **AND** each document SHALL carry an additive diagnostic naming liteparse as the fallback backend

### Requirement: pdf-inspector OCR evidence SHALL cover every page of text_based PDFs longer than the detection sample

pdf-inspector detects OCR need from a bounded page sample (8 pages). When `process_pdf` classifies a PDF as `text_based` and its page count is greater than 8, the adapter SHALL compute `pages_needing_ocr` from a scan of every page (`extract_pages_markdown`), so image-only pages outside the sample reach the OCR routing gate. The adapter SHALL NOT change `pdf_type` or `pdf_confidence`, and SHALL NOT add a metadata key.

#### Scenario: Image-only page outside the sample is counted

- **GIVEN** a 20-page PDF that pdf-inspector classifies as `text_based` with no sampled page needing OCR
- **AND** a full page scan finds 3 pages needing OCR
- **WHEN** the adapter emits its documents
- **THEN** `pages_needing_ocr` SHALL be 3

#### Scenario: Short or already complete results get no extra scan

- **GIVEN** a `text_based` PDF with 8 pages or fewer, or a PDF classified `scanned`, `image_based` or `mixed`
- **WHEN** the adapter emits its documents
- **THEN** no page scan SHALL run beyond the one per-page extraction that gives the page text
- **AND** `pages_needing_ocr` SHALL be the count from `process_pdf`, even when the per-page extraction flags a different number

#### Scenario: Full scan failure keeps the sampled evidence

- **GIVEN** a `text_based` PDF longer than 8 pages whose full page scan raises
- **WHEN** the adapter emits its documents
- **THEN** `pages_needing_ocr` SHALL be the sampled count
- **AND** the read SHALL succeed with a logged warning

#### Scenario: Silent-empty rescue records the full-scan count

- **GIVEN** a `text_based` PDF longer than 8 pages with empty Markdown whose fallback tier recovers text
- **WHEN** the adapter emits its documents
- **THEN** `pages_needing_ocr` SHALL be zero
- **AND** `pages_needing_ocr_before_fallback` SHALL be the full-scan count

### Requirement: LiteParse adapter SHALL emit multi-column pages in reading order

The LiteParse adapter SHALL classify each page's layout from its own text items before joining them into text. A page classified `multi_column` SHALL be joined column by column: every item of the first column in vertical order, then every item of the next column.

#### Scenario: Two-column body page is emitted column by column

- **GIVEN** a page whose text items form two columns separated by a gutter
- **WHEN** the adapter emits its Document
- **THEN** the text SHALL contain every item of the left column, in vertical order, before any item of the right column

### Requirement: Pages not classified multi_column keep the library order

A page not classified `multi_column` SHALL keep the order the library returned, so single-column pages, tables and layouts the classifier does not recognise are unchanged, and SHALL keep the `column` label the adapter emits today.

#### Scenario: Single-column page keeps the library order

- **GIVEN** a page whose items leave no qualifying gutter
- **WHEN** the adapter emits its Document
- **THEN** the text SHALL be the items joined in the order LiteParse returned them

### Requirement: Column classification requires a qualifying gutter in the page geometry

Column classification SHALL require a vertical gutter: a band of the page's horizontal extent that the page's own non-full-width items leave essentially uncovered, whose centre lies in the middle third of that extent, with text on both sides of comparable quantity, each side spanning most of the page's vertical text extent. A page that fails any of those conditions SHALL keep the library order and SHALL NOT be labelled `multi_column`.

#### Scenario: A table is not reordered

- **GIVEN** a page whose items are laid out in rows across the page with no qualifying gutter
- **WHEN** the adapter emits its Document
- **THEN** the item order SHALL be unchanged
- **AND** the page SHALL NOT be labelled `multi_column`

### Requirement: Column classification reads only the page geometry

Classification SHALL depend only on the geometry of the page's own text items and SHALL NOT read the document, the file name or any setting.

#### Scenario: Same geometry, same classification

- **GIVEN** two pages whose text items have the same geometry, from different documents with different file names
- **WHEN** each page is classified
- **THEN** both pages SHALL receive the same classification

### Requirement: Reordering changes only whitespace

Reordering SHALL NOT add, drop or alter any item. Together with the line join below, the only change to a page's characters SHALL be whitespace.

#### Scenario: Reordering preserves content

- **GIVEN** any page the adapter reorders
- **WHEN** the adapter emits its Document
- **THEN** the multiset of item texts in the output SHALL equal the multiset LiteParse returned

### Requirement: LiteParse adapter SHALL join the items of one visual line

The adapter SHALL join consecutive items that sit on one visual line, left to right, into one line of text. Two items share a line when their vertical ranges overlap by at least half the shorter item's height and the second starts at or to the right of the first. Items on one line SHALL be joined by a single space, or by no space when the horizontal gap is under one tenth of the shorter height (a kerning split).

#### Scenario: Words drawn separately form one line

- **GIVEN** a title whose words are separate items at the same height
- **WHEN** the adapter emits its Document
- **THEN** the title SHALL be one line, its words separated by single spaces

#### Scenario: A kerning split rejoins without a space

- **GIVEN** two pieces of one word with no gap between them
- **WHEN** the adapter emits its Document
- **THEN** they SHALL be joined with no space

### Requirement: A wide gap or any other item boundary breaks the line

A gap wider than the taller item's height SHALL start a new line, so a sidebar and the body beside it are never joined. Every other item boundary SHALL be a line break. The join SHALL NOT change item order or item text.

#### Scenario: A column gap breaks the line

- **GIVEN** two items at the same height separated by more than one text height
- **WHEN** the adapter emits its Document
- **THEN** they SHALL be on separate lines

### Requirement: Unit-scoped metadata keys SHALL enter the index identity only under their unit

A metadata key that only one routing unit can emit SHALL contribute to `embedding_text.excluded_keys` in the source index identity only when that unit is active.

This mirrors the routing unit's own treatment, which enters the identity only when it is not `document`.

#### Scenario: A document-unit install keeps the identity it had

- **GIVEN** the `document` routing unit and a source indexed before page routing existed
- **WHEN** its index identity is computed
- **THEN** the identity SHALL equal the identity computed before the page-source counts joined the exclusion set
- **AND** the source SHALL NOT be reprocessed

#### Scenario: A page-unit install includes them

- **GIVEN** the `page` routing unit
- **WHEN** its index identity is computed
- **THEN** the page-source counts SHALL contribute to `embedding_text.excluded_keys`

### Requirement: The page-source counts are keys only the page unit emits

The page-source counts SHALL be treated as keys that only one routing unit can emit: the `document` unit never puts them on a Document, so their presence in the centrally owned exclusion set cannot change a `document`-unit install's embedded text, and including them in its identity would reprocess every existing corpus for a key it can never emit.

#### Scenario: Subtracted keys are never emitted on the document path

- **GIVEN** the `document` routing unit
- **WHEN** a PDF is ingested
- **THEN** the emitted metadata SHALL carry none of the page-source counts

### Requirement: The page-source counts stay in the central exclusion set

The page-source counts SHALL remain in the one centrally owned exclusion set; a second list held by the PDF reader would exclude them from embedding text while moving no identity at all, on any unit.

#### Scenario: The PDF reader holds no second exclusion list

- **WHEN** embedding text is built on either routing unit
- **THEN** the page-source counts SHALL be excluded through the centrally owned exclusion set
- **AND** the PDF reader SHALL hold no second list of them

### Requirement: Page-level OCR routing SHALL OCR only pages that need it

When `OCR_ROUTING_UNIT=page` and OCR is enabled, the pdf-inspector path SHALL decide OCR need per page from a scan of every page. Pages that do not need OCR SHALL keep native pdf-inspector Markdown. Pages that need OCR SHALL be processed by the local OCR tier. The default routing unit SHALL remain `document`.

#### Scenario: Only flagged pages are OCRed

- **GIVEN** the `page` routing unit and a 20-page PDF with 3 pages needing OCR
- **WHEN** the PDF is ingested
- **THEN** the 17 other pages SHALL keep native Markdown
- **AND** only the 3 flagged pages SHALL be processed by the local OCR tier

#### Scenario: Missing local OCR runtime degrades to native text

- **GIVEN** the `page` routing unit and no usable PDFium library or ONNX Runtime
- **WHEN** a PDF with flagged pages is ingested
- **THEN** flagged pages SHALL keep native text and be counted as unresolved
- **AND** a warning SHALL name the missing runtime once per operation

#### Scenario: Document unit is unchanged

- **GIVEN** no routing unit is configured
- **WHEN** a PDF is ingested
- **THEN** routing SHALL follow the whole-PDF behaviour of the `document` unit

### Requirement: Only unreadable local OCR pages escalate to the OCR routes

A page SHALL escalate to the OCR routes only when the local tier returns no text or only whitespace, reports no confidence or a confidence below the configured minimum, or recommends hosted OCR. Escalated pages SHALL go in one page-listed request to the primary OCR route, or to the fallback route when the primary is unavailable before dispatch. The OCR routes SHALL receive only escalated pages.

#### Scenario: A page the local tier cannot read escalates

- **GIVEN** the `page` routing unit and a flagged page the local tier returns no text for
- **AND** the worker returns usable, non-empty Markdown for that page
- **WHEN** the PDF is ingested
- **THEN** that page SHALL be sent to the worker
- **AND** the metadata SHALL count it as a worker page

#### Scenario: Unreadable local OCR pages escalate alone

- **GIVEN** the local OCR tier returns no text for 1 of 3 flagged pages
- **AND** an OCR route is available
- **AND** the worker returns usable, non-empty Markdown for the escalated page
- **WHEN** the PDF is ingested
- **THEN** exactly that page SHALL be sent to the worker
- **AND** the metadata SHALL count 1 worker page and 2 local-OCR pages

#### Scenario: Missing worker keeps local OCR text

- **GIVEN** a page escalates and both OCR routes are unavailable
- **WHEN** the PDF is ingested
- **THEN** the page SHALL keep its local OCR text, or native text when local OCR produced none
- **AND** the page SHALL be counted as unresolved without failing the file

### Requirement: A page-routed document counts the source of every page

The `page` routing unit SHALL emit one document for each page that has text, in page order, each carrying its `page` and `page_label`. Every emitted document SHALL carry the same scalar counts of native, local-OCR, worker and unresolved pages, which SHALL sum to the page count.

#### Scenario: Page-source counts sum to the page count

- **GIVEN** the `page` routing unit and any ingested PDF
- **WHEN** the adapter emits its documents
- **THEN** the native, local-OCR, worker and unresolved page counts SHALL sum to `page_count` on every document

#### Scenario: OCR pages keep their page numbers

- **GIVEN** the `page` routing unit and a 5-page PDF whose page 3 is read by the local tier and page 4 by the worker
- **WHEN** the adapter emits its documents
- **THEN** the document for page 3 SHALL carry `page` 3 and the local OCR text
- **AND** the document for page 4 SHALL carry `page` 4 and the worker text

#### Scenario: The document unit emits no page-source counts

- **GIVEN** no routing unit is configured
- **WHEN** a PDF is ingested
- **THEN** the emitted metadata SHALL NOT carry the native, local-OCR, worker or unresolved page counts

### Requirement: The scalar OCR diagnostics keep their document-unit meaning

The four existing OCR diagnostics SHALL remain scalars and SHALL keep their document-unit meaning. `ocr_required` SHALL be true when at least one page was flagged. `ocr_used` SHALL be true when OCR produced the text of at least one page, by either tier. `pages_needing_ocr` SHALL remain the count of flagged pages.

#### Scenario: Page routing keeps the scalar OCR diagnostics

- **GIVEN** the `page` routing unit and a PDF with at least one flagged page
- **WHEN** OCR produces the text of at least one page
- **THEN** `ocr_required` and `ocr_used` SHALL be true
- **AND** `pages_needing_ocr` SHALL be the count of flagged pages

### Requirement: ocr_backend names a single backend or mixed

`ocr_backend` SHALL name the one backend that produced all of the document's text, and SHALL be `mixed` when more than one produced text, so that it never names a backend that produced only part of a document.

#### Scenario: A document read by two backends reports mixed

- **GIVEN** the `page` routing unit and a PDF whose text comes partly from native extraction and partly from OCR
- **WHEN** the adapter emits its document
- **THEN** `ocr_backend` SHALL be `mixed`
- **AND** it SHALL NOT name either contributing backend alone

### Requirement: Local OCR tier SHALL escalate pages below a default confidence of 0.9

When `OCR_ROUTING_UNIT=page` and the operator has not set `OCR_LOCAL_MIN_CONFIDENCE`, a page the local OCR tier reads SHALL escalate to the worker when its reported confidence is below 0.9. The tier SHALL keep a page whose confidence is 0.9 or higher, unless the page is empty, has no reported confidence, or carries the engine's hosted recommendation. A value the operator sets SHALL replace the default without change to the rule.

#### Scenario: Page below the default cut escalates

- **GIVEN** `page` routing unit and no operator value for `OCR_LOCAL_MIN_CONFIDENCE`
- **WHEN** the local tier reads a page with text and confidence 0.85
- **THEN** the page SHALL escalate to the worker

#### Scenario: Page at the default cut stays local

- **GIVEN** `page` routing unit and no operator value for `OCR_LOCAL_MIN_CONFIDENCE`
- **WHEN** the local tier reads a page with text, confidence 0.9 and no hosted recommendation
- **THEN** the page SHALL keep its local text

#### Scenario: Operator value replaces the default

- **GIVEN** `OCR_LOCAL_MIN_CONFIDENCE=0.7`
- **WHEN** the local tier reads a page with text and confidence 0.75
- **THEN** the page SHALL keep its local text

### Requirement: Changing the local cut re-indexes page-unit sources only

The page-unit index identity SHALL change when the effective cut changes, so that sources read under a different cut are re-indexed. The default `document` routing unit has no local tier, and its index identity SHALL NOT change.

#### Scenario: Page unit re-indexes when the default changes

- **GIVEN** a source indexed under `page` routing with the previous default cut of 0.8
- **WHEN** the source is ingested again under the default cut of 0.9
- **THEN** the source SHALL be re-indexed

#### Scenario: Document unit keeps its index identity

- **GIVEN** the default `document` routing unit
- **WHEN** the default cut changes from 0.8 to 0.9
- **THEN** the index identity of every source SHALL stay the same

### Requirement: Reader installation SHALL be reported per reader

The host SHALL probe each registered concrete reader with its registry dependency probe once per Engine, on first use. It SHALL report each reader as installed, or as not installed with a reason that names the missing package.

#### Scenario: A registered reader is not installed

- **WHEN** the `pypdfium2` package is not importable
- **THEN** the host SHALL report `pypdfium2` as not installed
- **AND** the reason SHALL name the package `pypdfium2`

#### Scenario: Probing happens once per Engine

- **WHEN** a client lists the operation catalogue twice and then validates a graph on the same Engine
- **THEN** the host SHALL probe each registered reader once only

### Requirement: pdf_inspector emits one document per page

The `pdf_inspector` reader SHALL emit one document for each page that has non-whitespace text, in page order. Pages without text SHALL emit no document. The declared text format SHALL stay `markdown`.

#### Scenario: Three-page PDF gives three page documents

- **GIVEN** a text-based PDF with 3 pages that each have text
- **WHEN** the PDF is parsed by `pdf_inspector`
- **THEN** the reader SHALL emit 3 documents in page order
- **AND** each document text SHALL be the Markdown of its own page only

#### Scenario: A page without text emits no document

- **GIVEN** a 3-page PDF whose second page has no text
- **WHEN** the PDF is parsed by `pdf_inspector`
- **THEN** the reader SHALL emit 2 documents, for pages 1 and 3

#### Scenario: No page has text

- **GIVEN** a PDF on which no page has text and no fallback tier recovers text
- **WHEN** the PDF is parsed by `pdf_inspector`
- **THEN** the reader SHALL emit one document with empty text and no `page` or `page_label`
- **AND** that document SHALL carry the classification so OCR routing can read it

### Requirement: Heading context carries across the pages of one source

When one source yields several page documents, the chunker SHALL start each page with the heading path left open at the end of the previous page, in page order. A heading on the new page SHALL close open headings of the same or a deeper level. The stack SHALL NOT cross into another source or across a missing page.

#### Scenario: Section continues onto the next page

- **WHEN** page 3 ends inside section `Methods > Data` and page 4 starts with body text
- **THEN** the first chunk of page 4 has the same header path that whole-document chunking gives at that position
- **AND** on the model-token path that path is `/Methods/Data/`, and on the legacy Markdown path it is `/Methods/`, because LlamaIndex lists only the parent headings of a section there

#### Scenario: Matches whole-document chunking

- **WHEN** a PDF's page texts joined in order equal its whole-document text
- **THEN** every chunk's header path equals the path whole-document chunking gives at that position

### Requirement: pdf_inspector page numbers are physical and 1-based

Each page document SHALL carry `page`, the physical page number counted from 1, as an integer, and `page_label`, the same number as a string. pdf-inspector numbers pages from 0 in its per-page result, so the reader SHALL add 1.

#### Scenario: The first page is page 1

- **GIVEN** pdf-inspector reports a per-page result whose page index is 0
- **WHEN** the reader emits the document for that page
- **THEN** `page` SHALL be the integer 1
- **AND** `page_label` SHALL be the string `"1"`

#### Scenario: Labels match the other page readers

- **GIVEN** the same 2-page PDF parsed by `pdf_inspector` and by `pypdfium2`
- **WHEN** both readers emit their page documents
- **THEN** both SHALL give `page` values 1 and 2 and `page_label` values `"1"` and `"2"`

#### Scenario: A chunk keeps its page

- **GIVEN** a multi-page PDF ingested with `pdf_inspector`
- **WHEN** a chunk from page 2 is retrieved
- **THEN** the result SHALL carry `page_label` `"2"`

### Requirement: Every pdf_inspector page document carries the whole-PDF evidence

Each page document SHALL carry the same whole-PDF metadata: `pdf_reader`, `pdf_type`, `pdf_confidence`, `page_count`, `pages_needing_ocr`, `file_path` and `file_name`, plus any fallback diagnostics. These keys SHALL keep their present meaning and SHALL stay excluded from embedding text.

#### Scenario: Page documents agree on the evidence

- **GIVEN** a 12-page text-based PDF
- **WHEN** the PDF is parsed by `pdf_inspector`
- **THEN** every page document SHALL carry `page_count` 12
- **AND** every page document SHALL carry the same `pdf_type`, `pdf_confidence` and `pages_needing_ocr`

### Requirement: pdf_inspector falls back to the whole-document Markdown

When the per-page extraction raises, or gives no page text while the whole-document Markdown has text, the reader SHALL emit the whole-document Markdown as one document without `page` or `page_label`, and SHALL log a warning. The read SHALL NOT fail for this reason.

#### Scenario: Per-page extraction raises

- **GIVEN** a PDF whose per-page extraction raises and whose whole-document Markdown is not empty
- **WHEN** the PDF is parsed by `pdf_inspector`
- **THEN** the reader SHALL emit one document with the whole-document Markdown
- **AND** that document SHALL NOT carry `page` or `page_label`
- **AND** a warning SHALL name the file

### Requirement: Readers declare an output revision

Each registered PDF reader SHALL declare an integer output revision in its registry metadata. The revision SHALL increase when a change to the reader changes the documents it emits for the same file. The descriptor SHALL report it.

#### Scenario: Declared revisions

- **WHEN** the PDF reader registry is inspected
- **THEN** `pdf_inspector` SHALL declare output revision 2
- **AND** `liteparse`, `pypdf` and `pypdfium2` SHALL declare output revision 1

### Requirement: The document unit stamps OCR diagnostics on every page document

Under the `document` routing unit, the OCR routing seam SHALL read the evidence from the page documents and SHALL stamp `ocr_required`, `ocr_used`, `ocr_backend` and any maths count on every page document it returns. The fast and degraded paths SHALL keep the page documents and their page numbers.

#### Scenario: Fast path keeps the pages

- **GIVEN** the `document` unit and a clean 3-page text-based PDF
- **WHEN** the PDF is ingested
- **THEN** 3 page documents SHALL be returned with `page` 1, 2 and 3
- **AND** each SHALL carry `ocr_required` false and `ocr_backend` `pdf_inspector`

#### Scenario: Degraded path keeps the pages

- **GIVEN** the `document` unit, a PDF the gate routes to OCR, and no available OCR route
- **WHEN** the PDF is ingested
- **THEN** the native page documents SHALL be returned with their page numbers
- **AND** each SHALL carry `ocr_required` true and `ocr_used` false

### Requirement: A worker-read document carries no page provenance

Under the `document` routing unit, a document built from the worker's whole-PDF Markdown SHALL NOT carry `page` or `page_label`, because the response does not attribute text to pages. It SHALL keep `page_count` and the other whole-PDF evidence.

#### Scenario: Worker path emits one document without a page

- **GIVEN** the `document` unit and a scanned PDF that an available OCR route parses
- **WHEN** the PDF is ingested
- **THEN** the seam SHALL return one document with the worker Markdown
- **AND** that document SHALL NOT carry `page` or `page_label`
