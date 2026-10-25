# Probes

Evidence for the design decisions. All probes ran on 2026-10-25 on macOS with `TZ=Europe/London` (BST, UTC+1, on the September dates). Each probe ran twice:

- **0.37.1**: the locked project environment (`uv run --no-sync python -I <probe>`): lancedb 0.37.1, pylance 10.0.0, pyarrow 25.0.1.
- **0.40.0**: a throwaway environment (`uv run --no-project --with "lancedb==0.40.0" --with "pylance==10.0.0" --with "pyarrow==25.0.1" python -I <probe>`).

A third run used pylance 13.0.0 and pyarrow 26.0.0 with lancedb 0.40.0 (P6).

The probe scripts are short and are not kept in the repository. Each section gives enough detail to write them again.

## P1. `lit(value).to_sql()` forms

Only the rows that differ between the versions, plus the rows the design depends on.

| Value | 0.37.1 | 0.40.0 |
|---|---|---|
| `float("inf")` | `inf` | `arrow_cast('inf', 'Float64')` |
| `float("-inf")` | `-inf` | `arrow_cast('-inf', 'Float64')` |
| `float("nan")` | `NaN` | `arrow_cast('NaN', 'Float64')` |
| `-0.0`, `1.0`, `3.14`, `1e16`, `1e300`, `5e-324` | plain decimal text | same as 0.37.1 |
| `Decimal("0")` | `0` | `arrow_cast('0', 'Decimal128(1, 0)')` |
| `Decimal("-0")` | `0` | `arrow_cast('0', 'Decimal128(1, 0)')` |
| `Decimal("0.05")` | `0.05` | `arrow_cast('0.05', 'Decimal128(3, 2)')` |
| `Decimal("0.050")` | `0.050` | `arrow_cast('0.050', 'Decimal128(4, 3)')` |
| `Decimal("100")` | `100` | `arrow_cast('100', 'Decimal128(3, 0)')` |
| `Decimal("1" * 38)` | 38 digits | `arrow_cast('<38 digits>', 'Decimal128(38, 0)')` |
| `Decimal("1" * 39)` | 39 digits | `arrow_cast('<39 digits>', 'Decimal128(39, 0)')` (Arrow allows 38 at most) |
| `Decimal("1E+3")`, `Decimal("1E-40")`, `Decimal("NaN")`, `Decimal("Infinity")` | `ValueError` | `ValueError` |
| naive `datetime(2026, 9, 2, 15, 30, 45)` | `CAST('2026-09-02 14:30:45' AS TIMESTAMP)` | `CAST('2026-09-02 15:30:45' AS TIMESTAMP)` |
| naive `datetime(2026, 1, 15, 12, 0)` (GMT, offset 0) | `CAST('2026-01-15 12:00:00' AS TIMESTAMP)` | same |
| aware `datetime(..., tzinfo=UTC)` or `+08:00` | UTC wall clock in a `TIMESTAMP` cast | same as 0.37.1 |
| `date`, `bytes`, `int`, `bool`, `str` | unchanged | unchanged |
| `"''"` (two apostrophes) | `''''` (decodes to one apostrophe) | `''''` (bug still present) |
| `"a\\'b"` | `'a\'b'` | `'a\'b'` (bug still present) |

`dir(lancedb.expr)` and the method list of `col(...)` are the same on both versions: `and_`, `cast`, `contains`, `eq`, `gt`, `gte`, `isin`, `lower`, `lt`, `lte`, `ne`, `or_`, `to_sql`, `upper`. There is no struct field access and no bind parameter API.

## P2. Rows that a filter matches

Table `t`: an `id` column and a `metadata` struct with `score: float64`, `n: int64` and `creation_date: string`. Rows:

| id | score | n | creation_date |
|---|---|---|---|
| a | 0.05 | 1 | 2026-09-01 |
| b | 3.14 | 100 | 2026-09-02 |
| c | inf | 0 | 2026-09-03 |
| d | -inf | -1 | 2026-09-04 |
| e | NaN | 5 | 2026-09-05 |

Each filter is `` `metadata`.`<field>` <op> <lit(value).to_sql()> ``.

| Filter | 0.37.1 | 0.40.0 |
|---|---|---|
| `score = inf` | error: `No field named inf` | `['c']` |
| `score = -inf` | error: `No field named inf` | `['d']` |
| `score < inf` | error: `No field named inf` | `['a', 'b', 'd']` |
| `score = NaN` | error: `No field named "NaN"` | `['e']` |
| `score = Decimal("3.14")` | `['b']` | error: `Cannot cast to Decimal128(30, 15). Overflowing on inf` |
| `n = Decimal("100")` | `['b']` | `['b']` |
| `creation_date = date(2026, 9, 2)` | `['b']` | `['b']` |
| `creation_date >= aware datetime(2026, 9, 3, tzinfo=UTC)` | `['c', 'd', 'e']` | `['c', 'd', 'e']` |
| `creation_date >= naive datetime(2026, 9, 3, 0, 30)` | `['c', 'd', 'e']` | `['d', 'e']` |

The last row shows the silent change: the same naive value matches different rows, with no error.

## P3. Decimal against a float column (no infinite values)

Rows: `tiny` (score `1e-20`), `a` (0.05), `b` (3.14), `c` (`0.1 + 0.2`, which is 0.30000000000000004). A second table adds `huge` (score `2.5e15`).

| Filter | 0.37.1 | 0.40.0 |
|---|---|---|
| `score > Decimal("0")` | `['a', 'b', 'c', 'tiny']` | `['a', 'b', 'c']` (drops `tiny`) |
| `score > 0.0` | `['a', 'b', 'c', 'tiny']` | `['a', 'b', 'c', 'tiny']` |
| `score = Decimal("0.3")` | `[]` | `['c']` (adds `c`) |
| `score = 0.3` | `[]` | `[]` |
| `score > Decimal("1")` with `huge` | `['b', 'huge']` | error: `2499999999999999.9... is too large` |

The Python evaluator in `core/retrieval/filters.py` compares exactly: `1e-20 > Decimal("0")` is `True` and `0.30000000000000004 == Decimal("0.3")` is `False`. It agrees with 0.37.1 and disagrees with 0.40.0.

## P4. Value types that OMRS can store

- The LlamaIndex adapter writes with `flat_metadata=True`. `llama_index.core.vector_stores.utils._validate_is_flat_dict` accepts only `str`, `int`, `float` and `None`, so a `datetime` or `Decimal` metadata value fails before the write.
- The precomputed upsert path infers `pa.string()` for any value that is not bool, int or float (`core/vectordb/lancedb/meta.py`, `infer_arrow_type`). `pa.array([datetime(...)], type=pa.string())` raises `ArrowTypeError: Expected bytes, got a 'datetime.datetime' object` on both versions.
- Result: an OMRS table has no `TIMESTAMP`, `DATE` or `DECIMAL` metadata field. Date-like metadata (`creation_date`, `last_modified_date`) is stored as ISO text. A date or datetime filter compares that text through a cast.

## P5. Runtime shutdown at exit

`atexit._ncallbacks()` after `import lancedb`, with pyarrow and numpy imported first: 2 on 0.37.1, 3 on 0.40.0. The extra callback is the runtime shutdown that lancedb PR #4175 registers in the `_lancedb` module init.

pylance has its own Tokio runtime (`python/src/executor.rs`). Neither `v10.0.0` nor `v13.0.0` of lance-format/lance has an `atexit` hook or a runtime shutdown in `python/src/lib.rs` or `executor.rs`. lance issue #4152 (shutdown crash in the pylance runtime) is open.

## P6. pylance 13.0.0 and pyarrow 26.0.0

P1 to P4 with lancedb 0.40.0, pylance 13.0.0 and pyarrow 26.0.0 gave output identical to the pylance 10.0.0 run. `LanceDataset.update_schema_metadata(values, replace=False)` and `LanceDataset.scanner` exist and work. This environment resolves `lance-namespace` 0.11.1 (the lock has 0.8.6).

## P7. Rollback

A table created, appended to and given schema metadata by lancedb 0.40.0 (data storage version 2.2) opened on lancedb 0.37.1 with the correct row count and schema metadata, and accepted one more append.

## Upstream facts

| Fact | Source |
|---|---|
| Runtime shutdown at interpreter exit, merged 2026-09-15 | https://github.com/lancedb/lancedb/pull/4175 |
| First release with it is v0.40.0 (2026-10-07) | `gh release list -R lancedb/lancedb`; TDR-040 checked the tags |
| Naive `lit(datetime)` read as UTC wall clock, merged 2026-08-17 (after 0.37.1, released 2026-08-10) | https://github.com/lancedb/lancedb/pull/3775 |
| Decimal exponent literals change again, merged 2026-10-22, not in 0.40.0 | https://github.com/lancedb/lancedb/pull/4449 |
| lancedb v0.40.0 builds on Rust `lance =13.0.0`; v0.37.1 on `=10.0.0` | `Cargo.toml` at each tag |
| lancedb v0.40.0 runs its own tests with `pylance==9.0.0` | `python/pyproject.toml` line 66 at tag v0.40.0 |
| lancedb 0.40.0 requires `pydantic>=2.7.4,<3`; no pylance requirement outside extras | PyPI `requires_dist` |
| Chroma accepts only `str`, `int`, `float` (and lists of them) as `where` values | `chromadb/api/types.py`, `validate_where`, tag 1.5.9 |
