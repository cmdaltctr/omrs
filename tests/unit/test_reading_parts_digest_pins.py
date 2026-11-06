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
DETECT_DIGEST = "6f99256dde779932ef8d0ff6b956f304b7ebcd96d4c40a549be583d731ed9eaa"
# Non-Latin routing "always": guards that the mode name alone moves the digest.
ALWAYS_DIGEST = "70ac715a9c4ad2a2991b3fc042d74ad28df39459dc96227ba98701066de7fe39"
# A resolved local model: guards the model in ``parser.local_ocr_backends``.
LOCAL_MODEL_DIGEST = "6f0616a7bf2d0bf8e2b650a5a5f0acb47cab207c37445651d0ad5a27eeb3c55c"
# Maths routing off (the default is on): guards ``maths_routing.enabled``.
MATHS_OFF_DIGEST = "f502cc3550e2e085c2ef6d79e3c8ee4fbea5f0fc4e81e22258b8987ea643c80f"
# Three OCR engines: guards the ``ocr_more_fingerprints`` member.
THIRD_ENGINE_DIGEST = "5347669f6b77e4ef5f168d71930a9e874b1c5cfa379637f0e7443ff7091b1939"

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
