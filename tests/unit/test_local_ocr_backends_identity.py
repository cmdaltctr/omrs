"""The local OCR backend list in the source index identity (change local-ocr-per-backend-cuts).

Identity schema 8. Every list, the default list included, adds one entry to the
PDF ``parser`` block: each listed backend in order with its effective cut and
its resolved model. The OCR routing block that every source carries holds no
cut and no model, so a cut or model change moves PDF digests and keeps every
other digest.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from omrs.core.ingestion import ocr_identity, source_state
from omrs.core.ingestion.ocr_identity import (
    local_backends_payload,
    ocr_routing_payload,
    resolved_routing_payload,
)
from omrs.core.ingestion.reader_identity import pdf_parser_payload
from omrs.core.ingestion.source_state import build_index_identity
from omrs.integrations.pdf import page_routing

_TWO = ("pp-ocrv6-small", "indra")
_INDRA_FIRST = ("indra", "pp-ocrv6-small")


@pytest.fixture
def models(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Patch the resolver (patch target follows the function, gotcha 8b); record calls."""
    calls: list[str] = []

    def fake_resolve(settings: Any, backend: str = "pp-ocrv6-small") -> str | None:
        calls.append(backend)
        return f"{backend}@rev"

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


def _payload_text(settings: Any, monkeypatch: pytest.MonkeyPatch, content_type: str) -> str:
    """Return the canonical JSON that one source identity hashes."""
    seen: list[str] = []
    real = source_state.json.dumps

    def dumps(value: Any, **kwargs: Any) -> str:
        seen.append(real(value, **kwargs))
        return seen[-1]

    monkeypatch.setattr(source_state, "json", SimpleNamespace(dumps=dumps))
    _digest(settings, content_type)
    return seen[0]


def _entry(name: str, cut: float, model: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": name, "min_confidence": cut}
    if model is not None:
        entry["model"] = model
    return entry


def test_resolver_takes_a_backend_name_with_the_default() -> None:
    """Shared contract with worker A: the default backend keeps today's call."""
    parameter = inspect.signature(page_routing.resolve_local_model_identity).parameters["backend"]
    assert parameter.default == "pp-ocrv6-small"


def test_identity_schema_is_8() -> None:
    assert source_state._INDEX_IDENTITY_SCHEMA == 8


# ── ocr_routing holds no local tier ──


def test_ocr_routing_holds_no_local_tier(effective_settings: Any) -> None:
    payload = ocr_routing_payload(effective_settings(ocr_fallback_enabled=True))
    assert set(payload) == {"enabled", "routing_unit", "blank_page_test"}


def test_resolved_routing_payload_probes_no_model(
    effective_settings: Any, models: list[str]
) -> None:
    payload = resolved_routing_payload(effective_settings(ocr_fallback_enabled=True))
    assert models == []
    assert payload == ocr_routing_payload(effective_settings(ocr_fallback_enabled=True))


def test_both_composition_paths_use_the_one_routing_builder() -> None:
    from omrs.core.ingestion import graph_adapters_values, sources

    for module in (graph_adapters_values, sources):
        assert module.resolved_routing_payload is resolved_routing_payload


# ── The PDF parser block holds the backend list ──


def test_default_list_names_the_default_backend_at_its_default_cut(
    effective_settings: Any, models: list[str]
) -> None:
    settings = effective_settings(ocr_fallback_enabled=True)
    expected = {
        "local_ocr_backends": {"backends": [_entry("pp-ocrv6-small", 0.92, "pp-ocrv6-small@rev")]}
    }
    assert local_backends_payload(settings) == expected
    assert models == ["pp-ocrv6-small"]
    assert pdf_parser_payload(settings)["local_ocr_backends"] == expected["local_ocr_backends"]


def test_entry_lists_backends_in_order(effective_settings: Any, models: list[str]) -> None:
    settings = effective_settings(ocr_fallback_enabled=True, ocr_local_backends=_INDRA_FIRST)
    assert local_backends_payload(settings) == {
        "local_ocr_backends": {
            "backends": [
                _entry("indra", 0.94, "indra@rev"),
                _entry("pp-ocrv6-small", 0.92, "pp-ocrv6-small@rev"),
            ]
        }
    }
    assert models == list(_INDRA_FIRST)
    listed = effective_settings(ocr_local_backends=_TWO)
    names = [b["name"] for b in local_backends_payload(listed)["local_ocr_backends"]["backends"]]
    assert names == list(_TWO)


def test_entry_reads_the_cut_through_effective_cut(
    effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One source of truth for the cut: the identity holds no literal."""
    monkeypatch.setattr(ocr_identity, "effective_cut", lambda settings, name: 0.31)
    backends = local_backends_payload(effective_settings(ocr_local_backends=_TWO))
    assert [b["min_confidence"] for b in backends["local_ocr_backends"]["backends"]] == [0.31, 0.31]


def test_entry_cuts_follow_the_cut_map(effective_settings: Any) -> None:
    settings = effective_settings(
        ocr_local_backends=_TWO, ocr_local_cuts={"indra": 0.96, "pp-ocrv6-small": 0.7}
    )
    backends = local_backends_payload(settings)["local_ocr_backends"]["backends"]
    assert [(b["name"], b["min_confidence"]) for b in backends] == [
        ("pp-ocrv6-small", 0.7),
        ("indra", 0.96),
    ]


def test_models_resolve_only_when_ocr_routing_is_on(
    effective_settings: Any, models: list[str]
) -> None:
    settings = effective_settings(ocr_fallback_enabled=False, ocr_local_backends=_TWO)
    backends = local_backends_payload(settings)["local_ocr_backends"]["backends"]
    assert all("model" not in b for b in backends)
    assert models == []


def test_a_list_without_the_default_backend_leaves_its_model_out(
    effective_settings: Any, models: list[str]
) -> None:
    """PR #168, finding 5: only a listed backend is probed."""
    settings = effective_settings(ocr_fallback_enabled=True, ocr_local_backends=("indra",))
    local_backends_payload(settings)
    assert models == ["indra"]


# ── No payload holds the retired script keys ──


@pytest.mark.parametrize("backends", [("pp-ocrv6-small",), _TWO], ids=["default", "two"])
@pytest.mark.parametrize("content_type", ["application/pdf", "text/markdown"])
def test_no_payload_holds_a_script_key(
    effective_settings: Any,
    monkeypatch: pytest.MonkeyPatch,
    models: list[str],
    backends: tuple[str, ...],
    content_type: str,
) -> None:
    settings = effective_settings(ocr_fallback_enabled=True, ocr_local_backends=backends)
    text = _payload_text(settings, monkeypatch, content_type)
    assert "keeps_scripts" not in text
    assert "output_script_version" not in text
    assert "local_tier" not in text


# ── Digests: the cut and the model live in the PDF block only ──


def test_explicit_default_cut_keeps_the_default_digest(effective_settings: Any) -> None:
    explicit = effective_settings(ocr_local_cuts={"pp-ocrv6-small": 0.92})
    assert _digest(explicit) == _digest(effective_settings())
    both = {"pp-ocrv6-small": 0.92, "indra": 0.94}
    assert _digest(effective_settings(ocr_local_backends=_TWO, ocr_local_cuts=both)) == _digest(
        effective_settings(ocr_local_backends=_TWO)
    )


@pytest.mark.parametrize(
    ("backends", "cuts"),
    [
        (("pp-ocrv6-small",), {"pp-ocrv6-small": 0.95}),
        (_TWO, {"pp-ocrv6-small": 0.95}),
        (_TWO, {"indra": 0.96}),
    ],
)
def test_a_cut_change_moves_pdf_only(
    effective_settings: Any, backends: tuple[str, ...], cuts: dict[str, float]
) -> None:
    base = effective_settings(ocr_local_backends=backends)
    changed = effective_settings(ocr_local_backends=backends, ocr_local_cuts=cuts)
    assert _digest(changed) != _digest(base)
    assert _digest(changed, "text/markdown") == _digest(base, "text/markdown")


def test_a_cut_for_an_unlisted_backend_moves_no_digest(effective_settings: Any) -> None:
    changed = effective_settings(ocr_local_cuts={"indra": 0.96})
    assert _digest(changed) == _digest(effective_settings())


def test_a_resolved_model_moves_pdf_only(
    effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = effective_settings(ocr_fallback_enabled=True)
    answers = {"model": None}
    monkeypatch.setattr(
        page_routing, "resolve_local_model_identity", lambda s, backend="x": answers["model"]
    )
    unresolved_pdf = _digest(settings)
    unresolved_md = _digest(settings, "text/markdown")
    answers["model"] = "pp-ocrv6-small@rev"
    resolved_pdf = _digest(settings)
    assert resolved_pdf != unresolved_pdf
    assert _digest(settings, "text/markdown") == unresolved_md
    answers["model"] = "pp-ocrv6-small@other"
    assert _digest(settings) != resolved_pdf


def test_list_change_moves_pdf_digest_only(effective_settings: Any) -> None:
    default = effective_settings()
    listed = effective_settings(ocr_local_backends=_INDRA_FIRST)
    assert _digest(listed) != _digest(default)
    assert _digest(listed, "text/markdown") == _digest(default, "text/markdown")


def test_ocr_routing_switch_still_moves_every_source(effective_settings: Any) -> None:
    on = effective_settings(ocr_fallback_enabled=True)
    off = effective_settings(ocr_fallback_enabled=False)
    assert _digest(on, "text/markdown") != _digest(off, "text/markdown")
