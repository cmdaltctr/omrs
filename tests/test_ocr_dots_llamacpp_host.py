"""The host checks the dots-mocr-llamacpp model files (change dots-mocr-llamacpp-backend, 2b.5).

The engine keeps no hash check at parse time (design D2). The host hashes both
declared model files before it starts the server. These tests build a workers
folder that holds the engine's real ``pyproject.toml`` (its runtime block) and
a fake ``llama-server`` at the declared path. Only the two pinned hashes are
replaced, with the hashes of two small stand-in files.
"""

from __future__ import annotations

import hashlib
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.llamacpp.harness import FakeRuntime
from tests.fixtures.ocr_worker.runtime_engine import OcrRuntimeHarness, TestEngine

from omrs.integrations.llamacpp_runtime import process

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_MANIFEST = REPO_ROOT / "ocr-workers/engines/dots-mocr-llamacpp/pyproject.toml"
NAME = "dots-mocr-llamacpp"
FILES = {"dots-mocr-Q8_0.gguf": b"stand-in model", "dots-mocr-mmproj-bf16.gguf": b"stand-in proj"}


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[OcrRuntimeHarness]:
    for name in ("OMRS_OCR_MODEL_CACHE", "OMRS_OCR_RUNTIME_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(process, "HEALTH_POLL_SECONDS", 0.05)
    env = OcrRuntimeHarness(tmp_path)
    try:
        yield env
    finally:
        env.cleanup()


def _dots_engine(harness: OcrRuntimeHarness) -> TestEngine:
    """Return the engine folder: the real runtime block, stand-in model files, a fake server."""
    engine = harness.engine(NAME, runtime=False)
    text = REAL_MANIFEST.read_text(encoding="utf-8")
    block = tomllib.loads(text)["tool"]["omrs-ocr"]["runtime"]
    cache = engine.folder / ".model-cache"
    models = cache / "models"
    models.mkdir(parents=True)
    for pinned in block["files"]:
        name = Path(pinned["path"]).name
        (models / name).write_bytes(FILES[name])
        text = text.replace(pinned["sha256"], hashlib.sha256(FILES[name]).hexdigest())
    (engine.folder / "pyproject.toml").write_text(text, encoding="utf-8")
    fake = FakeRuntime(cache, "llama.cpp/llama-b11941")
    (fake.logs / "llama.cpp").mkdir()  # the start log of a nested name
    fake.set_env(FAKE_LLAMA_REQUESTS=str(fake.logs / "requests.txt"))
    engine.fake = fake
    return engine


@pytest.mark.parametrize("name", sorted(FILES))
def test_a_changed_model_file_makes_the_route_unavailable_and_the_fallback_parses(
    harness: OcrRuntimeHarness, effective_settings: Any, name: str
) -> None:
    """A file whose hash differs stops the start; the reason names it; the fallback parses."""
    primary = _dots_engine(harness)
    fallback = harness.engine("fallback")
    routes = harness.pool().routes(harness.settings(effective_settings, NAME, "fallback"))
    (primary.folder / ".model-cache" / "models" / name).write_bytes(b"changed after provisioning")
    pdf = harness.pdf("a.pdf")

    with pytest.raises(Exception) as caught:  # noqa: PT011 - the type is the subject
        routes.primary.lease.join()
    assert getattr(caught.value, "reason", None) == "file-changed"
    assert name in str(caught.value)

    result = routes.select().parse(pdf, timeout=20)
    assert f"url={routes.fallback.lease.base_url}\n" in result.markdown
    assert fallback.requests() == [pdf]
    assert primary.requests() == [] and primary.fake.starts() == []


def test_unchanged_model_files_let_the_dots_route_serve(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    """The same folder with intact files starts the fake server and parses."""
    primary = _dots_engine(harness)
    routes = harness.pool().routes(harness.settings(effective_settings, NAME))
    pdf = harness.pdf("a.pdf")

    result = routes.select().parse(pdf, timeout=20)

    assert f"url={routes.primary.lease.base_url}\n" in result.markdown
    assert primary.requests() == [pdf]
    assert len(primary.fake.starts()) == 1
