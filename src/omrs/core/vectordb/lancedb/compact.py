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
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["FRAGMENT_COMPACTION_THRESHOLD", "compact_if_fragmented"]

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
    return True
