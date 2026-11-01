"""Import helper for the dots-mocr-llamacpp engine tests.

The engine package is not installed in the main environment, so each test
module puts the worker core and the engine on ``sys.path`` and unloads
every ``omrs_ocr_*`` module afterwards (see :mod:`.isolation`).
"""

from __future__ import annotations

import hashlib
import importlib
import tomllib
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

import pytest
from tests.fixtures.llamacpp.harness import FakeRuntime
from tests.fixtures.ocr_worker.isolation import isolated_worker_modules

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKERS = REPO_ROOT / "ocr-workers"
ENGINE_DIR = WORKERS / "engines" / "dots-mocr-llamacpp"
PACKAGE = "omrs_ocr_dots_mocr_llamacpp"


@contextmanager
def engine_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Callable[[str], ModuleType]]:
    """Make the engine package importable; yield a loader for its modules.

    Usage::

        with engine_modules(monkeypatch) as load:
            fetch = load("fetch")
    """
    monkeypatch.syspath_prepend(str(WORKERS / "core" / "src"))
    monkeypatch.syspath_prepend(str(ENGINE_DIR / "src"))

    def load(name: str) -> ModuleType:
        return importlib.import_module(f"{PACKAGE}.{name}")

    with isolated_worker_modules():
        yield load


#: Two small files that stand in for the pinned model and projector.
STAND_IN_FILES = {
    "dots-mocr-Q8_0.gguf": b"stand-in model",
    "dots-mocr-mmproj-bf16.gguf": b"stand-in proj",
}


def stand_in_engine(folder: Path) -> FakeRuntime:
    """Fill *folder* as the engine folder the host reads, with a fake server.

    The folder gets the engine's real ``pyproject.toml`` (its runtime block),
    with the two pinned hashes replaced by the hashes of :data:`STAND_IN_FILES`,
    those files in ``.model-cache/models`` and the shared fake ``llama-server``
    at the declared program path.

    Args:
        folder: The engine folder; it must exist.

    Returns:
        The fake server install, with its request record set up.
    """
    text = (ENGINE_DIR / "pyproject.toml").read_text(encoding="utf-8")
    block = tomllib.loads(text)["tool"]["omrs-ocr"]["runtime"]
    cache = folder / ".model-cache"
    models = cache / "models"
    models.mkdir(parents=True)
    for pinned in block["files"]:
        name = Path(pinned["path"]).name
        (models / name).write_bytes(STAND_IN_FILES[name])
        text = text.replace(pinned["sha256"], hashlib.sha256(STAND_IN_FILES[name]).hexdigest())
    (folder / "pyproject.toml").write_text(text, encoding="utf-8")
    program = Path(block["program"])
    fake = FakeRuntime(cache, program.parent.as_posix())
    (fake.logs / program.parent.parent.name).mkdir()  # the start log of a nested name
    fake.set_env(FAKE_LLAMA_REQUESTS=str(fake.logs / "requests.txt"))
    return fake
