"""llama.cpp decision model: ``llama-server`` ``POST /v1/systemone`` (design D2).

Experiment 43 made a recorded live request of this shape on build b11941.
The page image goes in an ``images`` list as a data URL, which is the form
that build takes. A server started without ``--mmproj`` answers an image
request with HTTP 501, so the smoke test fails with ``projector-not-loaded``.
"""

from __future__ import annotations

from typing import Any

from .base import DecisionRequest, endpoint, headers, noul_questions, parse_p_yes, png_base64
from .base import reported_model as reported_model

#: A live request of this kind passed the smoke test (Experiment 43).
NOT_YET_TESTED = False
#: The model runs on this machine, so the 8-bit rule applies (gotcha 16).
LOCAL_RUNTIME = True


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
    body: dict[str, Any] = {"model": model, "state": {"text": text}}
    if image is not None:
        body["images"] = ["data:image/png;base64," + png_base64(image)]
    body["questions"] = noul_questions(question)
    return DecisionRequest(
        endpoint(address), body, headers(key=key, hosted=hosted, image=image is not None)
    )


def read_reply(reply: Any) -> float:
    """Return P(yes) from the reply."""
    return parse_p_yes(reply)
