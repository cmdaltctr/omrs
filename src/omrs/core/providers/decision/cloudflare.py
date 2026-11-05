"""Cloudflare Workers AI decision model (design D2). Not yet tested.

Written from the Experiment 38 notes and tested against fake servers only.
The route is ``<address>/ai/run/@cf/cloudflare/<model>``, where the address
holds the account id, for example
``https://api.cloudflare.com/client/v4/accounts/<account id>``. The body is
the Jev request format with the image as raw base64 in an ``images`` list.
Workers AI wraps the answer in ``result``. The reply names the model without
a version, so a silent model change cannot be seen. The key is the Cloudflare
API token by reference. Read the Workers AI data retention terms before the
first hosted run.
"""

from __future__ import annotations

from typing import Any

from .base import DecisionRequest, endpoint, headers, noul_questions, parse_p_yes, png_base64

#: No live request of this kind is recorded yet; Settings shows "Not yet tested".
NOT_YET_TESTED = True
LOCAL_RUNTIME = False
_ROUTE = "/ai/run/@cf/cloudflare/"


def build_request(
    *,
    address: str,
    model: str,
    question: str,
    text: str,
    image: bytes | None,
    key: str | None,
    hosted: bool,
) -> DecisionRequest:
    """Build one request: the text in ``state``, the image in ``images``."""
    body: dict[str, Any] = {"state": {"text": text}}
    if image is not None:
        body["images"] = [png_base64(image)]
    body["questions"] = noul_questions(question)
    url = endpoint(address, _ROUTE + model)
    return DecisionRequest(url, body, headers(key=key, hosted=hosted, image=image is not None))


def _unwrap(reply: Any) -> Any:
    """Return the ``result`` object of a Workers AI reply, else the reply."""
    if isinstance(reply, dict) and isinstance(reply.get("result"), dict):
        return reply["result"]
    return reply


def read_reply(reply: Any) -> float:
    """Return P(yes) from the ``result`` object of the reply."""
    return parse_p_yes(_unwrap(reply))


def reported_model(reply: Any) -> str | None:
    """Return the model name the reply reports, or ``None``."""
    model = _unwrap(reply).get("model") if isinstance(_unwrap(reply), dict) else None
    return model if isinstance(model, str) else None
