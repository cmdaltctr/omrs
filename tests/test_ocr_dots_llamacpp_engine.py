"""The dots-mocr-llamacpp engine (change dots-mocr-llamacpp-backend, task 2.5).

The engine talks to a fake ``llama-server`` script, so no GPU, model or
network is needed. Page rendering needs pypdfium2, which the main
environment does not hold, so tests replace ``render_page`` or give it a
fake ``pypdfium2`` module. The real render and the real server run in the
provisioned smoke test.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import subprocess
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pypdf import PdfWriter
from tests.fixtures.ocr_worker.dots_llamacpp import (
    ENGINE_DIR,
    PACKAGE,
    WORKERS,
    engine_modules,
    make_fake_binary,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "experiments" / "34-worker-sample-review-2026-09-19" / "output" / "dots_mocr"
PNG = b"\x89PNG-fake-page-bytes"
MODEL_BYTES = b"model"
PROJECTOR_BYTES = b"projector"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Env:
    """The loaded modules, the engine under test and the files the fake writes."""

    def __init__(self, load: Any, folder: Path) -> None:
        self.engine_mod: ModuleType = load("engine")
        self.pins: ModuleType = load("pins")
        self.paths: ModuleType = load("paths")
        self.prompt: ModuleType = load("prompt")
        self.folder = folder
        self.requests = folder / "requests.txt"
        self.starts = folder / "starts.txt"
        self.engine = self.engine_mod.DotsMocrLlamacppEngine()

    def request_bodies(self) -> list[dict[str, Any]]:
        """Return the JSON body of each chat request the fake received."""
        if not self.requests.exists():
            return []
        return [json.loads(line) for line in self.requests.read_text().splitlines()]

    def start_count(self) -> int:
        """Return how many times the fake server started."""
        return len(self.starts.read_text().splitlines()) if self.starts.exists() else 0


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Env]:
    """An engine whose cache holds tiny model files and a fake llama-server."""
    cache = tmp_path / "cache"
    monkeypatch.setenv("OMRS_OCR_MODEL_CACHE", str(cache))
    monkeypatch.setenv("FAKE_LLAMA_STARTS", str(tmp_path / "starts.txt"))
    monkeypatch.setenv("FAKE_LLAMA_REQUESTS", str(tmp_path / "requests.txt"))
    with engine_modules(monkeypatch) as load:
        e = Env(load, tmp_path)
        files = (
            e.pins.PinnedFile("dots-mocr-Q8_0.gguf", _sha(MODEL_BYTES)),
            e.pins.PinnedFile("dots-mocr-mmproj-bf16.gguf", _sha(PROJECTOR_BYTES)),
        )
        monkeypatch.setattr(e.pins, "MODEL_FILES", files)
        models = e.paths.models_dir()
        models.mkdir(parents=True)
        (models / files[0].name).write_bytes(MODEL_BYTES)
        (models / files[1].name).write_bytes(PROJECTOR_BYTES)
        llama = e.paths.llama_dir()
        llama.mkdir(parents=True)
        make_fake_binary(llama)
        monkeypatch.setattr(e.engine_mod, "POLL_INTERVAL_S", 0.05)
        monkeypatch.setattr(e.engine, "render_page", lambda _pdf, _page: PNG)
        yield e
        e.engine.close()


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


def test_parse_sends_the_d5_request_and_converts_the_layout(
    env: Env, pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The request body matches design D5; the reply becomes Markdown."""
    monkeypatch.setenv("FAKE_LLAMA_CONTENT", _raw("eq01", 11))
    monkeypatch.setenv("FAKE_LLAMA_TOKENS", "1937")
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


def test_a_whole_document_request_parses_every_page_with_one_server(
    env: Env, pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``pages=None`` parses both pages; the second call reuses the server."""
    monkeypatch.setenv("FAKE_LLAMA_CONTENT", _raw("eq01", 11))
    assert len(env.engine.parse(pdf, None)) == 2
    assert len(env.engine.parse(pdf, [1])) == 1
    assert env.start_count() == 1
    assert len(env.request_bodies()) == 3


def test_a_capped_page_is_empty_and_the_reason_is_logged(
    env: Env, pdf: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A reply at the token cap gives "" and logs the reason."""
    monkeypatch.setenv("FAKE_LLAMA_CONTENT", _raw("eq01", 11))
    monkeypatch.setenv("FAKE_LLAMA_TOKENS", "8192")
    with caplog.at_level(logging.WARNING, logger="omrs_ocr_dots_mocr_llamacpp"):
        assert env.engine.parse(pdf, [1]) == [""]
    assert "token_cap" in caplog.text and "doc.pdf" in caplog.text


def test_an_unparsable_reply_gives_an_empty_page(
    env: Env, pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Text that is not a layout object gives "" like the PyTorch backend."""
    monkeypatch.setenv("FAKE_LLAMA_CONTENT", "not json")
    assert env.engine.parse(pdf, [1]) == [""]


@pytest.mark.parametrize(
    ("variable", "code", "needle"),
    [
        ("FAKE_LLAMA_STATUS", "server_error", "500"),
        ("FAKE_LLAMA_BAD_JSON", "server_bad_response", "JSON"),
    ],
)
def test_server_failures_become_parse_errors(
    env: Env, pdf: Path, monkeypatch: pytest.MonkeyPatch, variable: str, code: str, needle: str
) -> None:
    """An HTTP error or a body that is not JSON gives a coded parse error."""
    monkeypatch.setenv(variable, "500" if variable == "FAKE_LLAMA_STATUS" else "1")
    with pytest.raises(env.engine_mod.WorkerParseError) as excinfo:
        env.engine.parse(pdf, [1])
    assert excinfo.value.code == code and needle in excinfo.value.message


# ── The model file check ───────────────────────────────────────────────────


def test_a_changed_model_file_names_the_file_and_never_starts_the_server(
    env: Env, pdf: Path
) -> None:
    """A model whose hash differs from its pin stops the parse before the server starts."""
    (env.paths.models_dir() / "dots-mocr-Q8_0.gguf").write_bytes(b"changed")
    with pytest.raises(env.engine_mod.WorkerParseError) as excinfo:
        env.engine.parse(pdf, [1])
    assert excinfo.value.code == "model_changed"
    assert "dots-mocr-Q8_0.gguf" in excinfo.value.message
    assert env.start_count() == 0


def test_a_changed_projector_names_the_projector(env: Env, pdf: Path) -> None:
    """The projector is checked like the model."""
    (env.paths.models_dir() / "dots-mocr-mmproj-bf16.gguf").write_bytes(b"changed")
    with pytest.raises(env.engine_mod.WorkerParseError) as excinfo:
        env.engine.parse(pdf, [1])
    assert "dots-mocr-mmproj-bf16.gguf" in excinfo.value.message
    assert env.start_count() == 0


def test_a_missing_model_file_names_the_file_and_the_provision_command(env: Env, pdf: Path) -> None:
    """A file that is not there gives ``model_missing`` and the provisioning command."""
    (env.paths.models_dir() / "dots-mocr-Q8_0.gguf").unlink()
    with pytest.raises(env.engine_mod.WorkerParseError) as excinfo:
        env.engine.parse(pdf, [1])
    assert excinfo.value.code == "model_missing"
    assert "dots-mocr-Q8_0.gguf" in excinfo.value.message
    assert "provision.py dots-mocr-llamacpp" in excinfo.value.message


def test_a_missing_server_binary_gives_a_parse_error(env: Env, pdf: Path) -> None:
    """The server's own error code reaches the host."""
    (env.paths.llama_dir() / "llama-server").unlink()
    with pytest.raises(env.engine_mod.WorkerParseError) as excinfo:
        env.engine.parse(pdf, [1])
    assert excinfo.value.code == "server_binary_missing"


def test_the_wrong_build_gives_a_parse_error(
    env: Env, pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A server of another build is refused and never starts."""
    monkeypatch.setenv("FAKE_LLAMA_BUILD", "11960")
    with pytest.raises(env.engine_mod.WorkerParseError) as excinfo:
        env.engine.parse(pdf, [1])
    assert excinfo.value.code == "server_build" and "11960" in excinfo.value.message
    assert env.start_count() == 0


def test_the_hash_check_runs_once_per_worker(env: Env, pdf: Path) -> None:
    """After the first good check, later pages do not hash the files again."""
    env.engine.parse(pdf, [1])
    (env.paths.models_dir() / "dots-mocr-Q8_0.gguf").write_bytes(b"changed later")
    assert len(env.engine.parse(pdf, [2])) == 1
    assert env.start_count() == 1


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
