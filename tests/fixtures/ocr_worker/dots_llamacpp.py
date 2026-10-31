"""Import helper for the dots-mocr-llamacpp engine tests.

The engine package is not installed in the main environment, so each test
module puts the worker core and the engine on ``sys.path`` and unloads
every ``omrs_ocr_*`` module afterwards (see :mod:`.isolation`).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

import pytest
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


FAKE_SERVER = Path(__file__).with_name("fake_llama_server.py")


def make_fake_binary(folder: Path) -> Path:
    """Copy the fake ``llama-server`` into *folder* behind a Python shebang."""
    import stat
    import sys

    binary = folder / "llama-server"
    binary.write_text(f"#!{sys.executable}\n" + FAKE_SERVER.read_text(encoding="utf-8"))
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary
