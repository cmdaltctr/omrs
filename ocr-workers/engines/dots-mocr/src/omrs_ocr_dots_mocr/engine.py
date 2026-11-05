"""The dots-mocr OCR engine: dots.mocr as a client of a llama.cpp server.

The engine renders each requested page, asks the server for the layout
JSON, and converts that to Markdown with :mod:`.layout`. Framing,
validation and the capability command belong to the worker core.

Runtime rules (design D2, D5, D7):

- the engine starts no process. OMRS runs the pinned ``llama-server`` that
  ``pyproject.toml`` declares, checks the build and the SHA-256 of both model
  files before each start, and gives the worker the address in
  ``OMRS_OCR_RUNTIME_URL``. A missing or non-loopback address is a parse
  error that names the variable;
- a page is rendered with pypdfium2 at :data:`RENDER_DPI`, raised so the
  long side reaches :data:`MIN_LONG_SIDE_PX`, and sent as a PNG;
- a page whose reply reaches the token cap, or whose layout JSON does not
  parse, gives empty Markdown, and the reason goes to the log;
- a parse never downloads anything. The download step lives in another
  module that this one does not import.

pypdfium2 and Pillow are imported inside :meth:`render_page`, so the
capability command and the tests never import them.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from omrs_ocr_worker_core.engine import WorkerParseError

from . import pins
from .layout import CONVERTER_VERSION, page_markdown
from .paths import ENGINE_NAME
from .prompt import MAX_NEW_TOKENS, MIN_LONG_SIDE_PX, PROMPT, RENDER_DPI

logger = logging.getLogger("omrs_ocr_dots_mocr")

CHAT_PATH = "/v1/chat/completions"

#: The model name in each request. ``llama-server`` with one model ignores it;
#: Ollama and mlx-vlm refuse a request without one.
REQUEST_MODEL = "dots-mocr"

#: Seconds one page may take (Experiment 41 used the same limit).
REQUEST_TIMEOUT_S = 300.0

#: The variable in which OMRS gives the worker the address of its runtime.
RUNTIME_URL_ENV = "OMRS_OCR_RUNTIME_URL"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def completion_of(data: Any) -> tuple[str, int]:
    """Return the text and completion token count of a llama-server chat reply.

    Raises:
        WorkerParseError: ``server_bad_response`` when *data* is not a chat
            completion, for example a null message or non-text content.
    """
    try:
        content = data["choices"][0]["message"]["content"]
        tokens = int(data["usage"]["completion_tokens"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise WorkerParseError(
            "server_bad_response", f"the llama-server reply is not a chat completion: {exc!r}"
        ) from exc
    if content is not None and not isinstance(content, str):
        raise WorkerParseError("server_bad_response", "the llama-server reply content is not text")
    return content or "", tokens


def runtime_base_url(environ: Mapping[str, str] | None = None) -> str:
    """Return the llama-server address OMRS gave this worker.

    Args:
        environ: The environment to read; the process environment by default.

    Returns:
        An ``http://host:port`` address without a path.

    Raises:
        WorkerParseError: If the variable is missing, or its value is not an
            ``http`` address on this computer. The message names the variable.
    """
    value = (os.environ if environ is None else environ).get(RUNTIME_URL_ENV, "").strip()
    if not value:
        raise WorkerParseError(
            "runtime_url_missing",
            f"{RUNTIME_URL_ENV} is not set; OMRS gives the worker the address of its llama-server",
        )
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        port = 80 if parts.port is None else parts.port
    except ValueError:
        raise WorkerParseError(
            "runtime_url_invalid",
            f"{RUNTIME_URL_ENV} must be an http address on this computer, not {value!r}",
        ) from None
    if (
        parts.scheme != "http"
        or host not in _LOOPBACK_HOSTS
        or parts.username is not None
        or not 1 <= port <= 65535
    ):
        raise WorkerParseError(
            "runtime_url_invalid",
            f"{RUNTIME_URL_ENV} must be an http address on this computer, not {value!r}",
        )
    return f"http://{parts.netloc}"


class DotsMocrLlamacppEngine:
    """dots.mocr through a llama.cpp server that OMRS runs, one page at a time."""

    name = ENGINE_NAME
    backend_id = "dots_mocr_llamacpp"
    declared_packages: tuple[str, ...] = (
        "omrs-ocr-worker-core",
        "omrs-ocr-dots-mocr",
        "pypdfium2",
        "pillow",
    )
    pipeline = (
        "dots-mocr-layout",
        f"prompt_layout_all_en+llamacpp-{pins.LLAMA_TAG}+{pins.QUANT}+layout-{CONVERTER_VERSION}",
    )
    model = (pins.MODEL_REPO, pins.MODEL_REVISION)

    # ── Engine contract ──────────────────────────────────────────────

    def parse(self, pdf: Path, pages: Sequence[int] | None) -> list[str]:
        """Return one Markdown string per parsed page.

        A page that reaches the token cap, or whose layout JSON does not
        parse, yields ``""``; the reason goes to the log.
        """
        numbers = list(pages) if pages is not None else self._all_pages(pdf)
        out: list[str] = []
        for number in numbers:
            png = self.render_page(pdf, number)
            raw, new_tokens = self.generate(png)
            markdown, reason = page_markdown(raw, hit_token_cap=new_tokens >= MAX_NEW_TOKENS)
            if reason is not None:
                logger.warning("page %d of %s gives no text: %s", number, pdf.name, reason)
            out.append(markdown)
        return out

    # ── Seams (tests stub these) ─────────────────────────────────────

    def render_page(self, pdf: Path, page: int) -> bytes:
        """Render one 1-based page to PNG bytes (lossless RGB pixels)."""
        import pypdfium2 as pdfium  # engine environment only

        document = pdfium.PdfDocument(str(pdf))
        try:
            page_obj = document[page - 1]
            scale = max(RENDER_DPI / 72, MIN_LONG_SIDE_PX / max(page_obj.get_size()))
            image = page_obj.render(scale=scale).to_pil().convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()
        finally:
            document.close()

    def generate(self, png: bytes) -> tuple[str, int]:
        """Ask the server about one page image; return ``(raw text, new tokens)``.

        Raises:
            WorkerParseError: If the runtime address is missing or not on this
                computer, or the server's reply is an error or not a chat
                completion.
        """
        url = runtime_base_url() + CHAT_PATH
        image = {"url": "data:image/png;base64," + base64.b64encode(png).decode("ascii")}
        body: dict[str, Any] = {
            "model": REQUEST_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": image},
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": MAX_NEW_TOKENS,
            "stream": False,
        }
        request = urllib.request.Request(  # noqa: S310 - loopback address checked by runtime_base_url
            url, json.dumps(body).encode(), {"Content-Type": "application/json"}
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # ignore proxies
        try:
            with opener.open(request, timeout=REQUEST_TIMEOUT_S) as response:
                data = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read(300).decode("utf-8", "replace")
            raise WorkerParseError(
                "server_error", f"llama-server answered HTTP {exc.code}: {detail}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise WorkerParseError(
                "server_unreachable", f"cannot reach llama-server: {exc}"
            ) from exc
        except ValueError as exc:
            raise WorkerParseError(
                "server_bad_response", f"the llama-server reply was not JSON: {exc}"
            ) from exc
        return completion_of(data)

    # ── Internals ────────────────────────────────────────────────────

    def _all_pages(self, pdf: Path) -> list[int]:
        """Return every 1-based page number of *pdf*."""
        from omrs_ocr_worker_core.pages import document_page_count

        return list(range(1, document_page_count(pdf) + 1))


#: The object the ``omrs.ocr_engine`` entry point names.
ENGINE = DotsMocrLlamacppEngine()
