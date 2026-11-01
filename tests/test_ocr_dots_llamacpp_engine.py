"""The dots-mocr-llamacpp engine (change dots-mocr-llamacpp-backend, tasks 2.5 and 2b.4).

The engine is a client of a ``llama-server`` that the host runs. These tests
start the shared fake server of ``tests/fixtures/llamacpp`` through the host's
runtime manager and give its address to the engine in
``OMRS_OCR_RUNTIME_URL``, as the host does for a real worker. No GPU, model or
network is needed. Page rendering needs pypdfium2, which the main environment
does not hold, so tests replace ``render_page`` or give it a fake ``pypdfium2``
module. The real render and the real server run in the provisioned smoke test.
"""

from __future__ import annotations

import base64
import json
import logging
import subprocess
import sys
import types
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pypdf import PdfWriter
from tests.fixtures.llamacpp.harness import FakeRuntime
from tests.fixtures.ocr_worker.dots_llamacpp import (
    ENGINE_DIR,
    PACKAGE,
    WORKERS,
    engine_modules,
)

from omrs.integrations.llamacpp_runtime import process
from omrs.integrations.llamacpp_runtime.manager import RuntimeManager

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "experiments" / "34-worker-sample-review-2026-09-19" / "output" / "dots_mocr"
PNG = b"\x89PNG-fake-page-bytes"
URL_ENV = "OMRS_OCR_RUNTIME_URL"


class Env:
    """The loaded modules, the engine under test and the fake server the host runs."""

    def __init__(
        self, load: Any, folder: Path, monkeypatch: pytest.MonkeyPatch, manager: RuntimeManager
    ) -> None:
        self.engine_mod: ModuleType = load("engine")
        self.pins: ModuleType = load("pins")
        self.prompt: ModuleType = load("prompt")
        self.fake = FakeRuntime(folder)
        self.requests = self.fake.logs / "requests.txt"
        self.engine = self.engine_mod.DotsMocrLlamacppEngine()
        self._monkeypatch = monkeypatch
        self._manager = manager

    def serve(self, **fake_values: object) -> str:
        """Start the fake server through the manager and give its URL to the engine.

        Args:
            **fake_values: ``FAKE_LLAMA_*`` settings for the fake (the text it
                answers, the token count, an error status).

        Returns:
            The server address, which is also set as ``OMRS_OCR_RUNTIME_URL``.
        """
        self.fake.set_env(FAKE_LLAMA_REQUESTS=str(self.requests), **fake_values)
        url = self._manager.lease(self.fake.ocr()).join()
        self._monkeypatch.setenv(URL_ENV, url)
        return url

    def request_bodies(self) -> list[dict[str, Any]]:
        """Return the JSON body of each chat request the fake received."""
        if not self.requests.exists():
            return []
        return [json.loads(line) for line in self.requests.read_text().splitlines()]


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Env]:
    """An engine and a fake llama-server that the host's manager can start."""
    monkeypatch.delenv(URL_ENV, raising=False)
    monkeypatch.setenv("OMRS_OCR_MODEL_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(process, "HEALTH_POLL_SECONDS", 0.05)
    manager = RuntimeManager(tmp_path / "state", exit_hook=False)
    with engine_modules(monkeypatch) as load:
        e = Env(load, tmp_path, monkeypatch, manager)
        monkeypatch.setattr(e.engine, "render_page", lambda _pdf, _page: PNG)
        try:
            yield e
        finally:
            manager.close()
            e.fake.kill_all()


@pytest.fixture
def pdf(tmp_path: Path) -> Path:
    """A two-page PDF."""
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    writer.add_blank_page(612, 792)
    path = tmp_path / "doc.pdf"
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def _raw(doc: str, page: int) -> str:
    return (FIXTURES / doc / f"p{page:03d}.raw.txt").read_text(encoding="utf-8")


# ── parse and the D5 request ───────────────────────────────────────────────


def test_parse_sends_the_d5_request_and_converts_the_layout(env: Env, pdf: Path) -> None:
    """The request body matches design D5; the reply becomes Markdown."""
    env.serve(FAKE_LLAMA_CONTENT=_raw("eq01", 11), FAKE_LLAMA_TOKENS=1937)
    pages = env.engine.parse(pdf, [2])
    assert len(pages) == 1 and pages[0].count("$$") == 8
    (body,) = env.request_bodies()
    assert body["temperature"] == 0 and body["max_tokens"] == 8192 and body["stream"] is False
    assert set(body) == {"messages", "temperature", "max_tokens", "stream"}
    (message,) = body["messages"]
    image, text = message["content"]
    assert message["role"] == "user"
    assert image["type"] == "image_url" and text == {"type": "text", "text": env.prompt.PROMPT}
    prefix = "data:image/png;base64,"
    assert image["image_url"]["url"].startswith(prefix)
    assert base64.b64decode(image["image_url"]["url"][len(prefix) :]) == PNG


def test_a_whole_document_request_parses_every_page_on_the_same_server(env: Env, pdf: Path) -> None:
    """``pages=None`` parses both pages; a second call sends to the same server."""
    env.serve(FAKE_LLAMA_CONTENT=_raw("eq01", 11))
    assert len(env.engine.parse(pdf, None)) == 2
    assert len(env.engine.parse(pdf, [1])) == 1
    assert len(env.fake.starts()) == 1
    assert len(env.request_bodies()) == 3


def test_a_capped_page_is_empty_and_the_reason_is_logged(
    env: Env, pdf: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A reply at the token cap gives "" and logs the reason."""
    env.serve(FAKE_LLAMA_CONTENT=_raw("eq01", 11), FAKE_LLAMA_TOKENS=8192)
    with caplog.at_level(logging.WARNING, logger="omrs_ocr_dots_mocr_llamacpp"):
        assert env.engine.parse(pdf, [1]) == [""]
    assert "token_cap" in caplog.text and "doc.pdf" in caplog.text


def test_an_unparsable_reply_gives_an_empty_page(env: Env, pdf: Path) -> None:
    """Text that is not a layout object gives "" like the PyTorch backend."""
    env.serve(FAKE_LLAMA_CONTENT="not json")
    assert env.engine.parse(pdf, [1]) == [""]


@pytest.mark.parametrize(
    ("fake_values", "code", "needle"),
    [
        ({"FAKE_LLAMA_STATUS": 500}, "server_error", "500"),
        ({"FAKE_LLAMA_BAD_JSON": 1}, "server_bad_response", "JSON"),
    ],
)
def test_server_failures_become_parse_errors(
    env: Env, pdf: Path, fake_values: dict[str, object], code: str, needle: str
) -> None:
    """An HTTP error or a body that is not JSON gives a coded parse error."""
    env.serve(**fake_values)
    with pytest.raises(env.engine_mod.WorkerParseError) as excinfo:
        env.engine.parse(pdf, [1])
    assert excinfo.value.code == code and needle in excinfo.value.message


def test_each_page_goes_to_the_chat_completions_path_of_the_runtime(
    env: Env, pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The request URL is the runtime address plus ``/v1/chat/completions``."""
    url = env.serve(FAKE_LLAMA_CONTENT=_raw("eq01", 11))
    seen: list[str] = []
    real = urllib.request.Request

    def spy(target: str, *args: Any, **kwargs: Any) -> urllib.request.Request:
        seen.append(target)
        return real(target, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "Request", spy)
    env.engine.parse(pdf, [1])
    assert seen == [f"{url}/v1/chat/completions"]


def test_an_unreachable_server_gives_a_parse_error(
    env: Env, pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An address where nothing listens gives ``server_unreachable``."""
    monkeypatch.setenv(URL_ENV, "http://127.0.0.1:1")
    with pytest.raises(env.engine_mod.WorkerParseError) as excinfo:
        env.engine.parse(pdf, [1])
    assert excinfo.value.code == "server_unreachable"


# ── The runtime address (design D2) ────────────────────────────────────────


def test_a_missing_address_gives_a_parse_error_that_names_the_variable(env: Env, pdf: Path) -> None:
    """With no ``OMRS_OCR_RUNTIME_URL`` a parse fails and sends nothing."""
    env.serve()
    env._monkeypatch.delenv(URL_ENV)
    with pytest.raises(env.engine_mod.WorkerParseError) as excinfo:
        env.engine.parse(pdf, [1])
    assert excinfo.value.code == "runtime_url_missing"
    assert URL_ENV in excinfo.value.message
    assert env.request_bodies() == []


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "https://127.0.0.1:8080",
        "http://example.com:8080",
        "http://192.168.1.5:8080",
        "http://user@127.0.0.1:8080",
        "http://127.0.0.1:99999",
        "http://127.0.0.1:0",
        "ftp://127.0.0.1:21",
        "not a url",
    ],
)
def test_an_address_that_is_not_loopback_http_is_refused_by_name(
    env: Env, pdf: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Only an ``http`` address on this computer is accepted; the error names the variable."""
    env.serve()
    monkeypatch.setenv(URL_ENV, value)
    with pytest.raises(env.engine_mod.WorkerParseError) as excinfo:
        env.engine.parse(pdf, [1])
    assert excinfo.value.code in {"runtime_url_missing", "runtime_url_invalid"}
    assert URL_ENV in excinfo.value.message
    assert env.request_bodies() == []


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
def test_each_loopback_host_form_is_accepted(env: Env, host: str) -> None:
    """The three loopback spellings of the host rule pass the address check."""
    url = env.engine_mod.runtime_base_url({URL_ENV: f"http://{host}:8081/"})
    assert url == f"http://{host}:8081"


def test_the_engine_starts_no_process(env: Env, pdf: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A parse works while ``subprocess.Popen`` is made to fail."""
    env.serve(FAKE_LLAMA_CONTENT=_raw("eq01", 11))

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the engine started a process")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    assert len(env.engine.parse(pdf, [1])) == 1


def test_no_engine_module_imports_subprocess() -> None:
    """The engine package holds no ``subprocess`` import and no server module."""
    package = ENGINE_DIR / "src" / PACKAGE
    assert not (package / "server.py").exists()
    for source in sorted(package.glob("*.py")):
        text = source.read_text(encoding="utf-8")
        assert "import subprocess" not in text, source.name
        assert "from subprocess" not in text, source.name


def test_no_leftover_server_helper_remains_in_the_engine_or_the_tests() -> None:
    """The names of the old worker-owned server are gone from the engine and the tests."""
    # Built in pieces so a grep for the old names does not match this test.
    needles = (
        "server_pid" + "_file",
        "Llama" + "Server",
        "install_shutdown" + "_hooks",
        "def server" + "_log",
    )
    here = Path(__file__).resolve()
    roots = [ENGINE_DIR / "src", ENGINE_DIR / "smoke_test.py", REPO_ROOT / "tests"]
    for root in roots:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for source in files:
            if source == here or "__pycache__" in source.parts:
                continue
            text = source.read_text(encoding="utf-8")
            for needle in needles:
                assert needle not in text, f"{needle} found in {source.name}"


# ── Identity (design D7) ───────────────────────────────────────────────────


def test_the_fingerprint_fields_match_d7(env: Env) -> None:
    """The contract fields name the backend, the build, the quantisation and the model."""
    engine = env.engine_mod.ENGINE
    assert engine.name == "dots-mocr-llamacpp"
    assert engine.backend_id == "dots_mocr_llamacpp"
    assert engine.model == ("cmdaltctr/omrs-ocr-gguf-converted", env.pins.MODEL_REVISION)
    assert engine.pipeline == (
        "dots-mocr-layout",
        "prompt_layout_all_en+llamacpp-b11941+q8_0+layout-1",
    )
    assert engine.declared_packages == (
        "omrs-ocr-worker-core",
        "omrs-ocr-dots-mocr-llamacpp",
        "pypdfium2",
        "pillow",
    )


def test_the_engine_satisfies_the_worker_core_contract(env: Env) -> None:
    """The worker core accepts the engine object and builds its capability payload."""
    import importlib

    core = importlib.import_module("omrs_ocr_worker_core.engine")
    capabilities = importlib.import_module("omrs_ocr_worker_core.capabilities")
    core.validate_engine(env.engine_mod.ENGINE)
    payload = capabilities.fingerprint_payload(env.engine_mod.ENGINE)
    assert payload["backend_id"] == "dots_mocr_llamacpp"
    assert payload["pipeline"] == {
        "identity": "dots-mocr-layout",
        "revision": "prompt_layout_all_en+llamacpp-b11941+q8_0+layout-1",
    }


def test_importing_the_engine_loads_no_pytorch_module() -> None:
    """A fresh interpreter that imports the engine holds no torch-family module."""
    code = (
        "import sys\n"
        f"sys.path[:0] = [{str(WORKERS / 'core' / 'src')!r}, {str(ENGINE_DIR / 'src')!r}]\n"
        f"import {PACKAGE}.engine\n"
        "banned = {'torch', 'torchvision', 'transformers', 'accelerate', 'qwen_vl_utils',\n"
        "          'huggingface_hub'}\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in banned))\n"
    )
    out = subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"


def test_the_engine_never_imports_the_fetch_step(env: Env) -> None:
    """A parse cannot download: the engine module does not import ``fetch``."""
    source = (ENGINE_DIR / "src" / PACKAGE / "engine.py").read_text(encoding="utf-8")
    assert "fetch" not in source.replace("fetch step", "")


# ── Rendering, with a fake pypdfium2 ───────────────────────────────────────


def _fake_pdfium(size: tuple[float, float], scales: list[float]) -> ModuleType:
    class Image:
        def __init__(self) -> None:
            self.mode = "RGBA"

        def convert(self, mode: str) -> Image:
            self.mode = mode
            return self

        def save(self, handle: Any, format: str) -> None:  # noqa: A002 - PIL signature
            handle.write(f"{format}:{self.mode}".encode())

    class Bitmap:
        def to_pil(self) -> Image:
            return Image()

    class Page:
        def get_size(self) -> tuple[float, float]:
            return size

        def render(self, scale: float) -> Bitmap:
            scales.append(scale)
            return Bitmap()

    class Document:
        def __init__(self, _path: str) -> None:
            self.closed = False

        def __getitem__(self, _index: int) -> Page:
            return Page()

        def close(self) -> None:
            self.closed = True

    module = types.ModuleType("pypdfium2")
    module.PdfDocument = Document  # type: ignore[attr-defined]
    return module


@pytest.mark.parametrize(
    ("size", "expected"),
    [((612.0, 792.0), 200 / 72), ((200.0, 300.0), 1600 / 300)],
)
def test_render_page_uses_the_pytorch_scale_and_returns_rgb_png(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, size: tuple[float, float], expected: float
) -> None:
    """Scale is max(200 dpi, long side 1600 px); the image is RGB and goes out as PNG."""
    scales: list[float] = []
    monkeypatch.setitem(sys.modules, "pypdfium2", _fake_pdfium(size, scales))
    monkeypatch.setenv("OMRS_OCR_MODEL_CACHE", str(tmp_path))
    with engine_modules(monkeypatch) as load:
        engine = load("engine").DotsMocrLlamacppEngine()
        data = engine.render_page(tmp_path / "x.pdf", 1)
    assert scales == [pytest.approx(expected)]
    assert data == b"PNG:RGB"
