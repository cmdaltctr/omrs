"""Ollama decision model: ``POST /v1/systemone`` (design D2). Not yet tested.

Written from the design D2 facts and tested against fake servers only.
Ollama 0.40.13 answers this route and needs a model name. The image goes as
raw base64 in an ``images`` list, the form of Ollama's own API. Ollama shows
no GGUF header, so the 8-bit rule can check only the model name; name the
model built from the pinned Clef-Flash Q8_0 and projector files.
"""

from __future__ import annotations

from typing import Any

from .base import DecisionRequest, endpoint, headers, noul_questions, parse_p_yes, png_base64
from .base import reported_model as reported_model

NOT_YET_TESTED = True
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
        body["images"] = [png_base64(image)]
    body["questions"] = noul_questions(question)
    return DecisionRequest(
        endpoint(address), body, headers(key=key, hosted=hosted, image=image is not None)
    )


def read_reply(reply: Any) -> float:
    """Return P(yes) from the reply."""
    return parse_p_yes(reply)
