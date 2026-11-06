"""SHA-256 of listed model files with a ``hashes.json`` cache (design D5).

Hashing a 4 GiB file takes seconds, so the router folder keeps
``hashes.json``: one item per path with the file's size, ``mtime_ns`` and
SHA-256. A cached value counts only while size and ``mtime_ns`` still match.
The file holds no settings; a broken file reads as empty. Callers hold the
router's ``start.lock``, so two processes do not write it at once.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

_CHUNK = 1024 * 1024


def hash_file(path: str) -> str:
    """Return the SHA-256 of *path* in lower-case hex.

    Raises:
        OSError: The file cannot be read.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


class HashCache:
    """The ``hashes.json`` cache of one router folder.

    Args:
        path: The cache file; created on the first stored value.
        save: Whether a new value is written to the file. ``GET /v1/runtimes``
            reads with ``False``, because a read writes nothing.
    """

    def __init__(self, path: Path, *, save: bool = True) -> None:
        self.path = Path(path)
        self._save_values = save
        self._items = self._read()

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def sha256(self, path: str) -> str | None:
        """Return the SHA-256 of *path*, from the cache when size and ``mtime_ns`` match.

        Returns:
            The hex digest, or ``None`` when *path* is not a readable regular file.
        """
        try:
            info = os.stat(path)
        except OSError:
            return None
        if not os.path.isfile(path):
            return None
        cached = self._items.get(path)
        if (
            isinstance(cached, dict)
            and cached.get("size") == info.st_size
            and cached.get("mtime_ns") == info.st_mtime_ns
            and isinstance(cached.get("sha256"), str)
        ):
            return str(cached["sha256"])
        try:
            digest = hash_file(path)
        except OSError:
            return None
        self._items[path] = {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "sha256": digest}
        if self._save_values:
            self._save()
        return digest

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        temporary.write_text(json.dumps(self._items, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)
