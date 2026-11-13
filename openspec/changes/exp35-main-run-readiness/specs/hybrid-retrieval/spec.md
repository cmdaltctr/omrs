## MODIFIED Requirements

### Requirement: Native FTS lifecycle is specified and durable

The native sparse implementation on LanceDB SHALL define its full-text-search index lifecycle explicitly: additive creation on the stored `text` column and refresh at write time, never at query time; delete and stale-node handling; freshness diagnostics distinct from indexed/unindexed coverage; and failure diagnostics that route to BM25 fallback. When the resolved sparse backend is `native`, each ingest run SHALL end with a prepare step: it SHALL create the index when it is absent, and refresh it when rows are unindexed. The step SHALL run also when the ingest run wrote no new rows. A failure of the step SHALL be logged as a warning and SHALL NOT fail the ingest. A store without native sparse support SHALL treat the step as a no-op.

#### Scenario: FTS index is created additively

- **WHEN** an ingest run finishes on a collection without an FTS index, and the resolved sparse backend is `native`
- **THEN** the prepare step SHALL create the index additively, and no query SHALL create it
- **AND** the collection SHALL remain queryable throughout

#### Scenario: Ingest refreshes a stale index

- **WHEN** an ingest run finishes on a collection whose FTS index has unindexed rows, and the resolved sparse backend is `native`
- **THEN** the prepare step SHALL refresh the index, and the index SHALL then report zero unindexed rows

#### Scenario: BM25 backend builds no index

- **WHEN** an ingest run finishes and the resolved sparse backend is `bm25`
- **THEN** the ingest SHALL NOT create a full-text index

#### Scenario: Store without native sparse support

- **WHEN** an ingest run finishes on a Chroma collection
- **THEN** the prepare step SHALL do nothing and SHALL NOT raise

#### Scenario: Partial FTS coverage is distinguishable

- **WHEN** a collection contains both indexed and unindexed rows
- **THEN** diagnostics SHALL distinguish indexed from unindexed coverage
- **AND** unindexed rows SHALL remain eligible in dense rankings

### Requirement: Native queries never serve a stale FTS index

After a write, replacement, or deletion, the index SHALL be treated as stale until the next ingest prepare step completes. A native query SHALL NOT return stale index results as successful: it SHALL serve results that cover rows written after the last refresh and exclude deleted rows (the engine scans unindexed rows and honours delete tombstones at query time), or warn and fall back to BM25. A native query SHALL NOT refresh the index. The process-local store generation counter SHALL NOT be used as durable FTS-index maintenance; it SHALL remain a cache-invalidation mechanism for the in-memory BM25 index.

#### Scenario: Mutations make freshness explicit

- **WHEN** chunks are written, a source is replaced, or rows are deleted after an FTS index exists
- **THEN** the FTS index SHALL be considered stale until the next ingest prepare step completes
- **AND** a native query SHALL either return results that cover the new rows and exclude stale or deleted rows without a write, or warn and fall back to BM25
- **AND** diagnostics SHALL report the resulting fresh, stale, or fallback state

### Requirement: Existing collections are usable without re-ingestion
The system SHALL accept existing collections without forcing a re-ingestion. Every chunk SHALL participate in the dense ranking. On an FTS backend with an index, a row written after the last index refresh SHALL still participate in the sparse ranking, because the engine scans unindexed rows at query time, and a deleted row SHALL NOT appear. On a sparse-vector backend, a chunk without a sparse vector SHALL be excluded from the sparse ranking only. A collection with no FTS index SHALL get BM25 for the sparse ranking, with the fallback warning. RRF SHALL handle the missing-rank case naturally.

#### Scenario: Mixed coverage collection
- **GIVEN** a collection where some chunks have sparse coverage and others do not
- **WHEN** hybrid retrieval runs
- **THEN** all chunks SHALL participate in dense ranking
- **THEN** on an FTS backend, unindexed rows that match the query SHALL participate in the sparse ranking, and deleted rows SHALL NOT
- **THEN** on a sparse-vector backend, only chunks with a sparse vector SHALL participate in sparse ranking
- **THEN** the system SHALL NOT raise on chunks lacking sparse coverage

## ADDED Requirements

### Requirement: A native sparse query never writes to the store

A native sparse query SHALL only read the store. It SHALL NOT create, refresh or compact a full-text index, and SHALL NOT commit a new table version. When the collection has no FTS index, the query SHALL fail safely. The hybrid pipeline SHALL then warn, fall back to BM25 for that query, and name the remedy: run an ingest of the collection with the `native` backend.

#### Scenario: Query on a stale index

- **WHEN** a native query runs on a collection whose FTS index has unindexed rows
- **THEN** the table version and the FTS index row counts SHALL be the same after the query as before it
- **AND** the results SHALL include matching unindexed rows

#### Scenario: Query without an index

- **WHEN** a native query runs on a collection that has no FTS index
- **THEN** the collection SHALL still have no FTS index after the query
- **AND** the hybrid pipeline SHALL warn, fall back to BM25 for that query, and name the ingest remedy

#### Scenario: Concurrent searchers

- **WHEN** two processes run native queries on one collection at the same time
- **THEN** neither process SHALL write to the store, and the table version SHALL be unchanged
