"""The Indra OCR local backend (change local-ocr-backends, task 7.2, design D19).

Every test runs on a fake ``indra_ocr`` package and a fake ``pypdfium2`` in
``sys.modules``, so no test needs the ``local-ocr-indra`` extra, loads weights or
renders a real PDF. The fake ``model_dir`` follows the library's lookup order
(argument, then ``INDRA_OCR_MODEL_DIR``) and fails where the library would
download.
"""

from __future__ import annotations

import importlib.machinery
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from omrs.core import reading_parts
from omrs.core.settings import EffectiveSettings
from omrs.integrations.pdf import page_routing
from omrs.integrations.pdf.local_ocr import chain, registry

MODEL = "datalab-to/indra-ocr@bd02167fdf2005a19962cc15188f8496a2c87d3b"
#: ``indra_ocr.models`` facts of indra-ocr 1.1.2.
HF_REPO = "datalab-to/indra-ocr"
HF_REVISION = "v1.1.0"
FILES = ("det.onnx", "rec.onnx", "order.onnx", "meta.json")
ARABIC = "ب" * 300
BENGALI = "ক" * 300
#: A US Letter page in points: the long side is the height.
PAGE_POINTS = (612.0, 792.0)


class _FakePdfium:
    """A ``pypdfium2`` stand-in that records each render call."""

    def __init__(self) -> None:
        self.renders: list[dict] = []
        self.closed = 0
        fake = self

        class _Page:
            def get_size(self):
                return PAGE_POINTS

            def render(self, *, scale, grayscale):
                fake.renders.append({"scale": scale, "grayscale": grayscale})
                width, height = (round(side * scale) for side in PAGE_POINTS)
                return SimpleNamespace(to_numpy=lambda: np.zeros((height, width, 1), np.uint8))

        class PdfDocument:
            def __init__(self, path) -> None:
                self.path = path

            def __len__(self) -> int:
                return 10

            def __getitem__(self, index):
                return _Page()

            def close(self) -> None:
                fake.closed += 1

        self.module = types.ModuleType("pypdfium2")
        self.module.PdfDocument = PdfDocument


class _FakeIndra:
    """An ``indra_ocr`` stand-in: one list of ``(text, conf)`` lines per page read."""

    def __init__(self, *pages) -> None:
        self.pages = list(pages)
        self.folders: list[Path] = []
        self.images: list[np.ndarray] = []
        fake = self

        def model_dir(path=None, revision=None, math=False):
            import os

            path = path or os.environ.get("INDRA_OCR_MODEL_DIR")
            if not path:
                raise AssertionError("the real model_dir would download the weights here")
            # As the library: every file but the optional order.onnx must be there.
            missing = [f for f in FILES if f != "order.onnx" and not (Path(path) / f).exists()]
            if missing:
                raise OSError(f"the model folder {path} lacks {', '.join(missing)}")
            return Path(path)

        class OrtOCR:
            def __init__(self, onnx_dir, **kwargs) -> None:
                fake.folders.append(Path(onnx_dir))

            def __call__(self, gray):
                fake.images.append(gray)
                lines = fake.pages.pop(0)
                return SimpleNamespace(
                    lines=[SimpleNamespace(text=text, conf=conf) for text, conf in lines]
                )

        module = types.ModuleType("indra_ocr")
        module.__spec__ = importlib.machinery.ModuleSpec("indra_ocr", None)
        module.OrtOCR = OrtOCR
        module.model_dir = model_dir
        module.models = SimpleNamespace(HF_REPO=HF_REPO, HF_REVISION=HF_REVISION, FILES=FILES)
        self.module = module


class _FakeHub:
    """A ``huggingface_hub`` stand-in whose cache holds *cached* (a folder) or nothing."""

    def __init__(self, cached: Path | None) -> None:
        self.calls: list[dict] = []
        fake = self

        def snapshot_download(repo_id, **kwargs):
            fake.calls.append({"repo_id": repo_id, **kwargs})
            if kwargs.get("local_files_only") is not True:
                raise AssertionError("snapshot_download would download the weights here")
            if cached is None:
                raise FileNotFoundError("not in the local cache")
            return str(cached)

        self.module = types.ModuleType("huggingface_hub")
        self.module.snapshot_download = snapshot_download


def _write_weights(folder: Path) -> Path:
    """Write the weight files the library requires into *folder*."""
    folder.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        (folder / name).write_bytes(b"")
    return folder


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    state = registry.BACKENDS.snapshot()
    chain.reset_skip_warnings()
    monkeypatch.setenv("INDRA_OCR_MODEL_DIR", str(_write_weights(tmp_path / "weights")))
    yield
    registry.BACKENDS.restore(state)
    chain.reset_skip_warnings()


@pytest.fixture
def pdfium(monkeypatch) -> _FakePdfium:
    fake = _FakePdfium()
    monkeypatch.setitem(sys.modules, "pypdfium2", fake.module)
    return fake


def _indra(monkeypatch, *pages) -> _FakeIndra:
    fake = _FakeIndra(*pages)
    monkeypatch.setitem(sys.modules, "indra_ocr", fake.module)
    return fake


def _backend():
    """A fresh backend object, so no model loaded by another test is reused."""
    from omrs.integrations.pdf.local_ocr import indra

    return type(indra.BACKEND)()


def _settings(*backends):
    return SimpleNamespace(
        ocr_local_backends=tuple(backends),
        ocr_local_cuts={},
        ocr_non_latin_routing="off",
        ocr_local_model_directory="",
        ocr_local_offline=False,
    )


# ── read_pages ─────────────────────────────────────────────────────────────


def test_read_pages_returns_one_page_per_page_with_text_from_lines(
    monkeypatch, pdfium, tmp_path
) -> None:
    _indra(monkeypatch, [("abcd", 1.0), ("ab", 0.4)], [("x y", 0.5)])

    pages = _backend().read_pages(tmp_path / "a.pdf", [3, 1], settings=_settings())

    assert [p.page for p in pages] == [1, 3]
    assert pages[0].text == "abcd\nab"
    assert pages[1].text == "x y"
    assert all(p.model == MODEL for p in pages)
    assert all(p.hosted_recommended is False for p in pages)


def test_page_confidence_is_weighted_by_characters(monkeypatch, pdfium, tmp_path) -> None:
    _indra(monkeypatch, [("abcd", 1.0), ("a b", 0.4)])

    (page,) = _backend().read_pages(tmp_path / "a.pdf", [1], settings=_settings())

    # 4 characters at 1.0 and 2 (whitespace excluded) at 0.4.
    assert page.confidence == pytest.approx((4 * 1.0 + 2 * 0.4) / 6)


def test_a_page_with_no_lines_has_empty_text_and_no_confidence(
    monkeypatch, pdfium, tmp_path
) -> None:
    _indra(monkeypatch, [])

    (page,) = _backend().read_pages(tmp_path / "a.pdf", [1], settings=_settings())

    assert (page.text, page.confidence) == ("", None)


def test_each_page_is_rendered_grey_with_a_1600_px_long_side(monkeypatch, pdfium, tmp_path) -> None:
    fake = _indra(monkeypatch, [("a", 1.0)], [("b", 1.0)])

    _backend().read_pages(tmp_path / "a.pdf", [1, 2], settings=_settings())

    assert [r["grayscale"] for r in pdfium.renders] == [True, True]
    assert pdfium.renders[0]["scale"] == pytest.approx(1600 / max(PAGE_POINTS))
    assert [image.ndim for image in fake.images] == [2, 2]
    assert [max(image.shape) for image in fake.images] == [1600, 1600]
    assert pdfium.closed == 1


def test_weights_come_from_indra_ocr_model_dir(monkeypatch, pdfium, tmp_path) -> None:
    folder = _write_weights(tmp_path / "offline-weights")
    monkeypatch.setenv("INDRA_OCR_MODEL_DIR", str(folder))
    fake = _indra(monkeypatch, [("a", 1.0)])

    _backend().read_pages(tmp_path / "a.pdf", [1], settings=_settings())

    assert fake.folders == [folder]


def test_the_model_is_loaded_once_for_many_reads(monkeypatch, pdfium, tmp_path) -> None:
    fake = _indra(monkeypatch, [("a", 1.0)], [("b", 1.0)])
    backend = _backend()

    backend.read_pages(tmp_path / "a.pdf", [1], settings=_settings())
    backend.read_pages(tmp_path / "b.pdf", [1], settings=_settings())

    assert len(fake.folders) == 1


def test_read_pages_without_indra_ocr_raises_import_error(monkeypatch, pdfium, tmp_path) -> None:
    monkeypatch.setitem(sys.modules, "indra_ocr", None)

    with pytest.raises(ImportError, match="local-ocr-indra"):
        _backend().read_pages(tmp_path / "a.pdf", [1], settings=_settings())


def test_identity_names_the_pinned_model(monkeypatch) -> None:
    _indra(monkeypatch)

    assert _backend().identity(_settings()) == MODEL


def test_identity_without_indra_ocr_raises_import_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "indra_ocr", None)

    with pytest.raises(ImportError, match="local-ocr-indra"):
        _backend().identity(_settings())


def _hub(monkeypatch, cached: Path | None) -> _FakeHub:
    hub = _FakeHub(cached)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub.module)
    return hub


def _offline(offline: bool) -> SimpleNamespace:
    return SimpleNamespace(**{**vars(_settings()), "ocr_local_offline": offline})


def test_identity_is_none_when_the_weights_folder_lacks_files(monkeypatch, tmp_path) -> None:
    _indra(monkeypatch)
    hub = _hub(monkeypatch, None)
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv("INDRA_OCR_MODEL_DIR", str(tmp_path / "empty"))

    assert _backend().identity(_settings()) is None
    assert hub.calls == []


def test_identity_offline_without_a_weights_folder_is_none(monkeypatch) -> None:
    _indra(monkeypatch)
    hub = _hub(monkeypatch, None)
    monkeypatch.delenv("INDRA_OCR_MODEL_DIR", raising=False)

    assert _backend().identity(_offline(True)) is None
    assert hub.calls == []


def test_identity_reads_the_hugging_face_cache_without_a_download(monkeypatch, tmp_path) -> None:
    _indra(monkeypatch)
    hub = _hub(monkeypatch, _write_weights(tmp_path / "hf-snapshot"))
    monkeypatch.delenv("INDRA_OCR_MODEL_DIR", raising=False)

    assert _backend().identity(_offline(False)) == MODEL
    assert [(c["repo_id"], c["revision"]) for c in hub.calls] == [(HF_REPO, HF_REVISION)]
    assert all(call["local_files_only"] is True for call in hub.calls)


def test_identity_is_none_when_the_weights_are_not_cached(monkeypatch) -> None:
    _indra(monkeypatch)
    hub = _hub(monkeypatch, None)
    monkeypatch.delenv("INDRA_OCR_MODEL_DIR", raising=False)

    assert _backend().identity(_offline(False)) is None
    assert hub.calls and all(call["local_files_only"] is True for call in hub.calls)


def test_identity_is_none_when_the_cached_snapshot_lacks_files(monkeypatch, tmp_path) -> None:
    _indra(monkeypatch)
    (tmp_path / "partial").mkdir()
    _hub(monkeypatch, tmp_path / "partial")
    monkeypatch.delenv("INDRA_OCR_MODEL_DIR", raising=False)

    assert _backend().identity(_offline(False)) is None


# ── Registration, descriptor and default list ─────────────────────────────


def test_the_registry_reports_indra_installed_only_with_indra_ocr(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "indra_ocr", None)
    assert registry.BACKENDS.installed("indra") is False

    _indra(monkeypatch)
    assert registry.BACKENDS.installed("indra") is True


def test_the_descriptor_carries_the_facts_of_design_d19() -> None:
    descriptor = reading_parts.local_backend("indra")

    assert descriptor.min_confidence == 0.94
    assert descriptor.calibrated_by == "46a-local-ocr-per-backend-cuts-2026-11-06"
    assert not hasattr(descriptor, "keeps_scripts")
    assert descriptor.producer == "indra_ocr"
    assert descriptor.model == MODEL
    assert descriptor.extra == "local-ocr-indra"
    assert descriptor.probe_module == "indra_ocr"
    assert "OpenRAIL-M" in (descriptor.health.licence or "")


def test_indra_is_not_in_the_default_list() -> None:
    assert "indra" not in EffectiveSettings().ocr_local_backends
    assert "indra" not in reading_parts.DEFAULT_LOCAL_OCR_BACKENDS
    assert "indra" not in registry.DEFAULT_BACKENDS


# ── Through the chain (design D8 and D10) ──────────────────────────────────


class _PdfInspector:
    """A ``pdf_inspector`` stub for the real PP-OCRv6 backend."""

    def __init__(self, *calls) -> None:
        self.calls: list[list[int]] = []
        self._calls = list(calls)

    def process_pdf_with_ocr(self, path, **kwargs):
        self.calls.append(list(kwargs["page_numbers"]))
        pages = []
        for page, (text, conf) in self._calls.pop(0).items():
            provenance = SimpleNamespace(
                ocr_confidence=conf,
                ocr_model=SimpleNamespace(name="pp-ocrv6-small", revision="r"),
                hosted_recommended=False,
            )
            pages.append(SimpleNamespace(page_number=page, markdown=text, provenance=provenance))
        return SimpleNamespace(pages=pages)


def _pp(monkeypatch, *calls) -> _PdfInspector:
    stub = _PdfInspector(*calls)
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)
    return stub


def _read(pages, tmp_path):
    settings = _settings("indra", "pp-ocrv6-small")
    return {p.page: p for p in page_routing.local_ocr(tmp_path / "a.pdf", pages, settings=settings)}


def test_a_missing_indra_ocr_is_skipped_with_one_warning(monkeypatch, tmp_path, caplog) -> None:
    monkeypatch.setitem(sys.modules, "indra_ocr", None)
    pp = _pp(monkeypatch, {1: ("one", 0.95)}, {1: ("one", 0.95)})

    with caplog.at_level(logging.WARNING):
        first = _read([1], tmp_path)[1]
        second = _read([1], tmp_path)[1]

    assert pp.calls == [[1], [1]]
    assert first.producer == second.producer == "pdf_inspector_ocr"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, warnings
    assert "'indra'" in warnings[0]
    assert "local-ocr-indra" in warnings[0]  # the backend's own message, not an unknown name


def test_indra_keeps_an_arabic_page_at_its_cut(monkeypatch, pdfium, tmp_path) -> None:
    registry.BACKENDS.cache["indra"] = _backend()
    _indra(monkeypatch, [(ARABIC, 0.95)])
    pp = _pp(monkeypatch)

    page = _read([1], tmp_path)[1]

    assert (page.escalates, page.producer, page.model) == (False, "indra_ocr", MODEL)
    assert pp.calls == []


def test_indra_keeps_a_latin_page_above_its_cut(monkeypatch, pdfium, tmp_path) -> None:
    registry.BACKENDS.cache["indra"] = _backend()
    _indra(monkeypatch, [("a" * 300, 0.95)])
    pp = _pp(monkeypatch)

    page = _read([1], tmp_path)[1]

    assert (page.escalates, page.producer, page.reasons) == (False, "indra_ocr", ())
    assert pp.calls == []


def test_indra_keeps_a_bengali_page_above_its_cut(monkeypatch, pdfium, tmp_path) -> None:
    registry.BACKENDS.cache["indra"] = _backend()
    _indra(monkeypatch, [(BENGALI, 0.95)])
    pp = _pp(monkeypatch)

    page = _read([1], tmp_path)[1]

    assert (page.escalates, page.producer) == (False, "indra_ocr")
    assert pp.calls == []


def test_indra_passes_on_an_arabic_page_below_its_cut(monkeypatch, pdfium, tmp_path) -> None:
    registry.BACKENDS.cache["indra"] = _backend()
    _indra(monkeypatch, [(ARABIC, 0.93)])
    pp = _pp(monkeypatch, {1: ("pp text " * 10, 0.95)})

    page = _read([1], tmp_path)[1]

    assert pp.calls == [[1]]
    assert page.producer == "pdf_inspector_ocr"


def test_offline_without_a_weights_folder_refuses_before_any_download(
    monkeypatch, pdfium, tmp_path
) -> None:
    """``ocr_local_offline`` covers Indra too: no folder means no read, never a download."""
    monkeypatch.delenv("INDRA_OCR_MODEL_DIR", raising=False)
    fake = _indra(monkeypatch, [("a", 1.0)])
    settings = SimpleNamespace(**{**vars(_settings()), "ocr_local_offline": True})

    with pytest.raises(RuntimeError, match="INDRA_OCR_MODEL_DIR"):
        _backend().read_pages(tmp_path / "a.pdf", [1], settings=settings)

    assert fake.folders == []


def test_offline_with_a_weights_folder_reads(monkeypatch, pdfium, tmp_path) -> None:
    folder = _write_weights(tmp_path / "offline-weights")
    monkeypatch.setenv("INDRA_OCR_MODEL_DIR", str(folder))
    fake = _indra(monkeypatch, [("a", 1.0)])
    settings = SimpleNamespace(**{**vars(_settings()), "ocr_local_offline": True})

    _backend().read_pages(tmp_path / "a.pdf", [1], settings=settings)

    assert fake.folders == [folder]
