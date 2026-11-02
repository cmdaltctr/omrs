"""Request builders and HTTP clients for the two image arms (design D1, D5, D7).

Local arm: llama-server ``/v1/systemone`` with an ``images`` list.
Hosted arm: TypeSafe ``/v1/systemone`` with the image in the ``assets`` map and the
``TypeSafe-Danger-Zone-Images: true`` header. The key is read from
``TYPESAFE_API_KEY`` and never appears in a message, a log line or an output file.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any

HEAD_CHARACTERS = 2000
QUESTION_ID = "fidelity"
HOSTED_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
RETRY_STATUS = {429, 500, 502, 503, 504, 529}
ATTEMPTS = 3
#: How llama-server b11941 takes an image in the ``images`` list (smoke test, task 2.1).
LOCAL_IMAGE_ENCODING = "data_url"


def text_head(text: str) -> str:
    """Return the first 2,000 characters of the page text (no other cleaning)."""
    return text[:HEAD_CHARACTERS]


def noul_question(question: str) -> dict:
    """One noul question; its options are no and yes."""
    return {QUESTION_ID: {"type": "noul", "instructions": question}}


def encode_local_image(png: bytes, encoding: str = LOCAL_IMAGE_ENCODING) -> str:
    """Encode a PNG for the llama-server images list."""
    data = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{data}" if encoding == "data_url" else data


def build_local_body(question: str, text: str, png: bytes, encoding: str = LOCAL_IMAGE_ENCODING) -> dict:
    """Build the llama-server request: text head in state, the page image in images."""
    return {
        "model": "clef-flash",
        "state": {"text": text_head(text)},
        "images": [encode_local_image(png, encoding)],
        "questions": noul_question(question),
    }


def placeholder(doc_id: str, page: int) -> str:
    """A stable per-image UUID placeholder for the hosted assets map."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"omrs-exp43/{doc_id}/{page}"))


def build_hosted_body(
    question: str, text: str, png: bytes, model: str, image_id: str
) -> dict:
    """Build the TypeSafe request: the placeholder and text head in state, PNG in assets."""
    return {
        "model": model,
        "state": {"page_image": image_id, "text": text_head(text)},
        "assets": {
            image_id: {
                "type": "image",
                "format": "png",
                "data_base64": base64.b64encode(png).decode("ascii"),
            }
        },
        "questions": noul_question(question),
    }


def _detail(error: urllib.error.HTTPError, secret: str | None) -> str:
    """Return a short error detail with any secret removed."""
    try:
        text = error.read().decode("utf-8", "replace")[:300]
    except OSError:
        text = ""
    return text.replace(secret, "<redacted>") if secret else text


def post(
    url: str,
    body: dict,
    headers: dict[str, str],
    *,
    secret: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
    timeout: float = 300,
) -> dict:
    """POST JSON with retries on rate limits, overload and network errors."""
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310
        url, data, {"Content-Type": "application/json", **headers}
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(ATTEMPTS):
        try:
            with opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUS or attempt == ATTEMPTS - 1:
                raise RuntimeError(f"HTTP {error.code}: {_detail(error, secret)}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == ATTEMPTS - 1:
                raise RuntimeError("request failed: network error") from None
        sleep(2**attempt)
    raise AssertionError("unreachable")


def parse_noul(reply: dict) -> float:
    """Return P(yes) from a systemone reply, checking its bounds."""
    value = reply["answers"][QUESTION_ID]["noul"]
    if not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError("noul score outside probability bounds")
    return float(value)


class LocalClient:
    """Score one page on the local llama-server."""

    def __init__(self, base_url: str, question: str, send: Callable[..., dict] = post) -> None:
        self.url = base_url.rstrip("/") + "/v1/systemone"
        self.question = question
        self.send = send

    def score(self, text: str, png: bytes, encoding: str = LOCAL_IMAGE_ENCODING) -> dict:
        """Return P(yes), wall seconds and token usage when the server reports it."""
        start = time.perf_counter()
        reply = self.send(self.url, build_local_body(self.question, text, png, encoding), {})
        usage = reply.get("usage") or {}
        return {
            "p_yes": parse_noul(reply),
            # The server reports the model path; keep the file name (no home folder).
            "model": str(reply.get("model", "")).replace("\\", "/").rsplit("/", 1)[-1],
            "input_tokens": usage.get("input_tokens"),
            "seconds": time.perf_counter() - start,
        }


class HostedClient:
    """Score one page on hosted Jev; the key comes only from the environment."""

    def __init__(
        self,
        question: str,
        model: str,
        send: Callable[..., dict] = post,
        endpoint: str = HOSTED_ENDPOINT,
    ) -> None:
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise RuntimeError("TYPESAFE_API_KEY is not set")
        self._key = key
        self.question = question
        self.model = model
        self.send = send
        self.endpoint = endpoint

    def __repr__(self) -> str:
        return f"HostedClient(model={self.model!r})"

    def score(self, text: str, png: bytes, image_id: str) -> dict:
        """Return P(yes), the returned model id, token usage and wall seconds."""
        start = time.perf_counter()
        body = build_hosted_body(self.question, text, png, self.model, image_id)
        headers = {
            "Authorization": f"Bearer {self._key}",
            "TypeSafe-Danger-Zone-Images": "true",
        }
        reply = self.send(self.endpoint, body, headers, secret=self._key)
        return {
            "p_yes": parse_noul(reply),
            "model": reply["model"],
            "input_tokens": reply["usage"]["input_tokens"],
            "output_tokens": reply["usage"]["output_tokens"],
            "seconds": time.perf_counter() - start,
        }


class ModelIdGuard:
    """Stop the run when the returned model id changes (design D7)."""

    def __init__(self, first: str | None = None) -> None:
        self.first = first

    def check(self, model: Any) -> None:
        """Record the first model id; raise if a later one differs."""
        if self.first is None:
            self.first = model
        elif model != self.first:
            raise SystemExit(f"returned model id changed: {self.first} -> {model}: stop")
