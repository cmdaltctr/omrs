"""Literal digest pins for reading-part settings (change local-ocr-backends, task 1.2, D16).

Each pin is the source index identity digest of a PDF source, computed on
the code before the backend refactor. Later groups of the change must keep
every pin byte-identical. The pins cover settings that no earlier test pins
with a literal: non-Latin routing ``detect`` and ``always``, a resolved local
OCR model, maths routing off, and a third OCR engine.

The digests were computed under pytest with an explicit embedder, so they do
not depend on the conftest mock embedder. Settings: ``pdf_reader`` is
``pdf_inspector``, extraction is disabled, the tokenizer identity is empty,
the chunks are 512/100 and the PDF reader output revision is 2.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from omrs.core.ingestion.ocr_identity import resolved_routing_payload
from omrs.core.ingestion.source_state import build_index_identity
from omrs.integrations.ocr_worker.fingerprint import OcrWorkerFingerprint
from omrs.integrations.pdf import page_routing, script_routing

# Non-Latin routing "detect": guards the mode and detector version in the parser block.
DETECT_DIGEST = "d17e57eeaf1f1f964eeaca6e649571473798221941c1c2c53d85fc5d39680190"
# Non-Latin routing "always": guards that the mode name alone moves the digest.
ALWAYS_DIGEST = "21ab5a93a8bb4d858a9ab9cd1764cc4b7a37f39238901531f0048522494c6b12"
# A resolved local model: guards ``ocr_routing.local_tier.model``.
LOCAL_MODEL_DIGEST = "fcef2e013bf08c2024a90cabf13341779020eae0dbef4ad5c94ad38a62f7388e"
# Maths routing off (the default is on): guards ``maths_routing.enabled``.
MATHS_OFF_DIGEST = "b5972655848fa62def9dc9f059114f9e9b6a60ab2a44e651b82c3b39aed475e9"
# Three OCR engines: guards the ``ocr_more_fingerprints`` member.
THIRD_ENGINE_DIGEST = "08a0b65cbec16a3d70840623555e793b2ff5190f12416071f1b92ce21fcbaaed"

_RESOLVED_MODEL = "PP-OCRv6_small@pinned-revision"


def _fingerprint(backend_id: str) -> OcrWorkerFingerprint:
    """Return a fixed, available fingerprint for one engine."""
    return OcrWorkerFingerprint(
        available=True,
        protocol_version="1.1",
        packages=(("pkg", "1.0"),),
        pipeline_identity=backend_id,
        pipeline_revision="r1",
        model_identity=f"{backend_id}-m",
        model_revision="m1",
        output_schema_id="s",
        output_schema_version="1",
        backend_id=backend_id,
    )


def _digest(settings: Any, **identity: Any) -> str:
    """Return the digest of a PDF source under ``settings``.

    Args:
        settings: The effective settings to hash.
        **identity: Extra ``build_index_identity`` arguments (OCR routing or
            fingerprints).

    Returns:
        The hex source index identity digest.
    """
    return build_index_identity(
        settings,
        content_type="application/pdf",
        chunk_size=512,
        chunk_overlap=100,
        pdf_reader_revision=2,
        embed_model=SimpleNamespace(model_name="pinned-embedder"),
        **identity,
    )


@pytest.fixture
def pins(effective_settings: Any) -> Any:
    """Return a settings factory with the pinned reader and a clean model cache."""
    page_routing.reset_local_model_resolution()
    yield lambda **overrides: effective_settings(pdf_reader="pdf_inspector", **overrides)
    page_routing.reset_local_model_resolution()


def test_non_latin_detect_keeps_its_digest(pins: Any) -> None:
    assert _digest(pins(ocr_non_latin_routing="detect")) == DETECT_DIGEST


def test_non_latin_always_keeps_its_digest(pins: Any) -> None:
    assert _digest(pins(ocr_non_latin_routing="always")) == ALWAYS_DIGEST


def test_a_resolved_local_model_keeps_its_digest(
    monkeypatch: pytest.MonkeyPatch, pins: Any
) -> None:
    monkeypatch.setattr(
        page_routing, "_probe_local_model_identity", lambda settings: _RESOLVED_MODEL
    )
    settings = pins(ocr_fallback_enabled=True)

    routing = resolved_routing_payload(settings)

    assert routing["local_tier"]["model"] == _RESOLVED_MODEL
    assert _digest(settings, ocr_routing=routing) == LOCAL_MODEL_DIGEST


def test_maths_routing_off_keeps_its_digest(pins: Any) -> None:
    assert _digest(pins(ocr_maths_routing_enabled=False)) == MATHS_OFF_DIGEST
    assert _digest(pins(ocr_maths_routing_enabled=False)) != _digest(pins())


def test_a_third_engine_keeps_its_digest(pins: Any) -> None:
    engines = ("dots_mocr", "paddleocr_vl", "glm_ocr")
    settings = pins(ocr_fallback_enabled=True, ocr_engines=engines)
    digest = _digest(
        settings,
        ocr_worker_fingerprint=_fingerprint("dots_mocr"),
        ocr_fallback_fingerprint=_fingerprint("paddleocr_vl"),
        ocr_more_fingerprints=(_fingerprint("glm_ocr"),),
    )

    assert digest == THIRD_ENGINE_DIGEST


def test_the_detect_pin_follows_the_detector_version(
    monkeypatch: pytest.MonkeyPatch, pins: Any
) -> None:
    """Mutation check: a new detector version must move the ``detect`` digest."""
    monkeypatch.setattr(script_routing, "SCRIPT_DETECTOR_VERSION", 2)

    assert _digest(pins(ocr_non_latin_routing="detect")) != DETECT_DIGEST
