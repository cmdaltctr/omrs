"""The local OCR backend list in the source index identity (local-ocr-backends, task 4.6).

The default list keeps today's ``ocr_routing.local_tier`` and adds nothing,
so every digest stays put. Another list adds one ``parser`` entry, PDF
sources only: each backend in order with its effective cut, resolved model
and kept scripts, plus the output-script classifier version. A second
backend comes from a fake descriptor patched into the descriptor table.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from omrs.core import reading_parts
from omrs.core.ingestion.ocr_identity import local_backends_payload, ocr_routing_payload
from omrs.core.ingestion.reader_identity import pdf_parser_payload
from omrs.core.ingestion.source_state import build_index_identity
from omrs.core.reading_parts import LocalOcrBackendDescriptor
from omrs.integrations.pdf import page_routing, script_routing

_FAKE = LocalOcrBackendDescriptor(
    name="fake-cut",
    import_path="tests.fake:BACKEND",
    label="Fake with cut",
    help_key="local_ocr_backend.fake-cut",
    producer="fake_cut_ocr",
    min_confidence=0.8,
    calibrated_by="1-fake-experiment",
    keeps_scripts=frozenset({"devanagari", "arabic"}),
)
_TWO = ("fake-cut", "pp-ocrv6-small")


@pytest.fixture(autouse=True)
def fake_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reading_parts, "LOCAL_OCR_BACKENDS", (*reading_parts.LOCAL_OCR_BACKENDS, _FAKE)
    )


@pytest.fixture
def models(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Patch the resolver (patch target follows the function, gotcha 8b); record calls."""
    calls: list[str] = []

    def fake_resolve(settings: Any, backend: str = "pp-ocrv6-small") -> str | None:
        calls.append(backend)
        return None if backend == "fake-cut" else f"{backend}@rev"

    monkeypatch.setattr(page_routing, "resolve_local_model_identity", fake_resolve)
    return calls


def _digest(settings: Any, content_type: str = "application/pdf") -> str:
    pdf = content_type == "application/pdf"
    return build_index_identity(
        settings,
        content_type=content_type,
        chunk_size=512,
        chunk_overlap=100,
        pdf_reader_revision=2 if pdf else None,
        embed_model=SimpleNamespace(model_name="pinned-embedder"),
    )


def test_resolver_takes_a_backend_name_with_the_default() -> None:
    """Shared contract with worker A: the default backend keeps today's call."""
    parameter = inspect.signature(page_routing.resolve_local_model_identity).parameters["backend"]
    assert parameter.default == "pp-ocrv6-small"


def test_default_list_adds_nothing(effective_settings: Any, models: list[str]) -> None:
    settings = effective_settings(ocr_fallback_enabled=True)
    assert local_backends_payload(settings) == {}
    assert "local_ocr_backends" not in pdf_parser_payload(settings)
    assert models == []


def test_default_list_keeps_todays_local_tier(effective_settings: Any) -> None:
    assert ocr_routing_payload(effective_settings())["local_tier"] == {"min_confidence": 0.9}
    listed = effective_settings(ocr_local_backends=_TWO)
    assert ocr_routing_payload(listed) == ocr_routing_payload(effective_settings())


def test_entry_lists_backends_in_order(effective_settings: Any, models: list[str]) -> None:
    settings = effective_settings(ocr_fallback_enabled=True, ocr_local_backends=_TWO)
    assert local_backends_payload(settings) == {
        "local_ocr_backends": {
            "backends": [
                {
                    "name": "fake-cut",
                    "min_confidence": 0.8,
                    "keeps_scripts": ["arabic", "devanagari"],
                },
                {
                    "name": "pp-ocrv6-small",
                    "min_confidence": 0.9,
                    "model": "pp-ocrv6-small@rev",
                    "keeps_scripts": None,
                },
            ],
            "output_script_version": script_routing.OUTPUT_SCRIPT_VERSION,
        }
    }
    assert models == list(_TWO)


def test_override_replaces_every_cut(effective_settings: Any, models: list[str]) -> None:
    settings = effective_settings(ocr_local_backends=_TWO, ocr_local_min_confidence=0.7)
    backends = local_backends_payload(settings)["local_ocr_backends"]["backends"]
    assert [b["min_confidence"] for b in backends] == [0.7, 0.7]


def test_models_resolve_only_when_ocr_routing_is_on(
    effective_settings: Any, models: list[str]
) -> None:
    settings = effective_settings(ocr_fallback_enabled=False, ocr_local_backends=_TWO)
    backends = local_backends_payload(settings)["local_ocr_backends"]["backends"]
    assert all("model" not in b for b in backends)
    assert models == []


def test_list_change_moves_pdf_digest_only(effective_settings: Any, models: list[str]) -> None:
    default = effective_settings()
    listed = effective_settings(ocr_local_backends=_TWO)
    assert _digest(listed) != _digest(default)
    assert _digest(listed, "text/markdown") == _digest(default, "text/markdown")


def test_output_script_version_moves_the_listed_digest(
    effective_settings: Any, monkeypatch: pytest.MonkeyPatch, models: list[str]
) -> None:
    listed = effective_settings(ocr_local_backends=_TWO)
    before = _digest(listed)
    monkeypatch.setattr(script_routing, "OUTPUT_SCRIPT_VERSION", 99)
    assert _digest(listed) != before
    # The default list does not carry the version, so its digest stays.
    default = _digest(effective_settings())
    monkeypatch.setattr(script_routing, "OUTPUT_SCRIPT_VERSION", 100)
    assert _digest(effective_settings()) == default


def test_explicit_default_cut_keeps_the_default_digest(effective_settings: Any) -> None:
    assert _digest(effective_settings(ocr_local_min_confidence=0.9)) == _digest(
        effective_settings()
    )
