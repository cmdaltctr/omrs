"""The local OCR backend contract and registry (change local-ocr-backends, task 4.2).

Design D7: a backend reads pages and reports one confidence per page; it never
decides escalation. Design D9: the cut belongs to the backend, and a cut needs
the experiment that measured it. Design D17: the per-process switch-off moved
from ``page_routing._LOCAL_TIER_BROKEN`` to the registry, per backend.

``pdf_inspector`` is stubbed in ``sys.modules``; nothing loads a real model.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from omrs.integrations.pdf import page_routing
from omrs.integrations.pdf.local_ocr import registry
from omrs.integrations.pdf.local_ocr.base import BackendPage, page_confidence


@pytest.fixture
def isolated_registry():
    """Let a test register fake backends; put the real registry back after."""
    state = registry.BACKENDS.snapshot()
    page_routing.reset_local_model_resolution()
    yield registry
    registry.BACKENDS.restore(state)
    page_routing.reset_local_model_resolution()


class _IdentityBackend:
    """A fake backend whose identity names itself, counting each probe."""

    def __init__(self, identity: str) -> None:
        self._identity = identity
        self.probes = 0

    def read_pages(self, file, pages, *, settings):
        return []

    def identity(self, settings):
        self.probes += 1
        return self._identity


def _register_fake(name: str, backend, **facts) -> None:
    facts.setdefault("producer", f"{name}_ocr")
    registry.register(name, f"fake.{name}:BACKEND", **facts)
    registry.BACKENDS.cache[name] = backend


# ── Registration (design D9) ───────────────────────────────────────────────


def test_the_default_backend_is_registered_with_its_cut_and_producer() -> None:
    facts = registry.describe("pp-ocrv6-small")

    assert facts["import_path"] == "omrs.integrations.pdf.local_ocr.pp_ocrv6_small:BACKEND"
    assert facts["probe_module"] == "pdf_inspector"
    assert facts["min_confidence"] == 0.9
    assert facts["calibrated_by"] == "39-local-tier-escalation-2026-09-30"
    assert facts["keeps_scripts"] is None
    assert facts["producer"] == "pdf_inspector_ocr"
    assert registry.DEFAULT_BACKENDS == ("pp-ocrv6-small",)


def test_a_cut_without_its_experiment_is_refused(isolated_registry) -> None:
    with pytest.raises(ValueError, match="calibrated_by"):
        registry.register("uncalibrated", "fake.mod:BACKEND", producer="x", min_confidence=0.8)
    assert "uncalibrated" not in registry.available()


def test_a_backend_without_a_cut_registers(isolated_registry) -> None:
    registry.register("no-cut", "fake.mod:BACKEND", producer="x")

    assert registry.describe("no-cut")["min_confidence"] is None


def test_kept_scripts_are_stored_as_a_frozenset(isolated_registry) -> None:
    registry.register(
        "keeper",
        "fake.mod:BACKEND",
        producer="x",
        min_confidence=0.9,
        calibrated_by="46-local-ocr-backends-2026-11-04",
        keeps_scripts=["arabic", "devanagari"],
    )

    assert registry.describe("keeper")["keeps_scripts"] == frozenset({"arabic", "devanagari"})


def test_registering_imports_no_backend_module() -> None:
    """The register() line is lazy: the PP-OCRv6 module loads on first use only."""
    import subprocess

    code = (
        "import sys; import omrs.integrations.pdf.local_ocr.registry; "
        "print('omrs.integrations.pdf.local_ocr.pp_ocrv6_small' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# ── The effective cut (design D9) ──────────────────────────────────────────


def test_no_override_gives_the_backend_cut() -> None:
    settings = SimpleNamespace(ocr_local_min_confidence=None)

    assert registry.effective_cut("pp-ocrv6-small", settings) == 0.9


def test_an_override_replaces_the_backend_cut() -> None:
    settings = SimpleNamespace(ocr_local_min_confidence=0.7)

    assert registry.effective_cut("pp-ocrv6-small", settings) == 0.7


def test_settings_without_the_field_read_as_no_override() -> None:
    assert registry.effective_cut("pp-ocrv6-small", SimpleNamespace()) == 0.9
    assert registry.listed(SimpleNamespace()) == ("pp-ocrv6-small",)


# ── The PP-OCRv6 backend (design D7) ───────────────────────────────────────


def _settings(**overrides):
    base = {"ocr_local_model_directory": "", "ocr_local_offline": False}
    return SimpleNamespace(**{**base, **overrides})


def test_pp_ocrv6_imports_pdf_inspector_inside_read_pages(monkeypatch, tmp_path) -> None:
    """A stub in sys.modules after the module import still takes effect."""
    from omrs.integrations.pdf.local_ocr.pp_ocrv6_small import BACKEND

    calls: list[dict] = []
    provenance = SimpleNamespace(
        ocr_confidence=0.93,
        ocr_model=SimpleNamespace(name="pp-ocrv6-small", revision="r1"),
        hosted_recommended=True,
    )

    def _process(path, **kwargs):
        calls.append({"path": path, **kwargs})
        return SimpleNamespace(
            pages=[SimpleNamespace(page_number=5, markdown="five", provenance=provenance)]
        )

    stub = SimpleNamespace(process_pdf_with_ocr=_process)
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)

    pages = BACKEND.read_pages(tmp_path / "a.pdf", [5, 2], settings=_settings())

    assert calls[0]["mode"] == "force"
    assert calls[0]["page_numbers"] == [2, 5]
    assert calls[0]["model_directory"] is None
    assert calls[0]["offline"] is False
    assert pages == [BackendPage(5, "five", 0.93, "pp-ocrv6-small@r1", hosted_recommended=True)]


def test_pp_ocrv6_without_pdf_inspector_raises_import_error(monkeypatch, tmp_path) -> None:
    from omrs.integrations.pdf.local_ocr.pp_ocrv6_small import BACKEND

    monkeypatch.setitem(sys.modules, "pdf_inspector", None)

    with pytest.raises(ImportError, match="pdf_inspector is not installed"):
        BACKEND.read_pages(tmp_path / "a.pdf", [1], settings=_settings())


# ── Line confidences (local-ocr-backends spec, weighted mean) ──────────────


def test_line_confidences_reduce_to_a_character_weighted_mean() -> None:
    lines = [("a" * 90, 0.95), ("b" * 10, 0.45)]

    assert page_confidence(lines) == pytest.approx(0.90)


def test_whitespace_does_not_count_and_no_characters_give_none() -> None:
    assert page_confidence([("a b", 1.0), ("cc", 0.0)]) == pytest.approx(0.5)
    assert page_confidence([("   ", 0.9)]) is None
    assert page_confidence([]) is None


# ── Switch-off per backend (design D17) ────────────────────────────────────


def test_switch_off_is_per_backend(isolated_registry) -> None:
    _register_fake("fake-a", _IdentityBackend("a@1"))
    registry.switch_off("fake-a", "PanicException: poisoned")

    assert registry.off_reason("fake-a") == "PanicException: poisoned"
    assert registry.off_reason("pp-ocrv6-small") is None


def test_the_tier_is_off_only_when_every_listed_backend_is_off(isolated_registry) -> None:
    _register_fake("fake-a", _IdentityBackend("a@1"))
    two = SimpleNamespace(ocr_local_backends=("fake-a", "pp-ocrv6-small"))

    registry.switch_off("fake-a", "PanicException: a")
    assert page_routing.local_tier_off_reason(two) is None

    registry.switch_off("pp-ocrv6-small", "PanicException: pp")
    assert page_routing.local_tier_off_reason(two) == "PanicException: a"


def test_no_settings_reads_the_default_list() -> None:
    assert page_routing.local_tier_off_reason() is None
    page_routing.switch_local_tier_off("PanicException: pp")

    assert page_routing.local_tier_off_reason() == "PanicException: pp"
    assert registry.off_reason("pp-ocrv6-small") == "PanicException: pp"


# ── Identity per backend (design D17, cache key gains the backend) ─────────


def test_each_backend_resolves_its_own_identity(isolated_registry) -> None:
    first = _IdentityBackend("first@1")
    second = _IdentityBackend("second@2")
    _register_fake("fake-first", first)
    _register_fake("fake-second", second)
    settings = _settings()

    assert page_routing.resolve_local_model_identity(settings, "fake-first") == "first@1"
    assert page_routing.resolve_local_model_identity(settings, "fake-second") == "second@2"
    assert page_routing.resolve_local_model_identity(settings, "fake-first") == "first@1"
    assert (first.probes, second.probes) == (1, 1)


def test_a_switched_off_backend_resolves_no_identity(isolated_registry) -> None:
    backend = _IdentityBackend("a@1")
    _register_fake("fake-a", backend)
    registry.switch_off("fake-a", "PanicException: poisoned")

    assert page_routing.resolve_local_model_identity(_settings(), "fake-a") is None
    assert backend.probes == 0


def test_a_panic_in_one_identity_probe_switches_only_that_backend_off(isolated_registry) -> None:
    class _Panic(BaseException):
        pass

    class _Panicking(_IdentityBackend):
        def identity(self, settings):
            raise _Panic("poisoned")

    _register_fake("fake-a", _Panicking("never"))

    assert page_routing.resolve_local_model_identity(_settings(), "fake-a") is None
    assert registry.off_reason("fake-a") == "_Panic: poisoned"
    assert registry.off_reason("pp-ocrv6-small") is None
