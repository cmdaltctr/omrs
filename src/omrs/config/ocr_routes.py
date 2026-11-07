"""OCR engine route and maths-routing settings (change modular-ocr-workers-dots-mocr).

The six fields live in a mixin so ``config/__init__.py`` stays under the
file-size ceiling (the ``storage.py`` precedent). They are flat,
top-level fields beside the other OCR fields, read from ``OCR_WORKERS_DIR``,
``OCR_ENGINE_PRIMARY``, ``OCR_ENGINE_FALLBACK``, ``OCR_MATHS_ROUTING_ENABLED``,
``OCR_MATHS_PAGE_FRACTION`` and ``OCR_WORKER_SECONDS_PER_PAGE``.

Engine names are not validated against a list here: the host resolves an
engine from its folder name alone (design D3), and an unknown name
degrades to the unavailable fingerprint at the composition boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from .rules import ACCEPTED, _validate_provider_value, address_problem
from .sources import LegacyBool


class OcrRouteSettingsMixin(BaseModel):
    """The OCR route and maths-routing fields of :class:`omrs.config.Settings`."""

    # Design D3: the primary route serves every OCR dispatch; the fallback
    # serves only when the primary is unavailable before dispatch. Empty
    # workers directory = every route unavailable; empty fallback = none.
    ocr_workers_dir: str = ""
    ocr_engine_primary: str = "dots-mocr"
    ocr_engine_fallback: str = "paddleocr-vl"
    # Design D5/D6: maths pages route to OCR. The document-unit maths page
    # fraction went with the document unit (change page-routing-default).
    ocr_maths_routing_enabled: LegacyBool = True
    # Change page-routing-panel, design D3: a plain bool, so a typo such as
    # ``ture`` stops start-up instead of turning the blank drop off silently.
    ocr_skip_blank_pages: bool = True
    # Change non-latin-script-routing: off, detect or always. The value feeds
    # the index identity, so an unknown one stops start-up (no fallback).
    ocr_non_latin_routing: str = "off"
    # dots.mocr took 7-56 s per page on MPS (Experiment 34); 120 s leaves
    # headroom for CPU and long pages. The per-request timeout stays a floor.
    ocr_worker_seconds_per_page: float = Field(default=120.0, ge=0.0)
    # Change managed-llamacpp-runtimes D2: blank means OMRS starts the
    # llama-server an engine declares (managed). A set address means external:
    # OMRS starts nothing and passes it to every engine that declares a runtime.
    ocr_runtime_url: str = ""

    @field_validator("ocr_workers_dir", "ocr_engine_primary", "ocr_engine_fallback")
    @classmethod
    def _strip(cls, value: str) -> str:
        """Strip padding so ``OCR_ENGINE_FALLBACK= `` means no fallback."""
        return value.strip()

    @model_validator(mode="after")
    def _check_non_latin_routing(self) -> OcrRouteSettingsMixin:
        """Strip padding, reset blank to ``off`` and refuse an unknown mode."""
        _validate_provider_value(
            self,
            "ocr_non_latin_routing",
            ACCEPTED["ocr_non_latin_routing"],
            "OCR_NON_LATIN_ROUTING",
        )
        return self

    @model_validator(mode="after")
    def _check_runtime_url(self) -> OcrRouteSettingsMixin:
        """Strip padding, let blank mean managed, and apply the address rule to the rest.

        A model validator, not a field validator, so the error never echoes the address.
        """
        value = self.ocr_runtime_url.strip()
        problem = address_problem(value) if value else None
        if problem:
            raise ValueError(f"OCR_RUNTIME_URL is not valid. {problem}")
        object.__setattr__(self, "ocr_runtime_url", value)
        return self
