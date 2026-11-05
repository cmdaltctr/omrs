"""TypeSafe (hosted Jev) decision model: ``POST /v1/systemone`` (design D2).

Experiment 43 made a recorded live request of this shape. The page image goes
in the ``assets`` map under a placeholder id that ``state.page_image`` names,
and the request carries ``TypeSafe-Danger-Zone-Images: true``. The address is
``https://api.typesafe.ai``. The key goes as a bearer token.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from .base import DecisionRequest, endpoint, headers, noul_questions, parse_p_yes, png_base64
from .base import reported_model as reported_model

NOT_YET_TESTED = False
#: A hosted model: the 8-bit rule is for models on this machine.
LOCAL_RUNTIME = False


def _placeholder(image: bytes) -> str:
    """Return a stable placeholder id for *image*."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "omrs-page/" + hashlib.sha256(image).hexdigest()))


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
    """Build one request: the placeholder and text in ``state``, the PNG in ``assets``."""
    body: dict[str, Any] = {"model": model}
    if image is None:
        body["state"] = {"text": text}
    else:
        image_id = _placeholder(image)
        body["state"] = {"page_image": image_id, "text": text}
        body["assets"] = {
            image_id: {"type": "image", "format": "png", "data_base64": png_base64(image)}
        }
    body["questions"] = noul_questions(question)
    return DecisionRequest(
        endpoint(address), body, headers(key=key, hosted=hosted, image=image is not None)
    )


def read_reply(reply: Any) -> float:
    """Return P(yes) from the reply."""
    return parse_p_yes(reply)
