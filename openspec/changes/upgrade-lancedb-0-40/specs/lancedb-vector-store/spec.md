## MODIFIED Requirements

### Requirement: LanceDB SHALL translate ChromaDB where clauses safely

The store SHALL translate the ChromaDB-style `where` dict into LanceDB
filters in `core/vectordb/lancedb/filter.py`, with every VALUE serialised
through the `lancedb.expr` type-safe literal builder (whose unparser
performs the engine's own quoting), every field name validated against a
conservative identifier grammar and backtick-quoted in the emitted SQL,
and the operator vocabulary a fixed internal set. It SHALL NOT
interpolate client-supplied values into SQL strings. (A full per-leaf
expression tree is not possible: `lancedb.expr` (verified on 0.37.1 and
0.40.0) has no struct field access, and user metadata lives inside an
Arrow `metadata` struct, so filters must reference `metadata.<field>`
paths; recorded in ADR-046. The string assembly this design necessarily
performs is the sanctioned exception to parameterised filtering recorded
in ADR-058.)
The ChromaDB operators `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`,
`$nin`, `$and`, and `$or` SHALL be supported. An unsupported operator
SHALL raise a clear error naming it. Translation SHALL preserve ChromaDB
missing-field semantics: `$ne` and `$nin` match rows whose field is null
or absent, every other operator does not, and a field absent from the
table's schema SHALL fold to the same constants instead of reaching the
SQL planner. The translator SHALL validate each field name and
membership operand, including the membership-list limit, before it folds
a schema-absent field to a constant.

The translator SHALL treat the engine's unparser as untrusted. Every
serialised literal SHALL match the closed form for its value type and
represent the original value. This applies to bool, int, finite and
infinite float, bytes, date, time-zone-aware datetime, and string values.
The translator SHALL decode or parse each fragment and compare it with
the original value using the corresponding type's exact or canonical
semantics. An infinite float SHALL be accepted only as the engine's typed
Float64 cast of the same infinity. A fragment that is not a faithful
serialisation of its value SHALL refuse the whole filter with an
actionable error before any SQL reaches the engine. Client filters are
untrusted input, so nesting depth, comparison-clause count,
membership-list length, and serialised length SHALL each be capped with
an error naming the crossed limit.

The translator SHALL refuse three value classes whose comparison
semantics differ between the engine versions or between the dense and
sparse filter paths: a `Decimal`, a float NaN, and a `datetime` without a
time zone. The refusal SHALL name the value class and the accepted
alternative (an `int` or a `float` for a Decimal; a datetime with a time
zone for a naive datetime). It SHALL apply to a scalar operand and to
each membership item, and it SHALL run before a schema-absent field folds
to a constant, so the outcome does not depend on the table's schema.

#### Scenario: Equality filter

- **WHEN** a `where` of `{"file_path": "a/b.py"}` is supplied
- **THEN** the store MUST return only rows whose `file_path` equals
  `a/b.py`

#### Scenario: Boolean composition and set membership

- **WHEN** a `where` combines `$and`, `$or`, or `$in` operators
- **THEN** the store MUST return rows matching the composed condition

#### Scenario: String values carry no injection risk

- **WHEN** a filter value contains SQL metacharacters such as a single
  quote
- **THEN** the value MUST be treated as a literal through the expression
  builder
- **AND** it MUST NOT alter the filter structure

#### Scenario: Unknown operator rejected

- **WHEN** a `where` uses an operator outside the supported set
- **THEN** the translator MUST raise a clear error naming the operator

#### Scenario: Missing-field semantics match ChromaDB

- **WHEN** a `where` filters on a metadata field that some rows lack or
  that no row carries (absent from the schema)
- **THEN** `$ne` and `$nin` MUST match the rows lacking the field
- **AND** `$eq`, `$in`, and the comparison operators MUST NOT
- **AND** the filter MUST NOT fail with a planner error for a
  schema-absent field

#### Scenario: Unfaithful engine serialisation is refused

- **WHEN** the engine's literal builder emits a fragment that fails its
  closed-form check or represents a different value
- **THEN** the translator MUST refuse the filter with an error naming
  the affected value class
- **AND** this MUST apply to string, byte, boolean, integer, float,
  date, and datetime values
- **AND** no SQL MUST reach the engine for that filter

#### Scenario: Absent fields do not bypass input validation

- **WHEN** a filter targets a schema-absent field with an invalid field
  name, invalid membership operand, or oversized membership list
- **THEN** the translator MUST reject the invalid input before folding
  the predicate to an absent-field constant

#### Scenario: Structural bounds are enforced

- **WHEN** a filter exceeds the nesting-depth, clause-count,
  membership-list, or serialised-length cap
- **THEN** the translator MUST refuse it with an error naming the
  crossed limit

#### Scenario: Infinite float filters match the expected rows

- **GIVEN** a collection whose float metadata field holds `inf` in one
  row and `-inf` in another
- **WHEN** a `where` compares that field with `float("inf")` or
  `float("-inf")` by `$eq` or `$lt`
- **THEN** the store MUST return the rows that the comparison selects
- **AND** a fragment for an infinity that is a bare name, a different
  infinity, or a type other than Float64 MUST be refused

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

#### Scenario: Refused classes on a schema-absent field

- **WHEN** a refused value class targets a field that the table's schema
  does not hold
- **THEN** the translator MUST refuse the filter
- **AND** it MUST NOT fold the predicate to an absent-field constant

### Requirement: The LanceDB filter adapter is the sole sanctioned exception to parameterised filtering

lancedb 0.37.x and 0.40.x expose no bind-parameter filter API, and their
expression objects cannot address the struct sub-fields where user
metadata lives (verified live on 0.37.1 and 0.40.0; ADR-046, ADR-098). On
that engine, a SQL filter string assembled by
`core/vectordb/lancedb/filter.py` with engine-owned quoting and
fail-closed verification is the sanctioned filter mechanism, for the
`search_documents` and `answer_documents` paths alike (ADR-058). The
exception SHALL NOT extend to any other store or code path: any backend
that accepts structured filters or offers bound parameters MUST filter
through those mechanisms, and client values MUST NOT be assembled into
query text outside this adapter. When a lancedb release offers a
parameterised path that can address user metadata, the adapter MUST
migrate to it and this exception SHALL lapse.

#### Scenario: Exception applies only to the LanceDB filter adapter

- **WHEN** any store other than the LanceDB adapter filters retrieved
  data by client-supplied values
- **THEN** it MUST use that store's structured or parameterised filter
  mechanism
- **AND** client values MUST NOT be assembled into query text

#### Scenario: A future parameterised path supersedes the exception

- **WHEN** a lancedb release offers bind parameters or expression
  objects that can address user metadata sub-fields
- **THEN** the adapter MUST migrate to that path
- **AND** the exception recorded in ADR-058 SHALL lapse

## ADDED Requirements

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
