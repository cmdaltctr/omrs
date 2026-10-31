"""The dots-mocr-llamacpp OCR engine: dots.mocr on a llama.cpp server it owns.

The engine renders each requested page, asks the server for the layout
JSON, and converts that to Markdown with :mod:`.layout`. Framing,
validation and the capability command belong to the worker core.

Runtime rules (design D2, D5, D7):

- the first parse checks the SHA-256 of the model file and the projector,
  then starts the pinned ``llama-server`` on a free loopback port. Later
  parses reuse it. :mod:`.server` stops it with the worker;
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
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from omrs_ocr_worker_core.engine import WorkerParseError

from . import pins
from .files import sha256_of
from .layout import CONVERTER_VERSION, page_markdown
from .paths import ENGINE_NAME, models_dir, server_log, server_pid_file
from .prompt import MAX_NEW_TOKENS, MIN_LONG_SIDE_PX, PROMPT, RENDER_DPI
from .server import LlamaServer, ServerError, find_binary

logger = logging.getLogger("omrs_ocr_dots_mocr_llamacpp")

CHAT_PATH = "/v1/chat/completions"

#: Seconds the server may take to load the model and report healthy.
START_TIMEOUT_S = 180.0
#: Seconds between health checks.
POLL_INTERVAL_S = 0.5
#: Seconds one page may take (Experiment 41 used the same limit).
REQUEST_TIMEOUT_S = 300.0

_PROVISION_COMMAND = "python3 ocr-workers/provision.py dots-mocr-llamacpp --accept-model-licence"


class DotsMocrLlamacppEngine:
    """dots.mocr on a pinned llama.cpp server, one page at a time."""

    name = ENGINE_NAME
    backend_id = "dots_mocr_llamacpp"
    declared_packages: tuple[str, ...] = (
        "omrs-ocr-worker-core",
        "omrs-ocr-dots-mocr-llamacpp",
        "pypdfium2",
        "pillow",
    )
    pipeline = (
        "dots-mocr-layout",
        f"prompt_layout_all_en+llamacpp-{pins.LLAMA_TAG}+{pins.QUANT}+layout-{CONVERTER_VERSION}",
    )
    model = (pins.MODEL_REPO, pins.MODEL_REVISION)

    def __init__(self) -> None:
        self._server: LlamaServer | None = None

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

    def close(self) -> None:
        """Stop the llama.cpp server if this engine started one."""
        if self._server is not None:
            self._server.stop()

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
            WorkerParseError: If the model files or the server are not usable,
                or the server's reply is an error or not a chat completion.
        """
        url = self._ensure_server() + CHAT_PATH
        image = {"url": "data:image/png;base64," + base64.b64encode(png).decode("ascii")}
        body: dict[str, Any] = {
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
        request = urllib.request.Request(  # noqa: S310 - loopback URL built by the server module
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
        try:
            choice = data["choices"][0]
            return (choice["message"].get("content") or ""), int(data["usage"]["completion_tokens"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise WorkerParseError(
                "server_bad_response", f"the llama-server reply is not a chat completion: {exc!r}"
            ) from exc

    # ── Internals ────────────────────────────────────────────────────

    def _all_pages(self, pdf: Path) -> list[int]:
        """Return every 1-based page number of *pdf*."""
        from omrs_ocr_worker_core.pages import document_page_count

        return list(range(1, document_page_count(pdf) + 1))

    def _ensure_server(self) -> str:
        """Return the server URL; on the first call check the files and start it.

        The model files are hashed once per worker, before the server starts.
        """
        try:
            server = self._server
            if server is None:
                binary = find_binary()
                self._verify_model_files()
                server = LlamaServer(
                    binary,
                    models_dir() / pins.MODEL_FILE.name,
                    models_dir() / pins.PROJECTOR_FILE.name,
                    log_path=server_log(),
                    pid_path=server_pid_file(),
                    start_timeout=START_TIMEOUT_S,
                    poll_interval=POLL_INTERVAL_S,
                )
                server.install_shutdown_hooks()
                self._server = server
            return server.ensure_started()
        except ServerError as exc:
            raise WorkerParseError(exc.code, exc.message) from exc

    def _verify_model_files(self) -> None:
        """Check that each pinned file is present and matches its SHA-256."""
        folder = models_dir()
        for pinned in pins.MODEL_FILES:
            path = folder / pinned.name
            if not path.is_file():
                raise WorkerParseError(
                    "model_missing",
                    f"{pinned.name} is missing from {folder}; run `{_PROVISION_COMMAND}`",
                )
            if sha256_of(path) != pinned.sha256:
                raise WorkerParseError(
                    "model_changed",
                    f"{pinned.name} in {folder} no longer matches its pinned SHA-256; "
                    f"run `{_PROVISION_COMMAND}` again",
                )


#: The object the ``omrs.ocr_engine`` entry point names.
ENGINE = DotsMocrLlamacppEngine()
