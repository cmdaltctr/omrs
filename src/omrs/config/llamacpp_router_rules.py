"""Value rules of the llama.cpp router settings (one-llamacpp-router, design D2).

The accepted words of ``llamacpp_router_server`` live in ``rules.ACCEPTED`` and
the ranges of the two whole-number settings live in ``user_config.INT_KEY_BOUNDS``
(the one table that binds the environment, the saved page value and ``omrs.jsonc``).
This module adds the one rule that needs two settings together: a managed router
binds this machine only, so its address must be a loopback ``http`` address.

The rule is checked when a value is saved or a router starts. Reading settings does
not apply it, so a half-edited pair of settings never stops OMRS from starting.

This module is a leaf: it imports only ``config/`` modules that do not import it.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from .rules import address_problem

#: Hosts that mean this machine. The same three words as the launch rule.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LOOPBACK_RULE = (
    "A managed router address must be an http address on this machine: 127.0.0.1, localhost or ::1."
)


def router_url_problem(mode: str, url: str) -> str | None:
    """Return the rule that router address *url* breaks in *mode*, or ``None``.

    Any mode needs an absolute http or https address (``rules.address_problem``).
    ``managed`` also needs ``http`` and a loopback host. ``external`` accepts
    any host.

    Args:
        mode: ``managed`` or ``external``.
        url: The router address, such as ``http://127.0.0.1:8080/v1``.

    Returns:
        The rule, which never holds *url*.
    """
    rule = address_problem(url)
    if rule is not None or mode != "managed":
        return rule
    parts = urlsplit(url)
    return None if parts.scheme == "http" and parts.hostname in LOOPBACK_HOSTS else LOOPBACK_RULE
