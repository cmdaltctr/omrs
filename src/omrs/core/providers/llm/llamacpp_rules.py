"""Settings fields of the llama.cpp server card (design D12, ADR-108).

The launch rules (program check, model kind, loopback port, argument lists,
child environment, reasons) moved to
``integrations/llamacpp_runtime/rules.py`` with the shared runtime manager
(change ``managed-llamacpp-runtimes``, design D1); only the card field list
stayed here, because it is settings data and imports the provider
``ConnectionField``. Nothing here starts a process.
"""

from __future__ import annotations

from .connection import ConnectionField

#: Settings of the managed server. They are not part of any provider
#: descriptor: the card shows them in its own "Local server" block.
LLAMACPP_SERVER_FIELDS: tuple[ConnectionField, ...] = (
    ConnectionField(
        "server_binary", "Program path", "text", "llamacpp_server_binary", "LLAMACPP_SERVER_BINARY"
    ),
    ConnectionField(
        "chat_server",
        "Who runs the Chat server",
        "choice",
        "llamacpp_chat_server",
        "LLAMACPP_CHAT_SERVER",
    ),
    ConnectionField(
        "context_window",
        "Context window (tokens)",
        "int",
        "llamacpp_context_window",
        "LLAMACPP_CONTEXT_WINDOW",
        minimum=2048,
        maximum=262144,
    ),
    ConnectionField(
        "idle_sleep",
        "Idle sleep (seconds)",
        "int",
        "llamacpp_idle_sleep_seconds",
        "LLAMACPP_IDLE_SLEEP_SECONDS",
        minimum=0,
        maximum=86400,
    ),
)
