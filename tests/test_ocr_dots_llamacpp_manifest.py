"""The dots-mocr-llamacpp engine folder: lockfile, manifest and copied code.

Change dots-mocr-llamacpp-backend, tasks 2.1 and 2.2. The engine runs
dots.mocr through a llama.cpp server, so its environment must hold no
PyTorch. The prompt, the render settings and ``layout.py`` are copies of
the PyTorch engine's until cut-over (design D6); a test pins the copies.
"""

from __future__ import annotations

import importlib
import re
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.ocr_worker.isolation import isolated_worker_modules

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKERS = REPO_ROOT / "ocr-workers"
ENGINE_DIR = WORKERS / "engines" / "dots-mocr-llamacpp"
PYTORCH_DIR = WORKERS / "engines" / "dots-mocr"
PACKAGE = "omrs_ocr_dots_mocr_llamacpp"

FORBIDDEN = frozenset({"torch", "torchvision", "transformers", "accelerate"})


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _lock_names() -> set[str]:
    lock = tomllib.loads((ENGINE_DIR / "uv.lock").read_text(encoding="utf-8"))
    return {_normalise(pkg["name"]) for pkg in lock["package"]}


def test_lockfile_holds_no_pytorch_package() -> None:
    """The lock resolves no torch, torchvision, transformers or accelerate."""
    names = _lock_names()
    assert {"omrs-ocr-worker-core", "pypdfium2", "pillow", "huggingface-hub"} <= names
    assert not names & FORBIDDEN, sorted(names & FORBIDDEN)


def test_manifest_declares_entry_point_gate_and_no_fetch_of_pytorch() -> None:
    """The manifest names the entry point, the licence gate and the fetch script."""
    manifest = tomllib.loads((ENGINE_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    project = manifest["project"]
    assert project["name"] == "omrs-ocr-dots-mocr-llamacpp"
    assert project["entry-points"]["omrs.ocr_engine"] == {
        "dots-mocr-llamacpp": f"{PACKAGE}.engine:ENGINE"
    }
    assert project["scripts"]["omrs-ocr-fetch"] == f"{PACKAGE}.fetch:main"
    assert manifest["tool"]["omrs-ocr"] == {
        "licence-file": "LICENCE-NOTES.md",
        "requires-acceptance": True,
    }
    declared = {
        _normalise(re.split(r"[\[\s><=!~]", r, maxsplit=1)[0]) for r in project["dependencies"]
    }
    assert declared == {
        "omrs-ocr-worker-core",
        "pypdfium2",
        "pillow",
        "huggingface-hub",
    }
    assert manifest["tool"]["uv"]["sources"]["omrs-ocr-worker-core"] == {"path": "../../core"}


def test_licence_notes_keep_the_clauses_and_add_provenance() -> None:
    """Licence notes copy the PyTorch engine's clauses and record the GGUF files."""
    notes = (ENGINE_DIR / "LICENCE-NOTES.md").read_text(encoding="utf-8")
    for clause in ("3.3(c)", "5.2", "Clause 8", "Clause 9"):
        assert clause in notes
    for needle in (
        "6017b1844a77837010649939fe2e934af17728fc89243f88b10bde4afa04d6be",
        "63f415f961da981d0ee101cfdbf7a7bcc81ace4c4aa780a6e2823c0cd780761f",
        "e539fbb52280393adc081b289ec597430a0f9031",
        "11941",
    ):
        assert needle in notes
    assert "/Users/" not in notes


def test_gitignore_keeps_environment_and_model_cache_out_of_git() -> None:
    """The engine's virtual environment and model cache are ignored."""
    lines = (ENGINE_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".venv/" in lines and ".model-cache/" in lines


# ── Task 2.2: the copies of the PyTorch engine's pure parts ────────────────


@pytest.fixture
def both(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Any, Any]]:
    """Import the PyTorch engine package and the new package from source."""
    for src in (
        WORKERS / "core" / "src",
        PYTORCH_DIR / "src",
        ENGINE_DIR / "src",
    ):
        monkeypatch.syspath_prepend(str(src))
    with isolated_worker_modules():
        yield (
            importlib.import_module("omrs_ocr_dots_mocr.engine"),
            importlib.import_module(f"{PACKAGE}.prompt"),
        )


def test_layout_is_a_byte_for_byte_copy() -> None:
    """``layout.py`` in both engines is the same file."""
    old = (PYTORCH_DIR / "src" / "omrs_ocr_dots_mocr" / "layout.py").read_bytes()
    new = (ENGINE_DIR / "src" / PACKAGE / "layout.py").read_bytes()
    assert new == old


def test_prompt_and_render_settings_match_the_pytorch_engine(both: tuple[Any, Any]) -> None:
    """The prompt, the render settings and the token cap are equal."""
    old, new = both
    assert new.PROMPT == old.PROMPT
    assert new.RENDER_DPI == old.RENDER_DPI
    assert new.MIN_LONG_SIDE_PX == old.MIN_LONG_SIDE_PX
    assert new.MAX_NEW_TOKENS == old.MAX_NEW_TOKENS


def test_no_module_of_the_package_imports_pytorch() -> None:
    """No source file in the package names a PyTorch-family import."""
    pattern = re.compile(
        r"^\s*(?:import|from)\s+(?:torch|torchvision|transformers|accelerate|qwen_vl_utils)\b",
        re.MULTILINE,
    )
    sources = sorted((ENGINE_DIR / "src" / PACKAGE).glob("*.py"))
    assert sources, "the package has no source files"
    assert not [p.name for p in sources if pattern.search(p.read_text(encoding="utf-8"))]
