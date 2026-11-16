## ADDED Requirements

### Requirement: A search can return ranked stored chunks with no context assembly

The search entry points SHALL accept one additive option, off by default, that skips only the assembly stage. With it on, each returned row SHALL be one stored chunk with its own chunk ID, text, score and page label, in the final rank order. Ranking, reranking, fusion and truncation SHALL run as with the option off. With it off, the search SHALL return the assembled rows exactly as before.

#### Scenario: Exactly top_k stored chunks

- **GIVEN** a collection where at least 100 stored chunks qualify under the search's other settings (for example a similarity threshold)
- **WHEN** a search runs with the option on, `top_k` 100 and `fetch_k` 100
- **THEN** it SHALL return exactly 100 rows, one per stored chunk, in rank order
- **AND** when fewer than 100 chunks qualify, it SHALL return only the qualifying chunks, because the option changes assembly only

#### Scenario: Fewer chunks than top_k

- **GIVEN** a collection with 40 stored chunks
- **WHEN** a search runs with the option on and `top_k` 100
- **THEN** it SHALL return every chunk the index returns, and no merged row

#### Scenario: Adjacent chunks stay separate

- **GIVEN** chunks 5 and 6 of one source are adjacent and overlap, and the ranking is chunk 5, a chunk of another source, then chunk 6
- **WHEN** a search runs with the option on
- **THEN** it SHALL return three rows in that order, each with its own chunk ID, text and page label
- **AND** no row SHALL carry `chunk_ids` or `page_labels`

#### Scenario: Default unchanged

- **WHEN** the same search runs without the option
- **THEN** assembly SHALL merge chunks 5 and 6 into one row as the assembly requirements define
- **AND** the public result SHALL equal the result before the option existed

#### Scenario: Expansion requested with the option on

- **WHEN** a search runs with the option on and an expansion window above 0
- **THEN** it SHALL refuse before the query with an error that names both settings
- **AND** no row SHALL be returned

### Requirement: The unassembled option reaches every engine path

The option SHALL reach the core search from `Engine.search`. The user-profile path SHALL pass it through or refuse it with a clear error, and SHALL never ignore it. No transport SHALL be required to expose it.

#### Scenario: User-profile collection

- **WHEN** `Engine.search` runs with the option on, on a collection bound to a user profile
- **THEN** it SHALL either return stored chunks as on a built-in profile, or refuse with an error that names the option

## MODIFIED Requirements

### Requirement: Retrieval has an explicit context-assembly stage

The retrieval pipeline SHALL run a named assembly stage between final ranking
and return. The stage SHALL be the single place where returned evidence is
reshaped, and it SHALL NOT re-rank, re-score, or drop evidence. When the caller
turns on the unassembled search option, the stage is skipped and the ranked
stored chunks are returned.

#### Scenario: Assembly runs after ranking

- **WHEN** a search completes ranking and truncation
- **THEN** assembly SHALL run on the final result set
- **AND** the relative order established by ranking SHALL be preserved unless a
  scenario below states otherwise

#### Scenario: Assembly never removes evidence

- **WHEN** assembly runs
- **THEN** every distinct chunk present before assembly SHALL still be
  represented afterwards, either as its own row or as part of a merged row
- **AND** no chunk's unique text SHALL be lost
