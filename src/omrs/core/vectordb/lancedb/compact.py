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


def compact_if_fragmented(table: Any) -> bool:
    """Merge the table's data fragments when there are too many of them.

    Args:
        table: An open LanceDB table at its latest version.

    Returns:
        ``True`` when the table was compacted.
    """
    dataset = table.to_lance()
    fragments = len(dataset.get_fragments())
    if fragments < FRAGMENT_COMPACTION_THRESHOLD:
        return False
    dataset.optimize.compact_files()
    logger.debug("Compacted %d fragments of table %r", fragments, table.name)
    return True
