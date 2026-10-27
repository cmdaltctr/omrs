# lancedb-vector-store Specification

## Purpose
Defines the LanceDB implementation of the VectorStore contract: the
vector space locks on first write, embedding identity is enforced
through table config, ChromaDB-style where clauses are translated
safely, the metadata struct evolves on later writes, and reads use
bounded scanner pages. These are the guarantees that make LanceDB a
qualified default backend.

**Schema metadata.** (The
originally named mechanisms — table `update_config` and a table-level
`replace_schema_metadata` — do not exist in the lancedb Python SDK as of
0.37.1; schema metadata is the verified durable key-value bag, recorded in
ADR-046.)

**Filter assembly.** (A full per-leaf
expression tree is not possible: `lancedb.expr` (verified on 0.37.1 and
0.40.0) has no struct field access, and user metadata lives inside an
Arrow `metadata` struct, so filters must reference `metadata.<field>`
paths; recorded in ADR-046. The string assembly this design necessarily
performs is the sanctioned exception to parameterised filtering recorded
in ADR-058.)

**Filtering on LanceDB.** lancedb 0.37.x and 0.40.x expose no bind-parameter filter API, and their
expression objects cannot address the struct sub-fields where user
metadata lives (verified live on 0.37.1 and 0.40.0; ADR-046, ADR-098).

## Requirements

### Requirement: LanceDB SHALL implement the VectorStore contract

The system SHALL provide `core/vectordb/lancedb/store.py` implementing the
`VectorStore` ABC (`core/vectordb/base.py`). A single `lancedb.connect(uri)`
connection SHALL back the store, and each RAG collection SHALL map to one
LanceDB table.

#### Scenario: Collection maps to a table

- **WHEN** a collection named `X` is created, listed, or deleted
- **THEN** the store MUST create, enumerate, or drop the LanceDB table `X`
  through the shared connection

#### Scenario: Contract parity with the ABC

- **WHEN** the shared `VectorStore` contract tests run against the LanceDB
  store
- **THEN** every abstract method MUST pass the same assertions the ChromaDB
  store passes, except where a scenario in this spec states an explicit
  difference

### Requirement: The LanceDB code stays inside its own folder

The implementation SHALL be split across the modules of the
`core/vectordb/lancedb/` folder (`store.py`, `paged.py`, `filter.py` and
their siblings) so no file exceeds 500 lines (architecture invariant #11).
No module outside `core/vectordb/lancedb/` SHALL import `lancedb`.

#### Scenario: Single lancedb import site

- **WHEN** `src/omrs/` is searched for `import lancedb`
- **THEN** the only matches MUST be within `core/vectordb/lancedb/`

### Requirement: LanceDB SHALL lock the vector space on first write

The store SHALL fix a collection's vector dimension when the table schema is
created on first write, matching the ChromaDB dimension-lock behaviour.
`create_collection` SHALL record intent without forcing a schema before the
first write.

#### Scenario: Dimension fixed on first write

- **WHEN** the first documents are written to a new collection
- **THEN** the table schema MUST fix the vector column dimension
- **AND** a later write with a different embedding dimension MUST raise a
  clear error

#### Scenario: Create then write

- **WHEN** `create_collection(name)` is called before any write
- **THEN** the collection MUST be reported as existing
- **AND** the first write MUST succeed and fix the dimension

### Requirement: LanceDB SHALL enforce embedding identity through table config

The store SHALL persist the embedding-identity triple (`provider`, `model`,
`index_identity`) and profile tags in the table's durable Arrow schema
metadata, written read-merge-write through pylance's
`update_schema_metadata` seam (`core/vectordb/lancedb/meta.py`).

#### Scenario: Identity metadata survives reconnection

- **WHEN** identity and profile config are written, the connection is
  closed, and the table is reopened
- **THEN** the stored values MUST be readable unchanged

### Requirement: LanceDB stamps a legacy collection and rejects a mismatch

The store SHALL apply the same legacy-stamp-then-reject rule as
`identity.py`: a collection with no stored identity is stamped on first
write, and a stored identity that does not match the active configuration
is rejected before any write or query. When no embedding identity is
attached (the pre-cloud direct-call path), the store SHALL neither stamp
nor check.

#### Scenario: Legacy collection stamped on first write

- **WHEN** a collection has no stored embedding identity and an identity is
  attached
- **THEN** the first write MUST stamp the active identity into the table
  config
- **AND** existing config keys such as profile tags MUST be preserved
  (read-merge-write)

#### Scenario: Mismatched identity rejected

- **WHEN** a collection's stored identity does not match the active
  configuration
- **THEN** a write or query MUST raise a clear error
- **AND** matching vector dimensions MUST NOT be treated as proof of
  compatibility

### Requirement: LanceDB SHALL translate ChromaDB where clauses safely

The store SHALL translate the ChromaDB-style `where` dict into LanceDB
filters in `core/vectordb/lancedb/filter.py`, with every VALUE serialised
through the `lancedb.expr` type-safe literal builder (whose unparser
performs the engine's own quoting), every field name validated against a
conservative identifier grammar and backtick-quoted in the emitted SQL,
and the operator vocabulary a fixed internal set.

#### Scenario: String values carry no injection risk

- **WHEN** a filter value contains SQL metacharacters such as a single
  quote
- **THEN** the value MUST be treated as a literal through the expression
  builder
- **AND** it MUST NOT alter the filter structure

### Requirement: The translator never interpolates client values into SQL

The translator SHALL NOT
interpolate client-supplied values into SQL strings.

#### Scenario: Client values reach SQL only through the literal builder

- **WHEN** the translator builds a filter from a client `where`
- **THEN** no client-supplied value SHALL be placed in the SQL string except through the `lancedb.expr` literal builder

### Requirement: The translator supports the ChromaDB operators

The ChromaDB operators `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`,
`$nin`, `$and`, and `$or` SHALL be supported.

#### Scenario: Equality filter

- **WHEN** a `where` of `{"file_path": "a/b.py"}` is supplied
- **THEN** the store MUST return only rows whose `file_path` equals
  `a/b.py`

#### Scenario: Boolean composition and set membership

- **WHEN** a `where` combines `$and`, `$or`, or `$in` operators
- **THEN** the store MUST return rows matching the composed condition

### Requirement: The translator rejects an unsupported operator

An unsupported operator SHALL raise a clear error naming it.

#### Scenario: Unknown operator rejected

- **WHEN** a `where` uses an operator outside the supported set
- **THEN** the translator MUST raise a clear error naming the operator

### Requirement: Filters keep ChromaDB missing-field semantics

Translation SHALL preserve ChromaDB
missing-field semantics: `$ne` and `$nin` match rows whose field is null
or absent, every other operator does not, and a field absent from the
table's schema SHALL fold to the same constants instead of reaching the
SQL planner. The translator SHALL validate each field name and
membership operand, including the membership-list limit, before it folds
a schema-absent field to a constant.

#### Scenario: Missing-field semantics match ChromaDB

- **WHEN** a `where` filters on a metadata field that some rows lack or
  that no row carries (absent from the schema)
- **THEN** `$ne` and `$nin` MUST match the rows lacking the field
- **AND** `$eq`, `$in`, and the comparison operators MUST NOT
- **AND** the filter MUST NOT fail with a planner error for a
  schema-absent field

#### Scenario: Absent fields do not bypass input validation

- **WHEN** a filter targets a schema-absent field with an invalid field
  name, invalid membership operand, or oversized membership list
- **THEN** the translator MUST reject the invalid input before folding
  the predicate to an absent-field constant

### Requirement: The translator checks each serialised literal against its value

The translator SHALL treat the engine's unparser as untrusted. Every
serialised literal SHALL match the closed form for its value type and
represent the original value. This applies to bool, int, finite and
infinite float, bytes, date, time-zone-aware datetime, and string values.
The translator SHALL decode or parse each fragment and compare it with
the original value using the corresponding type's exact or canonical
semantics.

#### Scenario: Unfaithful engine serialisation is refused

- **WHEN** the engine's literal builder emits a fragment that fails its
  closed-form check or represents a different value
- **THEN** the translator MUST refuse the filter with an error naming
  the affected value class
- **AND** this MUST apply to string, byte, boolean, integer, float,
  date, and datetime values
- **AND** no SQL MUST reach the engine for that filter

### Requirement: The translator accepts only a faithful fragment for an infinity

An infinite float SHALL be accepted only as the engine's typed
Float64 cast of the same infinity. A fragment that is not a faithful
serialisation of its value SHALL refuse the whole filter with an
actionable error before any SQL reaches the engine.

#### Scenario: Infinite float filters match the expected rows

- **GIVEN** a collection whose float metadata field holds `inf` in one
  row and `-inf` in another
- **WHEN** a `where` compares that field with `float("inf")` or
  `float("-inf")` by `$eq` or `$lt`
- **THEN** the store MUST return the rows that the comparison selects
- **AND** a fragment for an infinity that is a bare name, a different
  infinity, or a type other than Float64 MUST be refused

### Requirement: The translator caps the size of a client filter

Client filters are
untrusted input, so nesting depth, comparison-clause count,
membership-list length, and serialised length SHALL each be capped with
an error naming the crossed limit.

#### Scenario: Structural bounds are enforced

- **WHEN** a filter exceeds the nesting-depth, clause-count,
  membership-list, or serialised-length cap
- **THEN** the translator MUST refuse it with an error naming the
  crossed limit

### Requirement: The translator refuses values whose comparison is unstable

The translator SHALL refuse three value classes whose comparison
semantics differ between the engine versions or between the dense and
sparse filter paths: a `Decimal`, a float NaN, and a `datetime` without a
time zone. The refusal SHALL name the value class and the accepted
alternative (an `int` or a `float` for a Decimal; a datetime with a time
zone for a naive datetime).

#### Scenario: Naive datetime is refused

- **WHEN** a `where` value is a `datetime` without a time zone
- **THEN** the translator MUST refuse the filter with an error that names
  the naive datetime and asks for a datetime with a time zone
- **AND** no SQL MUST reach the engine for that filter

#### Scenario: Aware datetime keeps its rows

- **GIVEN** rows whose metadata holds an ISO date as text
- **WHEN** a `where` compares that field with a datetime that has a time
  zone
- **THEN** the store MUST compare the UTC instant of that datetime
- **AND** the matched rows MUST NOT depend on the host time zone

#### Scenario: Decimal is refused

- **WHEN** a `where` value, or an item of a `$in` or `$nin` list, is a
  `Decimal`
- **THEN** the translator MUST refuse the filter with an error that names
  the Decimal and asks for an int or a float

#### Scenario: NaN is refused

- **WHEN** a `where` value is a float NaN
- **THEN** the translator MUST refuse the filter with an error that names
  the NaN value

### Requirement: The refusal covers membership items and runs before field folding

The refusal SHALL apply to a scalar operand and to
each membership item, and it SHALL run before a schema-absent field folds
to a constant, so the outcome does not depend on the table's schema.

#### Scenario: Refused classes on a schema-absent field

- **WHEN** a refused value class targets a field that the table's schema
  does not hold
- **THEN** the translator MUST refuse the filter
- **AND** it MUST NOT fold the predicate to an absent-field constant

### Requirement: LanceDB SHALL evolve the metadata struct on later writes

LanceDB fixes the Arrow `metadata` struct on the first write, and pylance
has no nested `add_columns`, so the store SHALL grow the struct itself in
`core/vectordb/lancedb/meta.py` when a later write introduces metadata keys
the struct lacks: existing rows gain nulls for the new fields (ChromaDB's
key-absent state), the schema metadata bag (identity triple, profile
tags) SHALL survive the growth, and no incoming metadata key SHALL be
silently dropped.

#### Scenario: A later write introduces a new metadata field

- **WHEN** a collection already exists and a write introduces a metadata
  key absent from its struct
- **THEN** the store MUST extend the struct before writing
- **AND** the new key MUST be retrievable through filters and paged reads
- **AND** existing rows and the stored identity/profile metadata MUST be
  preserved

#### Scenario: Adapter-internal struct fields

- **WHEN** the LlamaIndex adapter writes into a table created by
  `upsert_precomputed` (whose struct lacks the adapter's internal keys)
- **THEN** the store MUST add the internal keys to the struct before the
  adapter write so the write succeeds

### Requirement: LanceDB reads SHALL use bounded scanner pages

The store SHALL implement `iter_metadatas`, `iter_documents`, and
`fetch_all` over LanceDB's scanner in `core/vectordb/lancedb/paged.py`, using
bounded pages for the iterators. The BM25 sparse retriever SHALL read
through `iter_documents` unchanged, and the process-local generation counter
SHALL advance on every write, row delete, and collection drop so the
retriever rebuilds its index.

#### Scenario: Paged iteration over a large collection

- **WHEN** `iter_documents` or `iter_metadatas` scans a collection larger
  than one page
- **THEN** it MUST yield every row using bounded pages
- **AND** it MUST NOT load the whole collection at once

#### Scenario: Hybrid retrieval through the existing BM25 path

- **WHEN** hybrid retrieval runs against a LanceDB-backed collection
- **THEN** the in-memory BM25 retriever MUST build its index from
  `iter_documents`
- **AND** a write or delete MUST advance the generation counter so the
  index is rebuilt

#### Scenario: Dropping a collection invalidates the BM25 cache

- **WHEN** a collection is dropped through the store (directly, without
  the ingestion writer's external bump)
- **THEN** the generation counter MUST advance so a cached BM25 index
  built over the collection is invalidated

### Requirement: LanceDB SHALL stay local-first with no PyTorch on the base path

The LanceDB dependency SHALL be added through
`llama-index-vector-stores-lancedb` and SHALL NOT introduce PyTorch onto the
base install or the default retrieval path (ONNX-only hard boundary). v1
SHALL target the embedded, local LanceDB connection only.

#### Scenario: No PyTorch on the base path

- **WHEN** the base install is resolved and the default retrieval path runs
- **THEN** `torch` MUST NOT be imported

#### Scenario: Embedded connection by default

- **WHEN** `VECTOR_STORE=lancedb` is selected without remote credentials
- **THEN** the store MUST connect to the local `LANCEDB_URI` directory

### Requirement: LanceDB SHALL pass production-lifecycle qualification before becoming default

The default flip SHALL be blocked until a TDR-014-admissible LanceDB campaign
passes real ingestion, reopen, retrieval, mutation, identity and recovery gates
at the final pre-flip commit and lock.

#### Scenario: Qualification succeeds

- **WHEN** the LanceDB campaign completes
- **THEN** it MUST prove parse/chunk/embed/write, restart/reopen, dense query, BM25 hybrid query, filters, unchanged re-ingest, replacement, deletion, identity, generations and interrupted-write recovery
- **AND** requested/effective backend, URI/index identity, score kind, embedding identity and raw operation rows MUST be retained

#### Scenario: Qualification is incomplete or fails

- **WHEN** any required lifecycle cell fails, is incomplete or is not evaluable
- **THEN** LanceDB MUST NOT become the executable default
- **AND** Stage 6 calibration MUST NOT treat it as the final baseline

### Requirement: Qualified LanceDB SHALL be the base-install vector-store default

After the qualification gate passes, the system SHALL resolve embedded LanceDB
when no explicit backend is supplied. The base path SHALL not import or require
ChromaDB.

#### Scenario: Unset selector in a clean base installation

- **GIVEN** qualification passed
- **AND** no recognised legacy Chroma data requires acknowledgement
- **AND** no backend is explicitly selected
- **WHEN** settings and composition complete
- **THEN** the effective store MUST be embedded LanceDB at `LANCEDB_URI`
- **AND** both Chroma distributions MUST be absent from the environment
- **AND** no Chroma module MUST be loaded

#### Scenario: Explicit LanceDB selection

- **GIVEN** `VECTOR_STORE=lancedb` is explicitly selected
- **WHEN** runtime setup completes
- **THEN** every ingestion, retrieval, profile and deletion operation MUST use the configured LanceDB store

### Requirement: Recognised legacy Chroma data SHALL require an explicit decision

Settings resolution SHALL retain whether the backend was explicitly supplied.
Recognised legacy Chroma data with no explicit choice SHALL stop startup before
ingestion or retrieval. The legacy directory SHALL remain untouched.

#### Scenario: Recognised legacy layout and no explicit backend

- **GIVEN** Chroma markers such as `chroma.sqlite3` or the documented segment layout exist
- **AND** backend selection came only from shipped defaults
- **WHEN** startup evaluates migration safety
- **THEN** startup MUST fail naming the directory
- **AND** the error MUST require explicit Chroma keep-and-pin or explicit LanceDB re-ingestion acknowledgement
- **AND** it MUST disclose that automatic migration is not performed

#### Scenario: Explicit LanceDB acknowledges re-ingestion

- **GIVEN** recognised legacy Chroma data exists
- **AND** the operator explicitly selects `VECTOR_STORE=lancedb`
- **WHEN** startup completes
- **THEN** LanceDB MAY start
- **AND** the legacy Chroma directory MUST remain unchanged

#### Scenario: Non-empty unrecognised directory

- **GIVEN** the configured legacy path is non-empty but lacks recognised Chroma markers
- **AND** the backend was not explicitly selected
- **WHEN** startup evaluates migration safety
- **THEN** startup MUST emit an actionable warning rather than classify it as confirmed Chroma data

#### Scenario: Fresh LanceDB installation

- **GIVEN** no recognised legacy Chroma data exists
- **WHEN** default LanceDB setup completes
- **THEN** no migration diagnostic MUST be emitted

### Requirement: The LanceDB filter adapter is the sole sanctioned exception to parameterised filtering

On lancedb 0.37.x and 0.40.x, a SQL filter string assembled by
`core/vectordb/lancedb/filter.py` with engine-owned quoting and
fail-closed verification is the sanctioned filter mechanism, for the
`search_documents` and `answer_documents` paths alike (ADR-058). When a lancedb release offers a
parameterised path that can address user metadata, the adapter MUST
migrate to it and this exception SHALL lapse.

#### Scenario: A future parameterised path supersedes the exception

- **WHEN** a lancedb release offers bind parameters or expression
  objects that can address user metadata sub-fields
- **THEN** the adapter MUST migrate to that path
- **AND** the exception recorded in ADR-058 SHALL lapse

### Requirement: The filter exception covers no other store or path

The LanceDB filter exception SHALL NOT extend to any other store or code path: any backend
that accepts structured filters or offers bound parameters MUST filter
through those mechanisms, and client values MUST NOT be assembled into
query text outside this adapter.

#### Scenario: Exception applies only to the LanceDB filter adapter

- **WHEN** any store other than the LanceDB adapter filters retrieved
  data by client-supplied values
- **THEN** it MUST use that store's structured or parameterised filter
  mechanism
- **AND** client values MUST NOT be assembled into query text

### Requirement: LanceDB writer processes SHALL exit cleanly after a write

The declared lancedb minimum SHALL be a release that shuts its runtime
down at interpreter exit (lancedb 0.40.0 or later). A process that
finishes a LanceDB write SHALL exit with status 0. Tests that write
from a child process SHALL let the child run normal interpreter shutdown
and SHALL fail when the child exits with any other status.

#### Scenario: The floor includes the runtime shutdown

- **WHEN** the project installs at its declared floors
- **THEN** the installed lancedb MUST be 0.40.0 or later

#### Scenario: A crash at shutdown fails the test

- **GIVEN** a writer child process that finishes its work and then
  crashes during interpreter shutdown
- **WHEN** a test runs it through the shared child helper
- **THEN** the test MUST fail
- **AND** the failure message MUST show the child's stdout, with the
  finished marker, and its stderr, with the faulthandler output

#### Scenario: The child runs its exit handlers

- **WHEN** a writer child registers an exit handler that prints a line
- **THEN** that line MUST appear in the child's stdout
