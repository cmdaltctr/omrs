"""Magika file-type detection — in-process Python API transport.

Extracted from ``codebase_map.py`` in Phase 5. Owns the detection data
primitives (``FileEntry``, ``_EXCLUDED_DIRS``) so that ``codebase_map.py``
imports them from here rather than the reverse. Provides:
- ``FileEntry`` — dataclass for a single detected file
- ``_EXCLUDED_DIRS`` — directory names skipped during scanning
- ``_is_magika_available()`` — availability gate for detection
- ``scan_with_magika(path)`` — scan a directory and return typed file entries

Detection runs in process through ``magika.Magika().identify_paths``
(ADR-117): one model load per process, cached in ``_get_magika_instance``.
The ``magika`` import stays lazy inside that wrapper so importing this
module never loads the magika package or ONNX Runtime.
``_magika_binary``, ``_resolve_magika`` and ``_is_magika_available`` remain
the availability gate and keep the ``MAGIKA_BINARY`` settings injection
(TDR-025): the bundled CLI binary is the availability signal and the smoke
tool's ground truth.

``codebase_map.py`` re-exports ``_is_magika_available`` and ``scan_with_magika``
as thin wrappers so existing ``omrs.codebase_map.*`` references (including
test patches) keep resolving.
"""

from __future__ import annotations

import logging
import os
import shutil
import sysconfig
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.settings import get_default_effective_settings

logger = logging.getLogger(__name__)


# ── Detection data primitives (owned here, re-exported by codebase_map) ──
# Directories excluded from both Magika and suffix scanning.
_EXCLUDED_DIRS: set[str] = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    ".pytest_cache",
    "dist",
    "build",
    ".opencode",
}


@dataclass
class FileEntry:
    """A single file detected by Magika or suffix fallback.

    Attributes:
        path: Relative path from the project root.
        group: Magika group (e.g., "code", "document", "config", "binary").
        label: Magika label (e.g., "typescript", "markdown", "yaml").
        is_text: Whether the file is text (vs binary).
        suffix: File extension including the dot (e.g., ".py").
    """

    path: str
    group: str
    label: str
    is_text: bool
    suffix: str


def _magika_binary(settings: Any | None = None) -> str:
    """Return the configured Magika binary name.

    Args:
        settings: Injected effective settings carrying ``magika_binary``.
            ``None`` keeps the legacy process-global resolution for
            entry points that resolve at their own boundary.

    Raises:
        RuntimeError: When *settings* is ``None`` and no process-global
            default is installed (direct-Engine processes; the caller
            should inject settings instead).
    """
    if settings is not None:
        return settings.magika_binary
    return get_default_effective_settings().magika_binary


def _scripts_folder() -> Path:
    """Return the folder where the running Python installs its programs."""
    return Path(sysconfig.get_path("scripts"))


def _resolve_magika(settings: Any | None = None) -> str | None:
    """Return the Magika program to run, or ``None`` when there is none.

    ``$PATH`` comes first. ``magika`` is a base dependency, so an install
    also puts the program next to the running Python; the login item starts
    ``omrs web`` with a short ``$PATH`` that lacks that folder, so the
    folder is checked too. A configured path is used as given.

    Args:
        settings: Injected effective settings carrying ``magika_binary``.
    """
    binary = _magika_binary(settings)
    found = shutil.which(binary)
    if found is not None or os.sep in binary:
        return found
    return shutil.which(binary, path=os.fspath(_scripts_folder()))


def _is_magika_available(settings: Any | None = None) -> bool:
    """Check if the Magika program is on ``$PATH`` or next to the running Python."""
    return _resolve_magika(settings) is not None


# Groups that stay readable even when the model marks ``is_text`` false
# (PDF documents; taxonomy rows such as Ada or BRF). Everything else
# with ``is_text=false`` is treated as binary at this boundary.
_READABLE_GROUPS = frozenset({"document", "code", "text"})


def _normalise_detected(group: str, label: str, is_text: bool) -> tuple[str, str]:
    """Apply the OMRS boundary rules to one validated Magika label.

    Binary boundary: a non-readable group outside ``document``, ``code``,
    and ``text`` becomes ``binary`` so the pipeline's existing
    ``content_type.startswith("binary")`` skip fires. The label and
    ``is_text`` are preserved, and readable false-text groups keep their
    group so documents such as PDF stay reachable by readers.

    Alias normalisation: only the two confirmed readable aliases
    ``text/markdown -> document/markdown`` and ``text/txt ->
    document/text`` are mapped, keeping suffix-map identity stable
    without a taxonomy framework.
    """
    if not is_text and group not in _READABLE_GROUPS:
        return "binary", label
    if is_text and group == "text":
        if label == "markdown":
            return "document", "markdown"
        if label == "txt":
            return "document", "text"
    return group, label


_MAGIKA_INSTANCE: Any = None
_MAGIKA_LOCK = threading.Lock()


def reset_magika_cache() -> None:
    """Drop the cached Magika instance (test seam, mirrors the reranker)."""
    global _MAGIKA_INSTANCE
    _MAGIKA_INSTANCE = None


def _get_magika_instance() -> Any:
    """Return the process-wide Magika client, constructing it at most once.

    The ``magika`` import and ``Magika()`` construction stay inside this
    function so importing this module never loads the magika package or
    ONNX Runtime. A lock with a double check guards the cold path:
    ``functools.lru_cache`` alone permits concurrent cold callers to run
    the wrapped function twice, which here would build two ONNX sessions.
    Tests call ``reset_magika_cache()`` instead of poking the cache.

    Returns:
        A ``magika.Magika`` instance (``Any`` because the package is only
        imported lazily here).
    """
    global _MAGIKA_INSTANCE
    if _MAGIKA_INSTANCE is None:
        with _MAGIKA_LOCK:
            if _MAGIKA_INSTANCE is None:
                from magika import Magika

                _MAGIKA_INSTANCE = Magika()
    return _MAGIKA_INSTANCE


def _collect_files(root: Path) -> list[Path]:
    """Walk *root* (no depth limit) and return the files to identify.

    ``_EXCLUDED_DIRS`` are skipped during the walk. Directory symlinks are
    skipped as well: following them would let excluded folders and targets
    outside the scan root re-enter the walk. A directory that cannot be
    listed fails the whole scan with ``ValueError`` so the caller falls
    back to suffix detection instead of silently missing files.
    """
    files: list[Path] = []

    def _collect(directory: Path) -> None:
        try:
            children = sorted(directory.iterdir())
        except OSError as exc:
            raise ValueError(f"Magika walk cannot list {directory}: {exc}") from exc
        for child in children:
            if child.is_dir():
                if child.name in _EXCLUDED_DIRS or child.is_symlink():
                    continue
                _collect(child)
            elif child.is_file():
                files.append(child)

    _collect(root)
    return files


def scan_with_magika(path: str, settings: Any | None = None) -> list:
    """Scan a directory through the in-process Magika Python API.

    Walks the directory itself (no depth limit, skipping
    ``_EXCLUDED_DIRS``) and runs one ``identify_paths`` call for every
    collected file. Each result must report success with a non-empty
    string ``group``/``label`` and a boolean ``is_text``; one invalid
    result fails the whole scan with ``ValueError`` so the caller falls
    back to suffix detection instead of trusting partial results.
    Boundary normalisation is applied per entry (ADR-068 decision 5).

    Args:
        path: Directory path to scan, or a single file (keyed ``"."``).
        settings: Injected effective settings carrying ``magika_binary``;
            ``None`` keeps the legacy process-global resolution.

    Returns:
        List of ``FileEntry`` objects for each detected file.

    Raises:
        FileNotFoundError: If the availability gate finds no Magika
            program (``_resolve_magika`` returned ``None``).
        ValueError: If ``Magika()`` construction or ``identify_paths``
            raises, or any result fails validation.
    """
    program = _resolve_magika(settings)
    if program is None:
        raise FileNotFoundError(f"Magika CLI binary not found: {_magika_binary(settings)}")

    root = Path(path)
    if root.is_file():
        files: list[Path] = [root]
    else:
        files = _collect_files(root)

    if not files:
        return []

    try:
        results = _get_magika_instance().identify_paths(files)
    except Exception as exc:
        logger.warning(
            "Magika in-process detection failed (%s), falling back to suffix detection", exc
        )
        raise ValueError(f"Magika identify_paths failed: {exc}") from exc

    entries: list[FileEntry] = []
    for file_path, result in zip(files, results, strict=True):
        if not (getattr(result, "ok", False) or getattr(result, "status", None) == "ok"):
            raise ValueError(f"Magika result status is not 'ok' for {file_path}")
        output = getattr(result, "output", None)
        if output is None:
            raise ValueError(f"Magika result lacks an output object for {file_path}")
        group = getattr(output, "group", None)
        label = getattr(output, "label", None)
        is_text = getattr(output, "is_text", None)
        if not isinstance(group, str) or not group:
            raise ValueError(f"Magika result has an invalid group for {file_path}")
        if not isinstance(label, str) or not label:
            raise ValueError(f"Magika result has an invalid label for {file_path}")
        if not isinstance(is_text, bool):
            raise ValueError(f"Magika result has a non-boolean is_text for {file_path}")

        normalised_group, normalised_label = _normalise_detected(group, label, is_text)
        # The walk only collects paths under *root*, so this cannot fail.
        rel_path = str(file_path.relative_to(root))
        entries.append(
            FileEntry(
                path=rel_path,
                group=normalised_group,
                label=normalised_label,
                is_text=is_text,
                suffix=file_path.suffix.lower(),
            )
        )

    return entries
