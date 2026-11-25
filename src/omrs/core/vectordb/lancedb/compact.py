"""Bounded fragment count for LanceDB tables written one source at a time.

Every LanceDB append adds one data fragment. Ingest writes one source per
call, so a table built file by file holds one fragment per file. The
source-scoped reads of each commit (the durability count and the stale-row
scan) visit every fragment, so the store step costs time in proportion to
the number of files already written. Experiment 35 on the test pod: about
2 s per file after 3,300 files.

Compaction merges the small fragments into larger ones. It rewrites the
data files only: the rows, their order, the schema metadata (embedding
identity, profile tags, dataset epoch) and any index stay the same, and
Lance remaps an existing index to the new fragments. Old versions are not
deleted, so a reader with an older table handle keeps working.

Each compaction also keeps a scalar (BTREE) index on the metadata fields
that the per-file reads filter on (:data:`SOURCE_INDEX_FIELDS`). Without it,
the change detection, the durability count and the stale-row scan of each
commit read every row: about 40 ms per file at 196,000 rows on the
Experiment 35 test pod. With it, each read is an index lookup plus a scan of
the rows written since the last compaction, because each compaction also
folds the new rows into the index. The index changes no row, vector or
result. A table without the index (an older store, or one rebuilt by a
metadata-struct change) gets it at its next compaction.
"""

from __future__ import annotations

import logging
from typing import Any

import pyarrow as pa

logger = logging.getLogger(__name__)

__all__ = [
    "FRAGMENT_COMPACTION_THRESHOLD",
    "SOURCE_INDEX_FIELDS",
    "compact_if_fragmented",
]

#: Compact when a table holds this many fragments. Measured on a Mac with
#: 3-row writes: one filtered count and one filtered scan cost about 0.06 ms
#: per fragment, so the store step stays near its small-table cost.
FRAGMENT_COMPACTION_THRESHOLD = 64

#: A fragment with this many rows is full: compaction leaves it alone. Lance
#: otherwise treats every fragment under 1,048,576 rows as small, so each
#: compaction rewrote the whole table. Experiment 35 pod (4,096-dim vectors):
#: 12.4 s per compaction at 196,000 rows, about 0.2 s per file at the end.
#: With this bound a compaction rewrites at most this many rows plus the new
#: small fragments.
COMPACTION_TARGET_ROWS = 16_384

#: Metadata fields with a BTREE index. Change detection filters on
#: ``file_path`` and ``source_id``; the durability count and the stale-row
#: scan filter on ``source_id``.
SOURCE_INDEX_FIELDS = ("source_id", "file_path")


def compact_if_fragmented(table: Any) -> bool:
    """Merge the table's small data fragments when there are too many of them.

    Only fragments under :data:`COMPACTION_TARGET_ROWS` rows count and get
    merged, so the cost of one compaction does not grow with the table.

    Args:
        table: An open LanceDB table at its latest version.

    Returns:
        ``True`` when the table was compacted.
    """
    dataset = table.to_lance()
    small = sum(
        1 for fragment in dataset.get_fragments() if fragment.physical_rows < COMPACTION_TARGET_ROWS
    )
    if small < FRAGMENT_COMPACTION_THRESHOLD:
        return False
    # One thread: with a row target, Lance splits the work into several tasks,
    # and parallel tasks put the new fragments out of row order (pylance 10,
    # 20 of 20 trials). One task at a time keeps the row order.
    dataset.optimize.compact_files(target_rows_per_fragment=COMPACTION_TARGET_ROWS, num_threads=1)
    logger.debug("Compacted %d small fragments of table %r", small, table.name)
    _maintain_source_indexes(dataset)
    return True


def _maintain_source_indexes(dataset: Any) -> None:
    """Create a missing source index, or fold the unindexed rows into it.

    Queries still find unindexed rows, but by reading all their columns, so
    the refresh runs at every compaction: on a Mac, a stale-row scan took
    15 ms with 14,000 unindexed rows and 1.2 ms with none. One refresh of
    both indexes took about 20 to 30 ms at 47,000 to 200,000 rows. Only the
    source indexes are touched: ``optimize_indices`` names them, so the
    full-text index keeps its own upkeep (:mod:`.fts`).
    """
    schema = dataset.schema
    if "metadata" not in schema.names or not pa.types.is_struct(schema.field("metadata").type):
        return
    # A BTREE index needs a typed column; a field locked null-only has none.
    types = {field.name: field.type for field in schema.field("metadata").type}
    present = {tuple(index.field_names): index.name for index in dataset.describe_indices()}
    for field in SOURCE_INDEX_FIELDS:
        if not pa.types.is_string(types.get(field, pa.null())):
            continue
        column = f"metadata.{field}"
        name = present.get((column,))
        if name is None:
            dataset.create_scalar_index(column, "BTREE")
            logger.debug("Created a BTREE index on %s", column)
        elif dataset.stats.index_stats(name)["num_unindexed_rows"]:
            dataset.optimize.optimize_indices(index_names=[name])
