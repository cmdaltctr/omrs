"""Where the dots-mocr-llamacpp engine keeps its files (design D3, D4)."""

from __future__ import annotations

from pathlib import Path

from omrs_ocr_worker_core.engine import model_cache_dir

ENGINE_NAME = "dots-mocr-llamacpp"

#: The engine project folder. ``uv sync`` installs the engine editable, so
#: ``__file__`` resolves inside ``engines/dots-mocr-llamacpp/src/``.
ENGINE_DIR = Path(__file__).resolve().parents[2]


def cache_dir() -> Path:
    """Return the engine's cache root."""
    return model_cache_dir(ENGINE_NAME, ENGINE_DIR)


def models_dir() -> Path:
    """Return the folder that holds the model file and the projector."""
    return cache_dir() / "models"


def llama_dir() -> Path:
    """Return the folder that holds the unpacked llama.cpp release."""
    return cache_dir() / "llama.cpp"
