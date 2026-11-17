"""Ordered rows that survive a stop, and the resend rule (Exp 35 design D3, D39; tasks 3.1, 2.4).

One :class:`OrderedRows` serves one stage of one setup and run. It sits on top
of the stage's ``outputs35.RowFile``, which holds the runner lock, the key
check and the done-marker. Workers finish in any order; rows and trace rows
reach their files only in the frozen item order::

    log = outputs35.RowFile(run_dir, "answer", key, resume=resume)
    rows = OrderedRows(log, [q.qid for q in questions], trace=trace)
    for qid in rows.todo():          # pending results are committed first
        rows.dispatch(qid)           # synced before the paid call
        ...                          # the call, through a HostedGate
        rows.submit(qid, row, trace_row)          # a result with content
        rows.fail(qid, error, trace_row)          # an error with no content
    rows.finish(summary)             # done-marker only when every item has a row

Files in the stage folder, each appended one synced line at a time:

- ``<stage>.pending.jsonl``: every finished result (``id``, ``row``, ``trace``),
  written at once. It is removed after the done-marker.
- ``<stage>.dispatch.jsonl``: one ``id`` line before each send. An item with
  more than one line was resent; ``resent_calls`` counts those resends.
- ``<stage>.errors.jsonl``: one line per error that is not a rate limit and
  not out of credit (``id``, ``error``). The third such error of an item
  closes it as missing (pre-registration section 12).

Resend rule. A result with content is final, a refusal or an empty answer
included; the class never reads the content. An error with no content saves
no row, so ``--resume`` sends the item again. A rate-limit stop and a call cut
off before its result was saved write no error line, so they do not count
toward the cap. A stop between a row and its trace line is completed on the
next open, so a committed item has both lines.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from .trace import TraceWriter
except ImportError:  # imported as top-level ``_lib`` from an experiment folder
    from _lib.trace import TraceWriter  # type: ignore[no-redef]

__all__ = ["ERROR_CAP", "OrderedRows", "append_line", "read_lines"]

ERROR_CAP = 3
"""Errors (not rate limits, not out of credit) that close an item as missing."""


def read_lines(path: Path) -> list[dict[str, Any]]:
    """Return the lines of *path*; drop a last line that a stop cut part-way."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        text = text[: text.rfind("\n") + 1]
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def append_line(path: Path, record: Mapping[str, Any]) -> None:
    """Append *record* as one JSON line to *path*; flush and sync it before returning."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


class OrderedRows:
    """Commit one stage's results in frozen order, and apply the resend rule."""

    def __init__(
        self,
        log: Any,
        order: Sequence[str],
        *,
        trace: TraceWriter | None = None,
        id_field: str = "qid",
    ) -> None:
        """Read the stage's files; send nothing and write nothing yet.

        Args:
            log: The stage's open ``outputs35.RowFile``.
            order: The item ids in frozen order.
            trace: The run's trace writer, or None for a stage with no trace rows.
            id_field: The row key that holds the item id.
        """
        self._log = log
        self._order = [str(item) for item in order]
        self._trace = trace
        self._id_field = id_field
        folder = Path(log.path).parent
        self._pending_path = folder / f"{log.stage}.pending.jsonl"
        self._dispatch_path = folder / f"{log.stage}.dispatch.jsonl"
        self._errors_path = folder / f"{log.stage}.errors.jsonl"
        self._committed = log.done_ids(id_field)
        self._pending = {str(e["id"]): e for e in read_lines(self._pending_path)}
        self._sends = Counter(str(e["id"]) for e in read_lines(self._dispatch_path))
        self._errors: dict[str, list[str]] = {}
        for entry in read_lines(self._errors_path):
            self._errors.setdefault(str(entry["id"]), []).append(str(entry["error"]))

    @property
    def resent_calls(self) -> int:
        """Harness resends of this stage across every start: sends beyond the first per item."""
        return sum(count - 1 for count in self._sends.values() if count > 1)

    @property
    def closed_missing(self) -> list[str]:
        """Items closed as missing after :data:`ERROR_CAP` errors, in frozen order."""
        return [item for item in self._order if len(self._errors.get(item, [])) >= ERROR_CAP]

    def resends(self, item: str) -> int:
        """Return the harness resends of *item* so far."""
        return max(self._sends[item] - 1, 0)

    def todo(self) -> list[str]:
        """Commit the pending results in order; return the items to send.

        A pending result whose row reached the row file before a stop gets its
        missing trace line here. The returned items, in frozen order, have no
        row and no pending result.
        """
        if self._trace is not None:
            for item, entry in self._pending.items():
                if item in self._committed and entry.get("trace"):
                    if not self._trace.contains(entry["trace"]):
                        self._trace.append(entry["trace"])
        self.commit()
        return [i for i in self._order if i not in self._committed and i not in self._pending]

    def dispatch(self, item: str) -> None:
        """Record a send of *item*; synced before the paid call is made."""
        append_line(self._dispatch_path, {"id": item})
        self._sends[item] += 1

    def submit(
        self, item: str, row: Mapping[str, Any], trace: Mapping[str, Any] | None = None
    ) -> None:
        """Keep the finished result of *item* on disk at once, then commit what is in order.

        Args:
            item: The item id.
            row: The row to save. It is final whatever it holds.
            trace: The item's trace row (``TraceWriter.row``), or None. Its
                ``resent_calls`` is set here.
        """
        entry = {
            "id": item,
            "row": dict(row),
            "trace": None if trace is None else {**trace, "resent_calls": self.resends(item)},
        }
        append_line(self._pending_path, entry)
        self._pending[item] = entry
        self.commit()

    def fail(self, item: str, error: str, trace: Mapping[str, Any] | None = None) -> bool:
        """Record an error with no content; close *item* as missing at the cap.

        Call it only for an error that is not a rate limit and not out of
        credit. The item stays pending, so ``--resume`` sends it again, until
        its third error. Then it gets the row ``{id: item, "missing": True,
        "error": error}``, and the stage goes on.

        Returns:
            True when this error closed the item as missing.
        """
        append_line(self._errors_path, {"id": item, "error": error})
        errors = self._errors.setdefault(item, [])
        errors.append(error)
        if len(errors) < ERROR_CAP:
            return False
        self.submit(item, {self._id_field: item, "missing": True, "error": error}, trace)
        return True

    def commit(self) -> None:
        """Write the longest run of finished results that follows the committed rows."""
        for item in self._order:
            if item in self._committed:
                continue
            entry = self._pending.get(item)
            if entry is None:
                return
            self._log.append(entry["row"])
            self._committed.add(item)
            if self._trace is not None and entry.get("trace"):
                self._trace.append(entry["trace"])

    def finish(self, summary: Mapping[str, Any]) -> bool:
        """Write the done-marker when every item has a row, then remove the pending file.

        The marker holds *summary*, ``resent_calls`` and ``closed_missing``. A
        stage that counts these per call (the judge stage) gives its own in
        *summary*, and they win.

        Returns:
            False, with no marker, while an item has no row (``--resume`` sends it).
        """
        self.commit()
        if any(item not in self._committed for item in self._order):
            return False
        self._log.mark_done(
            {"resent_calls": self.resent_calls, "closed_missing": self.closed_missing, **summary}
        )
        self._pending_path.unlink(missing_ok=True)
        return True
