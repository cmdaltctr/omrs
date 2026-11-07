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
        "router_server",
        "Who runs the llama.cpp router",
        "choice",
        "llamacpp_router_server",
        "LLAMACPP_ROUTER_SERVER",
    ),
)
