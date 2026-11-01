"""The shared llama.cpp runtime manager (capability ``llamacpp-runtimes``).

One manager per OMRS process. Components (Chat, embeddings, OCR engines)
are clients of a runtime; they do not own it. ``manager`` and ``process``
hold the lifecycle; this package facade exports the stable surface only.
"""

from __future__ import annotations

from .locks import LockFile, LockNotSupportedError
from .spec import DeclaredFile, RuntimeSpec, chat_spec, embeddings_spec, ocr_spec
from .state import ServerRecord, read_server_record, runtime_dir, state_root, write_server_record

__all__ = [
    "DeclaredFile",
    "LockFile",
    "LockNotSupportedError",
    "RuntimeSpec",
    "ServerRecord",
    "chat_spec",
    "embeddings_spec",
    "ocr_spec",
    "read_server_record",
    "runtime_dir",
    "state_root",
    "write_server_record",
]
