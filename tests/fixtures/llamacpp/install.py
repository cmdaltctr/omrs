"""Install helpers for the fake ``llama-server`` fixture.

The launch rules accept only an absolute path to an executable file named
exactly ``llama-server``. Tests therefore copy the fake server behind a
Python shebang, which keeps the fixture importable and diffable in Git.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

#: This file and the fake server sit in the same folder.
FIXTURE_DIR = Path(__file__).resolve().parent

SHEBANG = "#!/usr/bin/env python3\n"


def install_fake_server(folder: Path) -> Path:
    """Copy the fake server into *folder* as an executable ``llama-server``.

    Args:
        folder: Destination folder; created when missing.

    Returns:
        The program path, ready for the launch rule.
    """
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "llama-server"
    source = FIXTURE_DIR / "fake_llama_server.py"
    target.write_text(SHEBANG + source.read_text(encoding="utf-8"), encoding="utf-8")
    mode = target.stat().st_mode
    target.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


def touch_count_file(folder: Path, name: str, value: int) -> Path:
    """Write *value* into ``folder/name`` and return the path.

    The fake server reads such files for counters that must survive one
    process (``FAKE_LLAMA_BIND_FAILS``, ``FAKE_LLAMA_STARTS``).
    """
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(str(value), encoding="utf-8")
    return path


def read_start_log(path: Path) -> list[dict[str, object]]:
    """Return one entry per recorded server start (pid and argv)."""
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        pid_text, _, argv_json = line.partition(" ")
        entries.append({"pid": int(pid_text), "argv": json.loads(argv_json)})
    return entries


def process_alive(pid: int) -> bool:
    """Return whether *pid* exists (signal 0), as ``os.kill`` does."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - exists but not ours
        return True
    return True
