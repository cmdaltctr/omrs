"""The one llama.cpp runtime manager of this process (managed-llamacpp-runtimes D1).

Chat, embeddings and OCR leases all come from this one instance. The module
imports neither ``compose`` nor ``core``, so the OCR route builder in
``capabilities`` (which ``core/ingestion`` calls) can take the manager here
without reaching the composition root.
"""

from __future__ import annotations

import threading

from .integrations.llamacpp_runtime import RuntimeManager, state_root

_lock = threading.Lock()
_manager: RuntimeManager | None = None


def runtime_manager() -> RuntimeManager:
    """Return this process's runtime manager (one per state root, so one per process)."""
    global _manager
    with _lock:
        root = state_root()
        if _manager is None or _manager.root != root:
            old, _manager = _manager, RuntimeManager(root)
            if old is not None:
                old.close()
        return _manager


def close_runtime_manager() -> None:
    """Leave every lease and drop the manager; the next call builds a new one (tests)."""
    global _manager
    with _lock:
        old, _manager = _manager, None
    if old is not None:
        old.close()
