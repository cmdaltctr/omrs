"""The shared llama.cpp runtime manager (capability ``llamacpp-runtimes``).

One manager per OMRS process. Components (Chat, embeddings, OCR engines,
decision models) are clients of a runtime; they do not own it. ``manager``
and ``process`` hold the lifecycle; this package facade exports the stable
surface only.
"""

from __future__ import annotations

from .lease import OPERATOR_STOP, RuntimeLease, RuntimeRequestFailed, RuntimeUnavailable
from .locks import LockFile, LockNotSupportedError
from .manager import RuntimeManager, install_sigterm_exit
from .spec import DeclaredFile, RuntimeSpec, chat_spec, decision_spec, embeddings_spec, ocr_spec
from .state import ServerRecord, read_server_record, runtime_dir, state_root, write_server_record

__all__ = [
    "OPERATOR_STOP",
    "DeclaredFile",
    "LockFile",
    "LockNotSupportedError",
    "RuntimeLease",
    "RuntimeManager",
    "RuntimeRequestFailed",
    "RuntimeSpec",
    "RuntimeUnavailable",
    "ServerRecord",
    "chat_spec",
    "decision_spec",
    "embeddings_spec",
    "install_sigterm_exit",
    "ocr_spec",
    "read_server_record",
    "runtime_dir",
    "state_root",
    "write_server_record",
]
