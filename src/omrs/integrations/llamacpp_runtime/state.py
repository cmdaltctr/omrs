"""The runtime state folder and its ``server.json`` record (design D3).

The root comes from the environment alone (``OMRS_STATE_DIR``, else
``$XDG_STATE_HOME/omrs``, else ``~/.local/state/omrs``) so every OMRS
process, including the CLI that cannot see ``omrs web`` flags, agrees on one
folder. The files hold no settings and no secrets; every OMRS process may
write them (root ``AGENTS.md`` Gotcha 17). ``server.json`` is written to a
temporary file and renamed, so a reader never sees a partial record, and a
broken file reads as no record.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from .spec import RUNTIME_ID_RE

#: The one JSON file of a runtime folder.
SERVER_FILE = "server.json"

_State = Literal["starting", "running", "stopped"]
_StoppedBy = Literal["operator", "idle", "last-client"]


class ServerRecord:
    """What a runtime folder says about its server.

    The record is mutable on purpose: the manager updates one field at a time
    (state, stopped_by, reason) and rewrites the file atomically. It is not
    frozen data like :class:`~omrs.integrations.llamacpp_runtime.spec.RuntimeSpec`,
    because two processes write it at different moments of one lifecycle.
    """

    __slots__ = (
        "pid",
        "port",
        "binary",
        "digest",
        "build",
        "state",
        "stopped_by",
        "generation",
        "reason",
        "reason_text",
    )

    def __init__(
        self,
        *,
        pid: int,
        port: int,
        binary: str,
        digest: str,
        build: int | None = None,
        state: _State = "starting",
        stopped_by: _StoppedBy | None = None,
        generation: int = 1,
        reason: str | None = None,
        reason_text: str | None = None,
    ) -> None:
        self.pid = pid
        self.port = port
        self.binary = binary
        self.digest = digest
        self.build = build
        self.state = state
        self.stopped_by = stopped_by
        self.generation = generation
        self.reason = reason
        self.reason_text = reason_text

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the record."""
        return {
            "pid": self.pid,
            "port": self.port,
            "binary": self.binary,
            "digest": self.digest,
            "build": self.build,
            "state": self.state,
            "stopped_by": self.stopped_by,
            "generation": self.generation,
            "reason": self.reason,
            "reason_text": self.reason_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServerRecord:
        """Build a record from :meth:`to_dict` output, coerced where needed."""
        return cls(
            pid=int(data["pid"]),
            port=int(data["port"]),
            binary=str(data["binary"]),
            digest=str(data["digest"]),
            build=int(data["build"]) if data.get("build") is not None else None,
            state=data.get("state", "starting"),
            stopped_by=data.get("stopped_by"),
            generation=int(data.get("generation", 1)),
            reason=data.get("reason"),
            reason_text=data.get("reason_text"),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ServerRecord):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ServerRecord({self.to_dict()})"


def state_root(environ: dict[str, str] | None = None) -> Path:
    """Return the runtime state root.

    Args:
        environ: The environment to read; the process environment by default.

    Returns:
        ``OMRS_STATE_DIR``, else ``$XDG_STATE_HOME/omrs``, else
        ``~/.local/state/omrs``. The folder must be on a local disk; ``flock``
        is not reliable on NFS or SMB (the configuration guide says so).
    """
    env = dict(os.environ) if environ is None else dict(environ)
    explicit = env.get("OMRS_STATE_DIR", "").strip()
    if explicit:
        return Path(explicit)
    xdg = env.get("XDG_STATE_HOME", "").strip()
    if xdg:
        return Path(xdg) / "omrs"
    return Path.home() / ".local" / "state" / "omrs"


def runtime_dir(root: Path, runtime_id: str) -> Path:
    """Return ``<root>/runtimes/<runtime_id>`` after checking the id."""
    if not RUNTIME_ID_RE.fullmatch(runtime_id or ""):
        raise ValueError(f"not a runtime id: {runtime_id!r}")
    return Path(root) / "runtimes" / runtime_id


def write_server_record(folder: Path, record: ServerRecord) -> None:
    """Write *record* to ``<folder>/server.json`` atomically.

    The JSON goes to ``server.json.tmp`` first, then the file is renamed over
    the old one. A crash between the two leaves the old record intact.
    """
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / SERVER_FILE
    temporary = folder / f"{SERVER_FILE}.tmp"
    payload = json.dumps(record.to_dict(), ensure_ascii=True)
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, target)


def read_server_record(folder: Path) -> ServerRecord | None:
    """Return the record of *folder*, or ``None`` when it is missing or broken.

    A file the manager cannot parse reads as no record: the next start writes
    a fresh one. No exception escapes.
    """
    path = Path(folder) / SERVER_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return ServerRecord.from_dict(data)
    except (KeyError, TypeError, ValueError):
        return None
