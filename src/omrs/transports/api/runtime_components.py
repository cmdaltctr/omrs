"""Runtime components for ``GET /v1/integrations`` (integrations-show-runtime-components, D1).

The ``runtime`` block lists the parts that a setting depends on but that no
pip extra installs: OCR engines, model files and local servers. Each item
says whether it is ready, why not, and the command that fixes it.

Every probe only reads. No probe downloads a file, installs a package,
starts a process or writes a file. OCR engines use the same resolver as
parsing (``resolve_engine_command``), so the page and parsing cannot
disagree. Model files read the local Hugging Face cache only. The server
probes live in ``runtime_servers.py``.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from huggingface_hub import try_to_load_from_cache

from ... import capabilities
from ...config.user_config import display_path
from ...integrations.ocr_worker.manifest import engine_manifest, licence_gate
from ...integrations.ocr_worker.routes import _ENGINE_NAME_RE, resolve_engine_command

logger = logging.getLogger(__name__)

READY = "ready"
MISSING = "missing"
NOT_CONFIGURED = "not-configured"
NOT_RUNNING = "not-running"
UNKNOWN = "unknown"

LOCAL_TIER_NAME = "local OCR tier"
TOKENIZER_NAME = "Chunking tokenizer"
RERANKER_NAME = "Reranker model"
LOCAL_MODEL_NAME = "Local OCR model"

#: The pdf-inspector page model (``pp-ocrv6-small@oar-ocr-v0.7.0``).
LOCAL_MODEL_RELEASE = "https://github.com/GreatV/oar-ocr/releases/download/v0.7.0"
LOCAL_MODEL_FILES = ("pp-ocrv6_small_det.onnx", "pp-ocrv6_small_rec.onnx", "ppocrv6_dict.txt")
_LOCAL_MODEL_SUBDIR = Path("pp-ocrv6-small") / "oar-ocr-v0.7.0"

UNCHECKED = "The server could not check this item."


@dataclass(frozen=True)
class RuntimeItem:
    """One runtime component row.

    Attributes:
        name: Display name.
        purpose: One-line description of what it does.
        status: ``ready``, ``missing``, ``not-configured``, ``not-running`` or ``unknown``.
        reason: Why it is not ready, or ``None``.
        fix: A copy command that fixes it, or ``None``.
        used_by: The settings in force at launch that need it.
    """

    name: str
    purpose: str
    status: str
    reason: str | None = None
    fix: str | None = None
    used_by: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        """Return the response shape, with ``used_by`` as a list."""
        return {**asdict(self), "used_by": list(self.used_by)}


def guarded(name: str, purpose: str, probe: Callable[[], RuntimeItem]) -> RuntimeItem:
    """Run *probe*; a probe that raises gives ``unknown`` and no error text."""
    try:
        return probe()
    except Exception:
        # Detail stays in the (redacted) log. The client gets the state only.
        logger.warning("Runtime probe %r failed.", name, exc_info=True)
        return RuntimeItem(name, purpose, UNKNOWN, UNCHECKED)


# ── OCR engines ──────────────────────────────────────────────────────────

ENGINE_PURPOSE = "OCR engine for PDF pages without a usable text layer."
LOCAL_TIER_PURPOSE = "Reads flagged pages with the small local model before a worker engine."


def _engine_used_by(settings: Any, name: str) -> tuple[str, ...]:
    if not settings.ocr_fallback_enabled:
        return ()
    keys = ("ocr_engine_primary", "ocr_engine_fallback")
    return tuple(key for key in keys if str(getattr(settings, key, "")).strip() == name)


def _engine_item(name: str, root: str, settings: Any) -> RuntimeItem:
    used_by = _engine_used_by(settings, name)
    if not _ENGINE_NAME_RE.fullmatch(name):
        return RuntimeItem(
            name, ENGINE_PURPOSE, MISSING, "The name is not a folder name.", None, used_by
        )
    if not root:
        reason = "The OCR workers folder is not set, so no OCR engine can run."
        return RuntimeItem(name, ENGINE_PURPOSE, NOT_CONFIGURED, reason, None, used_by)
    if resolve_engine_command(name, root).command:
        return RuntimeItem(name, ENGINE_PURPOSE, READY, None, None, used_by)
    folder = Path(root).expanduser() / "engines" / name
    if not (folder / "pyproject.toml").is_file():
        reason = "The workers folder has no engine folder with this name."
        return RuntimeItem(name, ENGINE_PURPOSE, MISSING, reason, None, used_by)
    needs_licence, licence_file = licence_gate(engine_manifest(folder))
    fix = f"python3 ocr-workers/provision.py {name}"
    reason = "Not provisioned."
    if needs_licence:
        fix += " --accept-model-licence"
        reason += (
            f" The model licence adds terms. Read {licence_file or 'the licence notes'}"
            " in the engine folder before you accept it."
        )
    return RuntimeItem(name, ENGINE_PURPOSE, MISSING, reason, fix, used_by)


def _engine_names(root: str, settings: Any) -> list[str]:
    names = {
        str(getattr(settings, key, "")).strip()
        for key in ("ocr_engine_primary", "ocr_engine_fallback")
    }
    try:
        engines = Path(root).expanduser() / "engines"
        if root and engines.is_dir():
            names |= {
                item.name
                for item in engines.iterdir()
                if item.is_dir() and _ENGINE_NAME_RE.fullmatch(item.name)
            }
    except (RuntimeError, OSError):
        # The engines in force are still listed; their guarded probes report.
        logger.warning("The OCR engines folder could not be listed.", exc_info=True)
    return sorted(name for name in names if name)


def _local_tier_item(settings: Any) -> RuntimeItem:
    used_by = ("ocr_routing_unit",) if settings.ocr_routing_unit == "page" else ()
    if not capabilities.pdf_reader_installed("pdf_inspector"):
        reason = "The pdf-inspector reader is not installed."
        fix = "uv sync --extra pdf-inspector"
        return RuntimeItem(LOCAL_TIER_NAME, LOCAL_TIER_PURPOSE, MISSING, reason, fix, used_by)
    model = _local_model_item(settings)
    return RuntimeItem(
        LOCAL_TIER_NAME, LOCAL_TIER_PURPOSE, model.status, model.reason, model.fix, used_by
    )


def ocr_engine_items(settings: Any) -> list[RuntimeItem]:
    """Return every engine folder, the engines in force and the local OCR tier."""
    root = str(getattr(settings, "ocr_workers_dir", "") or "").strip()
    items = [
        guarded(name, ENGINE_PURPOSE, lambda name=name: _engine_item(name, root, settings))
        for name in _engine_names(root, settings)
    ]
    items.append(guarded(LOCAL_TIER_NAME, LOCAL_TIER_PURPOSE, lambda: _local_tier_item(settings)))
    return items


# ── Model files ──────────────────────────────────────────────────────────

TOKENIZER_PURPOSE = "Counts tokens for token-aware Markdown chunking."
RERANKER_PURPOSE = "Re-scores search results when the reranker is on."
LOCAL_MODEL_PURPOSE = "The page model of the local OCR tier."


def _hf_fix(repo: str, files: Iterable[str], revision: str | None = None) -> str:
    command = f"uvx --from huggingface_hub hf download {repo} {' '.join(files)}"
    return f"{command} --revision {revision}" if revision else command


def _cached(repo: str, filename: str, revision: str | None = None) -> bool:
    return isinstance(try_to_load_from_cache(repo, filename, revision=revision), str)


def _tokenizer_item(settings: Any) -> RuntimeItem:
    model = settings.embedding.tokenizer_model.strip()
    revision = settings.embedding.tokenizer_revision.strip()
    if not model or not revision:
        reason = "Token-aware chunking is off, so Markdown uses the legacy splitter."
        return RuntimeItem(TOKENIZER_NAME, TOKENIZER_PURPOSE, NOT_CONFIGURED, reason)
    used_by = ("embedding.tokenizer_model",)
    if _cached(model, "tokenizer.json", revision):
        return RuntimeItem(TOKENIZER_NAME, TOKENIZER_PURPOSE, READY, used_by=used_by)
    reason = (
        f"{model} at revision {revision[:8]} is not in the local cache. "
        "Markdown chunking falls back to the legacy splitter."
    )
    fix = _hf_fix(model, ["tokenizer.json"], revision)
    return RuntimeItem(TOKENIZER_NAME, TOKENIZER_PURPOSE, MISSING, reason, fix, used_by)


def _reranker_item(settings: Any) -> RuntimeItem:
    from ...core.retrieval.reranker import _select_onnx_variant

    model = settings.retrieval.rerank_model.strip()
    used_by = ("retrieval.rerank_enabled",) if settings.retrieval.rerank_enabled else ()
    candidates = _select_onnx_variant(model)
    if _cached(model, "tokenizer.json") and any(_cached(model, name) for name in candidates):
        return RuntimeItem(RERANKER_NAME, RERANKER_PURPOSE, READY, used_by=used_by)
    reason = f"{model} is not in the local cache. The first reranked search downloads it."
    fix = _hf_fix(model, [candidates[0], "tokenizer.json"])
    return RuntimeItem(RERANKER_NAME, RERANKER_PURPOSE, MISSING, reason, fix, used_by)


def _platform_cache() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")


def local_model_folder(settings: Any) -> Path:
    """Return the folder that pdf-inspector reads the local OCR model from."""
    explicit = str(getattr(settings, "ocr_local_model_directory", "") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    root = os.environ.get("PDF_INSPECTOR_MODEL_CACHE", "").strip()
    models = Path(root).expanduser() if root else _platform_cache() / "pdf-inspector" / "models"
    return models / _LOCAL_MODEL_SUBDIR


def _local_model_item(settings: Any) -> RuntimeItem:
    used_by = ("ocr_routing_unit",) if settings.ocr_routing_unit == "page" else ()
    folder = local_model_folder(settings)
    if all((folder / name).is_file() for name in LOCAL_MODEL_FILES):
        return RuntimeItem(LOCAL_MODEL_NAME, LOCAL_MODEL_PURPOSE, READY, used_by=used_by)
    shown = display_path(folder)
    reason = f"Not in {shown}. The first page OCR downloads it unless ocr_local_offline is on."
    fetch = " ".join(f"-O {LOCAL_MODEL_RELEASE}/{name}" for name in LOCAL_MODEL_FILES)
    target = "$HOME" + shown[1:] if shown.startswith("~") else shown
    fix = f'mkdir -p "{target}" && cd "{target}" && curl -fL {fetch}'
    return RuntimeItem(LOCAL_MODEL_NAME, LOCAL_MODEL_PURPOSE, MISSING, reason, fix, used_by)


def model_file_items(settings: Any) -> list[RuntimeItem]:
    """Return the tokenizer, the reranker model and the local OCR model."""
    return [
        guarded(TOKENIZER_NAME, TOKENIZER_PURPOSE, lambda: _tokenizer_item(settings)),
        guarded(RERANKER_NAME, RERANKER_PURPOSE, lambda: _reranker_item(settings)),
        guarded(LOCAL_MODEL_NAME, LOCAL_MODEL_PURPOSE, lambda: _local_model_item(settings)),
    ]
