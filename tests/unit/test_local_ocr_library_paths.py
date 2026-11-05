"""The local OCR tier finds its own PDFium and ONNX Runtime libraries (issue #175).

pdf-inspector loads two shared libraries named by ``PDFIUM_LIB_PATH`` and
``ORT_DYLIB_PATH``. The ``pp-ocrv6-small`` backend sets a variable from the
copy bundled in the running environment when the variable is unset or empty.
A value the user set is never replaced. The tests use fake package folders and
a stub ``pdf_inspector``; nothing loads a real library.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from omrs.integrations.pdf.local_ocr import pp_ocrv6_small
from omrs.integrations.pdf.local_ocr.pp_ocrv6_small import BACKEND, export_library_paths

PDFIUM = "PDFIUM_LIB_PATH"
ORT = "ORT_DYLIB_PATH"


def _fake_packages(
    monkeypatch: pytest.MonkeyPatch, root: Path, *, pdfium: str | None, ort: str | None
) -> tuple[Path, Path]:
    """Point the package lookup at folders under *root*; create the named files."""
    lite = root / "liteparse"
    capi = root / "onnxruntime"
    (capi / "capi").mkdir(parents=True)
    lite.mkdir()
    if pdfium:
        (lite / pdfium).write_bytes(b"")
    if ort:
        (capi / "capi" / ort).write_bytes(b"")
    found = {"liteparse": lite, "onnxruntime": capi}
    monkeypatch.setattr(
        pp_ocrv6_small,
        "find_spec",
        lambda name: SimpleNamespace(submodule_search_locations=[str(found[name])]),
    )
    return lite, capi


def test_both_variables_are_set_from_the_bundled_libraries(monkeypatch, tmp_path) -> None:
    lite, capi = _fake_packages(
        monkeypatch, tmp_path, pdfium="libpdfium.dylib", ort="libonnxruntime.1.28.0.dylib"
    )

    export_library_paths()

    assert os.environ[PDFIUM] == str(lite / "libpdfium.dylib")
    assert os.environ[ORT] == str(capi / "capi" / "libonnxruntime.1.28.0.dylib")


def test_a_value_the_user_set_is_kept(monkeypatch, tmp_path) -> None:
    _fake_packages(
        monkeypatch, tmp_path, pdfium="libpdfium.dylib", ort="libonnxruntime.1.28.0.dylib"
    )
    monkeypatch.setenv(PDFIUM, "/user/choice/libpdfium.dylib")

    export_library_paths()

    assert os.environ[PDFIUM] == "/user/choice/libpdfium.dylib"
    assert os.environ[ORT].endswith("libonnxruntime.1.28.0.dylib")


def test_an_empty_value_counts_as_unset(monkeypatch, tmp_path) -> None:
    lite, _ = _fake_packages(
        monkeypatch, tmp_path, pdfium="libpdfium.dylib", ort="libonnxruntime.1.28.0.dylib"
    )
    monkeypatch.setenv(PDFIUM, "")

    export_library_paths()

    assert os.environ[PDFIUM] == str(lite / "libpdfium.dylib")


def test_a_missing_library_leaves_its_variable_unset(monkeypatch, tmp_path) -> None:
    _fake_packages(monkeypatch, tmp_path, pdfium=None, ort="libonnxruntime.1.28.0.dylib")

    export_library_paths()

    assert PDFIUM not in os.environ
    assert ORT in os.environ


def test_the_provider_library_is_not_taken_for_the_runtime(monkeypatch, tmp_path) -> None:
    _fake_packages(monkeypatch, tmp_path, pdfium=None, ort="libonnxruntime_providers_shared.so")

    export_library_paths()

    assert ORT not in os.environ


def test_a_package_that_is_not_installed_leaves_its_variable_unset(monkeypatch) -> None:
    monkeypatch.setattr(pp_ocrv6_small, "find_spec", lambda name: None)

    export_library_paths()

    assert PDFIUM not in os.environ
    assert ORT not in os.environ


def test_one_info_line_names_each_variable_that_was_set(monkeypatch, tmp_path, caplog) -> None:
    _fake_packages(
        monkeypatch, tmp_path, pdfium="libpdfium.dylib", ort="libonnxruntime.1.28.0.dylib"
    )
    monkeypatch.setenv(ORT, "/user/choice/libonnxruntime.dylib")

    with caplog.at_level(logging.INFO, logger=pp_ocrv6_small.logger.name):
        export_library_paths()
        export_library_paths()

    lines = [r.getMessage() for r in caplog.records if PDFIUM in r.getMessage()]
    assert len(lines) == 1
    assert not any(ORT in r.getMessage() for r in caplog.records)


def test_read_pages_sets_the_variables_before_the_library_call(monkeypatch, tmp_path) -> None:
    lite, _ = _fake_packages(
        monkeypatch, tmp_path, pdfium="libpdfium.dylib", ort="libonnxruntime.1.28.0.dylib"
    )
    seen: dict[str, str | None] = {}

    def _process(path, **kwargs):
        seen["pdfium"] = os.environ.get(PDFIUM)
        return SimpleNamespace(pages=[])

    stub = SimpleNamespace(process_pdf_with_ocr=_process)
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)
    settings = SimpleNamespace(ocr_local_model_directory="", ocr_local_offline=False)

    BACKEND.read_pages(tmp_path / "a.pdf", [1], settings=settings)

    assert seen["pdfium"] == str(lite / "libpdfium.dylib")


def test_identity_sets_the_variables_before_the_library_call(monkeypatch, tmp_path) -> None:
    lite, _ = _fake_packages(
        monkeypatch, tmp_path, pdfium="libpdfium.dylib", ort="libonnxruntime.1.28.0.dylib"
    )
    seen: dict[str, str | None] = {}

    def _process(path, **kwargs):
        seen["pdfium"] = os.environ.get(PDFIUM)
        return SimpleNamespace(pages=[])

    stub = SimpleNamespace(process_pdf_with_ocr=_process)
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)
    settings = SimpleNamespace(ocr_local_model_directory="", ocr_local_offline=False)

    BACKEND.identity(settings)

    assert seen["pdfium"] == str(lite / "libpdfium.dylib")
