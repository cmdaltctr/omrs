"""The config-facing embedding knobs (env prefix ``EMBEDDING__``).

Moved out of ``core/settings.py`` (change page-routing-panel), which sits at
the 500-line ceiling. Only :class:`omrs.config.Settings` uses this model, so it
lives with the other config-side parts (``ocr_routes.py``, ``storage.py``).
The ``core`` twin is :class:`omrs.core.settings.EmbeddingBlock`; both models
must stay in sync.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EmbeddingSettings(BaseModel):
    """Config-facing embedding knobs (env prefix ``EMBEDDING__``).

    The Settings twin of :class:`omrs.core.settings.EmbeddingBlock`. It does
    not live under ``core/providers/embeddings/``: the providers package is quarantined
    behind import-linter contracts that forbid transitive imports from
    retrieval, vectordb, and daemon, and ``config`` composing a providers
    submodule would leak that package across every module that imports
    config.
    """

    model_config = ConfigDict(extra="forbid")

    # Optional model-specific query prefix. Empty preserves the caller's
    # query verbatim, including for generic embedding models.
    query_instruction: str = ""
    # Explicit tokenizer identity prevents inference-server aliases from
    # selecting a mismatched size calculator. Promoted packaged default
    # (task 5.5, exp 25 PASS, ADR-063 Accepted): the evaluated Qwen
    # tokenizer. The Qwen3 embedding family shares one 151,669-token
    # vocabulary, so the identity matches every shipped embedding size.
    # Set both fields empty to return to the legacy character-budgeted
    # path; an uncached revision also falls back with a warning.
    tokenizer_model: str = "Qwen/Qwen3-Embedding-4B"
    tokenizer_revision: str = "5cf2132abc99cad020ac570b19d031efec650f2b"

    # Fail-closed at ingest, warn-and-continue at query. Disabling is an
    # explicit, startup-logged operator escape hatch — never a silent
    # default.
    norm_guard_enabled: bool = True
    # Observed float32 rounding band for the production model is ~1e-7;
    # three orders of headroom catch real drift without false alarms.
    norm_tolerance: float = Field(default=0.001, gt=0)
