"""Direct children of the recorded router pid, and their memory (design D9).

Each loaded model of the router runs as a child ``llama-server``. The router
item's memory is the router's resident size plus the resident size of each
direct child whose command line holds the recorded binary path. OMRS reads
the children of the recorded pid only; it lists no other process:

* macOS: ``proc_listchildpids`` of ``libproc`` (spike 1.3, macOS half);
* Linux: every ``/proc/<pid>/task/*/children`` file, because each child sits
  under the router thread that spawned it, so the main thread's file alone
  finds none (spike 1.3, Linux half).

Children share the router's process group, so the group stop in
:func:`omrs.integrations.llamacpp_runtime.process.stop` reaches them.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from pathlib import Path

from . import process

#: Most children read on macOS; the router runs at most 16 models at once.
_MAX_CHILDREN = 256


def _darwin_children(pid: int) -> list[int]:
    path = ctypes.util.find_library("proc") or "/usr/lib/libproc.dylib"
    try:
        libproc = ctypes.CDLL(path, use_errno=True)
    except OSError:
        return []
    buffer = (ctypes.c_int * _MAX_CHILDREN)()
    count = libproc.proc_listchildpids(ctypes.c_int(pid), buffer, ctypes.sizeof(buffer))
    if count <= 0:
        return []
    return [int(child) for child in buffer[: min(count, _MAX_CHILDREN)] if child > 0]


def _linux_children(pid: int) -> list[int]:
    found: list[int] = []
    for children_file in sorted(Path(f"/proc/{pid}/task").glob("*/children")):
        try:
            text = children_file.read_text(encoding="ascii")
        except OSError:
            continue
        found += [int(word) for word in text.split() if word.isdigit()]
    return found


def direct_children(pid: int) -> list[int]:
    """Return the direct child pids of *pid*, sorted; ``[]`` on another platform."""
    if pid <= 0:
        return []
    if sys.platform == "darwin":
        return sorted(set(_darwin_children(pid)))
    if sys.platform.startswith("linux"):
        return sorted(set(_linux_children(pid)))
    return []


def tree_rss(pid: int, binary: str) -> int | None:
    """Return the router's resident memory plus that of its model children, in bytes.

    A child counts only when its command line holds *binary*, so a helper the
    router might start for something else is left out.

    Returns:
        The sum, or ``None`` when the router's own size cannot be read.
    """
    own = process.rss_bytes(pid)
    if own is None:
        return None
    total = own
    for child in direct_children(pid):
        if process.owns(child, binary):
            total += process.rss_bytes(child) or 0
    return total
