"""Shared parts of every decision model request (change document-reading-routers, D2).

A decision model answers one System One ``noul`` question. The ``noul`` type
has the two options ``no`` and ``yes``, and the answer is P(yes). The request
shape follows the Experiment 43 runners, which made the only recorded live
requests: the question id is ``fidelity`` and the page text goes in
``state.text``.

Only a hosted image request carries ``TypeSafe-Danger-Zone-Images: true``.
Hosted means the address is not a loopback address (design D7).

Nothing here logs. A malformed reply raises :class:`MalformedReplyError`,
whose text is the fixed reason only, never the reply.
"""

from __future__ import annotations

import base64
import ipaddress
import math
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

#: The question id of every request (Experiment 43 used ``fidelity``).
QUESTION_ID = "fidelity"
#: The options of a ``noul`` question. The type implies them, so the request
#: does not list them; the answer is the probability of ``yes``.
OPTIONS = ("no", "yes")
SYSTEMONE_PATH = "/v1/systemone"
#: TypeSafe needs this header to take an image. Only hosted image requests send it.
HOSTED_IMAGE_HEADER = "TypeSafe-Danger-Zone-Images"
#: The fixed reason of a reply without a usable P(yes).
MALFORMED_REPLY = "malformed-reply"


class MalformedReplyError(ValueError):
    """The reply holds no P(yes) in [0, 1]. The text is the fixed reason only."""

    def __init__(self) -> None:
        """Carry the fixed reason, never the reply."""
        super().__init__(MALFORMED_REPLY)


@dataclass(frozen=True)
class DecisionRequest:
    """One HTTP request to a decision model. ``repr`` hides the body and headers.

    Attributes:
        url: Where the request goes.
        body: The JSON body.
        headers: HTTP headers, which can hold a key.
    """

    url: str
    body: dict[str, Any] = field(repr=False)
    headers: dict[str, str] = field(repr=False)


def is_loopback(address: str) -> bool:
    """Return whether *address* names this machine (``localhost`` or a loopback IP)."""
    try:
        host = urlsplit(address).hostname or ""
    except ValueError:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def endpoint(address: str, path: str = SYSTEMONE_PATH) -> str:
    """Return *address* joined to *path* with one slash."""
    return address.rstrip("/") + path


def noul_questions(question: str) -> dict[str, Any]:
    """Return the one ``noul`` question of a request."""
    return {QUESTION_ID: {"type": "noul", "instructions": question}}


def png_base64(png: bytes) -> str:
    """Return *png* as base64 text with no ``data:`` prefix."""
    return base64.b64encode(png).decode("ascii")


def headers(*, key: str | None, hosted: bool, image: bool) -> dict[str, str]:
    """Return the request headers.

    Args:
        key: The resolved key, sent as a bearer token when set.
        hosted: Whether the address is not a loopback address.
        image: Whether the request carries a page image.
    """
    result = {"Content-Type": "application/json"}
    if key:
        result["Authorization"] = f"Bearer {key}"
    if hosted and image:
        result[HOSTED_IMAGE_HEADER] = "true"
    return result


def parse_p_yes(reply: Any) -> float:
    """Return P(yes) from a System One reply.

    Raises:
        MalformedReplyError: The answer is missing, not a number, not finite
            or outside [0, 1].
    """
    try:
        value = reply["answers"][QUESTION_ID]["noul"]
    except (KeyError, TypeError, IndexError):
        raise MalformedReplyError() from None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MalformedReplyError()
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise MalformedReplyError()
    return float(value)


def reported_model(reply: Any) -> str | None:
    """Return the model name the reply reports, or ``None``."""
    model = reply.get("model") if isinstance(reply, dict) else None
    return model if isinstance(model, str) else None
