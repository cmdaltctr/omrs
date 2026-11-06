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

from omrs.core.ingestion.ocr_identity import (
    local_backends_payload,
    ocr_routing_payload,
    resolved_routing_payload,
)
from omrs.core.ingestion.source_state import build_index_identity
from omrs.integrations.ocr_worker.fingerprint import OcrWorkerFingerprint
from omrs.integrations.pdf import page_routing, script_routing

# Re-pinned on 6 November 2026 (change local-ocr-per-backend-cuts): schema 7 to 8,
# ``ocr_routing.local_tier`` gone, ``parser.local_ocr_backends`` added (default
# backend at cut 0.92). Every pin below moved for those reasons only.
# Non-Latin routing "detect": guards the mode and detector version in the parser block.
DETECT_DIGEST = "4d5741aa650f3cab0e70068fe706325322d614b2f278b42e77089a255ec010b9"
# Non-Latin routing "always": guards that the mode name alone moves the digest.
ALWAYS_DIGEST = "e66860f8b2a87ea1320942dc9e8812d569430894b09119cf0888198a9b097332"
# A resolved local model: guards the model in ``parser.local_ocr_backends``.
LOCAL_MODEL_DIGEST = "c95e3a36819cd54a978cab474ab51cc505d1c4669b8fce70a9c3f08797049e6f"
# Maths routing off (the default is on): guards ``maths_routing.enabled``.
MATHS_OFF_DIGEST = "15118e467a79571496cbcf720e12ad7bb4715bbabe76f09d0f253bcabbf34198"
# Three OCR engines: guards the ``ocr_more_fingerprints`` member.
THIRD_ENGINE_DIGEST = "e1dfec5777ec266cf6b5d7738d14b31cdf0ff761a120b77f5db6961cf1cde082"

_RESOLVED_MODEL = "PP-OCRv6_small@pinned-revision"


@pytest.fixture(autouse=True)
def _unresolved_local_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hash with the local OCR model unresolved: the real probe depends on the host runtime."""
    page_routing.reset_local_model_resolution()
    monkeypatch.setattr(
        page_routing, "_probe_local_model_identity", lambda settings, backend="x": None
    )


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

    backends = local_backends_payload(settings)

    assert backends["local_ocr_backends"]["backends"][0]["model"] == _RESOLVED_MODEL
    assert resolved_routing_payload(settings) == ocr_routing_payload(settings)
    assert _digest(settings, local_ocr_backends=backends) == LOCAL_MODEL_DIGEST


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
