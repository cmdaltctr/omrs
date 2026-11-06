"""The shared llama.cpp runtime manager (capability ``llamacpp-runtimes``).

One manager per OMRS process. Components (Chat, embeddings, OCR engines,
decision models) are clients of a runtime; they do not own it. Every local
llama.cpp model except OCR runs on the one router (runtime ``router``);
:func:`open_router` gives this process's per-model view of it. ``manager``
and ``process`` hold the lifecycle; this package facade exports the stable
surface only.
"""

from __future__ import annotations

from .lease import OPERATOR_STOP, RuntimeLease, RuntimeRequestFailed, RuntimeUnavailable
from .locks import LockFile, LockNotSupportedError
from .manager import RuntimeManager, install_sigterm_exit
from .model_reasons import MODEL_REASONS, MODEL_STATES, ModelUnavailable
from .readiness import MODEL_LOAD_TIMEOUT_SECONDS
from .router_lease import RouterLease, open_router
from .router_spec import ROUTER_ID, external_router_spec, model_id, router_spec
from .spec import DeclaredFile, RuntimeSpec, chat_spec, decision_spec, embeddings_spec, ocr_spec
from .state import ServerRecord, read_server_record, runtime_dir, state_root, write_server_record

__all__ = [
    "MODEL_LOAD_TIMEOUT_SECONDS",
    "MODEL_REASONS",
    "MODEL_STATES",
    "OPERATOR_STOP",
    "ROUTER_ID",
    "DeclaredFile",
    "LockFile",
    "LockNotSupportedError",
    "ModelUnavailable",
    "RouterLease",
    "RuntimeLease",
    "RuntimeManager",
    "RuntimeRequestFailed",
    "RuntimeSpec",
    "RuntimeUnavailable",
    "ServerRecord",
    "chat_spec",
    "decision_spec",
    "embeddings_spec",
    "external_router_spec",
    "install_sigterm_exit",
    "model_id",
    "ocr_spec",
    "open_router",
    "read_server_record",
    "router_spec",
    "runtime_dir",
    "state_root",
    "write_server_record",
]
