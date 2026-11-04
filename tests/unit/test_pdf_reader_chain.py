"""Reader list rules (ordered-reader-and-ocr-lists, tasks 2.1 and 2.2).

Start-up picks the first installed listed reader. The pdf-inspector rescue
retries with the readers that follow it in the list. No test parses a real
PDF: pdf-inspector is stubbed in ``sys.modules`` and the tier readers are
seeded into the registry cache.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from llama_index.core import Document
from tests.unit.test_pdf_inspector_reader import _stub_pdf_inspector

from omrs.capabilities import resolve_pdf_reader, resolve_pdf_readers
from omrs.integrations.pdf import registry
from omrs.integrations.pdf.chain import clean_reader_list, rescue_pages, tiers_after
from omrs.integrations.pdf.factory import build_pdf_reader
from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader


def _list_settings(*names: str) -> Any:
    """Settings stand-in that carries only the reader list."""
    return SimpleNamespace(pdf_readers=names, pdf_reader=names[0] if names else "auto")


def _seed(monkeypatch: pytest.MonkeyPatch, name: str, texts: list[str] | Exception) -> list[str]:
    """Seed the registry cache with a stub reader; return the log of its constructions."""
    built: list[str] = []

    class _Stub:
        def __init__(self, *, ocr_enabled: bool = False, num_workers: int | None = None) -> None:
            assert ocr_enabled is False and num_workers is None
            built.append(name)

        def load_data(self, file: Path, *args: Any, **kwargs: Any) -> list:
            if isinstance(texts, Exception):
                raise texts
            return [Document(text=text) for text in texts]

    monkeypatch.setitem(registry._cache, name, _Stub)
    return built


def _silent_empty(monkeypatch: pytest.MonkeyPatch, pages: int = 2) -> None:
    """Stub pdf-inspector so it reports ``text_based`` with no extracted text."""
    _stub_pdf_inspector(monkeypatch, "", page_count=pages, pages_needing_ocr=list(range(pages)))


def _pdf(tmp_path: Path) -> Path:
    path = tmp_path / "sloman.pdf"
    path.write_bytes(b"%PDF-1.4 stub")
    return path


# ── 2.1 Start-up choice ──────────────────────────────────────────────────


def test_a_missing_first_reader_is_skipped_and_named(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    with caplog.at_level(logging.WARNING):
        assert resolve_pdf_reader(_list_settings("pypdfium2", "pypdf")) == "pypdf"
    assert any("pypdfium2" in r.message and "not installed" in r.message for r in caplog.records)


def test_the_first_installed_reader_wins_even_when_later_ones_are_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "pdf_inspector", None)
    monkeypatch.setitem(sys.modules, "liteparse", SimpleNamespace())
    assert resolve_pdf_reader(_list_settings("pdf_inspector", "liteparse", "pypdf")) == "liteparse"


def test_no_installed_reader_logs_an_error_and_uses_pypdf(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    monkeypatch.setitem(sys.modules, "liteparse", None)
    with caplog.at_level(logging.ERROR):
        assert resolve_pdf_reader(_list_settings("liteparse", "pypdfium2")) == "pypdf"
    assert any(r.levelno == logging.ERROR and "pypdfium2" in r.message for r in caplog.records)


def test_auto_in_a_list_is_dropped_with_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert clean_reader_list(("auto", "pypdf")) == ("pypdf",)
    assert any("single-value" in r.message for r in caplog.records)


def test_an_unknown_name_in_a_list_is_dropped_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        assert clean_reader_list(("fastparser", "pypdf")) == ("pypdf",)
    assert any("fastparser" in r.message for r in caplog.records)


def test_the_resolved_list_is_the_cleaned_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pdf_inspector", SimpleNamespace())
    reader, readers = resolve_pdf_readers(_list_settings("pdf_inspector", "auto", "pypdfium2"))
    assert (reader, readers) == ("pdf_inspector", ("pdf_inspector", "pypdfium2"))


def test_a_single_auto_keeps_the_probe_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "liteparse", None)
    monkeypatch.setitem(sys.modules, "pypdfium2", SimpleNamespace())
    settings: Any = SimpleNamespace(pdf_readers=(), pdf_reader="auto")
    assert resolve_pdf_reader(settings) == "pypdfium2"


# ── 2.2 Rescue tiers ─────────────────────────────────────────────────────


def test_tiers_are_the_readers_after_the_primary() -> None:
    assert tiers_after("pdf_inspector", ("pdf_inspector", "liteparse", "pypdf")) == (
        "liteparse",
        "pypdf",
    )
    assert tiers_after("pdf_inspector", ("pdf_inspector",)) == ()
    assert tiers_after("pypdf", ("pdf_inspector", "liteparse")) == ()  # primary not in the list


def test_a_bare_adapter_keeps_the_liteparse_then_pypdf_chain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _silent_empty(monkeypatch)
    lite = _seed(monkeypatch, "liteparse", ["lite one", "lite two"])
    pypdf = _seed(monkeypatch, "pypdf", ["must not run"])
    documents = PdfInspectorReader().load_data(file=_pdf(tmp_path))
    assert [doc.text for doc in documents] == ["lite one", "lite two"]
    assert (lite, pypdf) == (["liteparse"], [])


def test_a_custom_list_retries_with_pypdfium2_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Mutation check: hard-coding ``liteparse`` in the adapter fails this test."""
    _silent_empty(monkeypatch)
    monkeypatch.setitem(sys.modules, "pypdfium2", SimpleNamespace())  # installed, for the probe
    lite = _seed(monkeypatch, "liteparse", ["lite must not run"])
    pypdf = _seed(monkeypatch, "pypdf", ["pypdf must not run"])
    pdfium = _seed(monkeypatch, "pypdfium2", ["pdfium one", "pdfium two"])
    reader = build_pdf_reader(
        "pdf_inspector",
        SimpleNamespace(pdf_readers=("pdf_inspector", "pypdfium2"), ocr_fallback_enabled=False),
    )
    documents = reader.load_data(file=_pdf(tmp_path))
    assert [doc.text for doc in documents] == ["pdfium one", "pdfium two"]
    assert {doc.metadata["extraction_fallback_backend"] for doc in documents} == {"pypdfium2"}
    assert (lite, pypdf, pdfium) == ([], [], ["pypdfium2"])


def test_a_list_of_one_runs_no_tier_and_keeps_the_flagged_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _silent_empty(monkeypatch, pages=3)
    lite = _seed(monkeypatch, "liteparse", ["must not run"])
    pypdf = _seed(monkeypatch, "pypdf", ["must not run"])
    reader = build_pdf_reader(
        "pdf_inspector",
        SimpleNamespace(pdf_readers=("pdf_inspector",), ocr_fallback_enabled=False),
    )
    documents = reader.load_data(file=_pdf(tmp_path))
    assert len(documents) == 1 and documents[0].text == ""
    assert documents[0].metadata["pages_needing_ocr"] == 3
    assert "extraction_fallback_backend" not in documents[0].metadata
    assert (lite, pypdf) == ([], [])


def test_the_default_list_gives_the_default_tiers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _silent_empty(monkeypatch)
    _seed(monkeypatch, "liteparse", [""])
    _seed(monkeypatch, "pypdf", ["pypdf one"])
    reader = build_pdf_reader(
        "pdf_inspector",
        SimpleNamespace(
            pdf_readers=("pdf_inspector", "liteparse", "pypdf"), ocr_fallback_enabled=False
        ),
    )
    documents = reader.load_data(file=_pdf(tmp_path))
    assert documents[0].metadata["extraction_fallback_backend"] == "pypdf"


def test_a_tier_exception_hands_over_to_the_next_tier(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _seed(monkeypatch, "liteparse", ValueError("broken"))
    _seed(monkeypatch, "pypdf", ["pypdf one"])
    recovered, tier = rescue_pages(_pdf(tmp_path), ("liteparse", "pypdf"))
    assert (recovered, tier) == ([(1, "1", "pypdf one")], "pypdf")


def test_the_last_tier_exception_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _seed(monkeypatch, "liteparse", [""])
    _seed(monkeypatch, "pypdf", RuntimeError("pypdf crashed"))
    with pytest.raises(RuntimeError, match="pypdf crashed"):
        rescue_pages(_pdf(tmp_path), ("liteparse", "pypdf"))


def test_an_uninstalled_last_tier_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    assert rescue_pages(_pdf(tmp_path), ("pypdfium2",)) == ([], None)


def test_the_primary_readers_exception_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stub = _stub_pdf_inspector(monkeypatch, "text")
    stub.process_pdf.side_effect = RuntimeError("pdf-inspector crashed")
    _seed(monkeypatch, "liteparse", ["must not run"])
    with pytest.raises(RuntimeError, match="pdf-inspector crashed"):
        PdfInspectorReader().load_data(file=_pdf(tmp_path))
