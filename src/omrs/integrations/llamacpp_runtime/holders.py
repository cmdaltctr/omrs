"""Which OMRS processes hold a runtime (the ``clients`` field of ``GET /v1/runtimes``).

A shared ``clients.lock`` cannot tell a holder in this process from a holder in
another one: a probe on a second descriptor of the same process is refused too.
Each joined lease therefore also holds a shared lock on ``holder-<pid>.lock``.
A status read tries every file of another pid. A refused lock means that
process still holds the runtime. The kernel drops the lock when the process
ends, so a killed process leaves a file that no longer counts.
"""

from __future__ import annotations

import os
from pathlib import Path

from .locks import LockFile


def _own_name() -> str:
    return f"holder-{os.getpid()}.lock"


def hold(folder: Path) -> LockFile:
    """Take this process's shared hold on the runtime in *folder*; close it to drop it."""
    lock = LockFile(folder / _own_name())
    lock.acquire(shared=True)
    return lock


def other_process_holds(folder: Path) -> bool:
    """Return whether a process other than this one holds the runtime in *folder*.

    Creates and writes nothing: it only probes the hold files that exist.
    """
    own = _own_name()
    for path in sorted(folder.glob("holder-*.lock")):
        if path.name == own:
            continue
        probe = LockFile(path)
        try:
            if not probe.acquire(blocking=False):
                return True
        finally:
            probe.close()
    return False
