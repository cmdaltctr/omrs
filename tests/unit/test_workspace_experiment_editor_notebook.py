"""Notebook preparation for a Library launch (open-experiment-in-marimo D1, D4).

The converter is a fake, so no test starts a process. Each test checks the
files in the experiment folder before and after the call.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from pathlib import Path
from typing import Any

import pytest

from omrs.core.workspace import experiment_editor
from omrs.core.workspace.experiment_editor import (
    JUPYTEXT_HINT,
    NOTEBOOK_NAME,
    SOURCE_NAME,
    EditorRefusal,
    PreparedNotebook,
    needs_conversion,
    notebook_exists,
    prepare_notebook,
)

_REPO = Path(__file__).resolve().parents[2]
_CONVERTED = _REPO / "experiments" / "32-misnamed-extension-detection-2026-09-16"
_TEMPLATE = "import marimo\n\napp = marimo.App()\n"
_CONVERTED_TEXT = b"import marimo\n\n__generated_with = '0.25.1'\napp = marimo.App()\n"
_JUPYTEXT_ERROR = "Error: Converting py:percent format requires jupytext"


class _Converter:
    """Fake ``marimo convert`` that records its calls."""

    def __init__(self, returncode: int = 0, output: str = "", *, write: bool = True) -> None:
        self.returncode = returncode
        self.output = output
        self.write = write
        self.calls: list[tuple[Path, Path]] = []
        self.output_mode: int | None = None

    def __call__(self, source: Path, output: Path) -> tuple[int, str]:
        self.calls.append((source, output))
        self.output_mode = stat.S_IMODE(output.parent.stat().st_mode)
        if self.write:
            output.write_bytes(_CONVERTED_TEXT)
        return self.returncode, self.output


def _hashes(folder: Path) -> dict[str, str]:
    return {
        str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def _folder(tmp_path: Path, *, source: bool = True) -> Path:
    folder = tmp_path / "project" / "experiments" / "1-demo-2026-10-25"
    folder.mkdir(parents=True)
    (folder / "experiment.json").write_text("{}", encoding="utf-8")
    if source:
        (folder / SOURCE_NAME).write_text("# %%\nprint(1)\n", encoding="utf-8")
    return folder


def _prepare(folder: Path, scratch: Path, convert: _Converter) -> PreparedNotebook:
    return prepare_notebook(folder, convert=convert, scratch_parent=scratch, template=_TEMPLATE)


# --- notebook_exists and needs_conversion ----------------------------------------


def test_notebook_exists_is_false_when_absent(tmp_path: Path) -> None:
    assert notebook_exists(_folder(tmp_path)) is False


def test_notebook_exists_is_true_for_a_regular_file(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    (folder / NOTEBOOK_NAME).write_text(_TEMPLATE, encoding="utf-8")
    assert notebook_exists(folder) is True


def test_notebook_link_is_refused(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    target = tmp_path / "elsewhere.py"
    target.write_text(_TEMPLATE, encoding="utf-8")
    (folder / NOTEBOOK_NAME).symlink_to(target)
    with pytest.raises(EditorRefusal) as caught:
        notebook_exists(folder)
    assert caught.value.reason == "notebook_not_regular"
    assert "link" in caught.value.message
    assert str(tmp_path) not in caught.value.message


def test_notebook_folder_is_refused(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    (folder / NOTEBOOK_NAME).mkdir()
    with pytest.raises(EditorRefusal) as caught:
        notebook_exists(folder)
    assert caught.value.reason == "notebook_not_regular"


def test_needs_conversion_with_source_and_no_notebook(tmp_path: Path) -> None:
    assert needs_conversion(_folder(tmp_path)) is True


def test_needs_conversion_is_false_without_source(tmp_path: Path) -> None:
    assert needs_conversion(_folder(tmp_path, source=False)) is False


def test_needs_conversion_is_false_with_a_notebook(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    (folder / NOTEBOOK_NAME).write_text(_TEMPLATE, encoding="utf-8")
    assert needs_conversion(folder) is False


def test_needs_conversion_is_false_for_a_source_link(tmp_path: Path) -> None:
    folder = _folder(tmp_path, source=False)
    target = tmp_path / "outside.py"
    target.write_text("print(1)\n", encoding="utf-8")
    (folder / SOURCE_NAME).symlink_to(target)
    assert needs_conversion(folder) is False


# --- prepare_notebook: existing notebook -----------------------------------------


def test_existing_notebook_is_opened_unchanged(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    notebook = folder / NOTEBOOK_NAME
    notebook.write_text("# my edits\n", encoding="utf-8")
    os.utime(folder / SOURCE_NAME, (1_000, 1_000))
    before = _hashes(folder)
    convert = _Converter()
    result = _prepare(folder, tmp_path / "scratch", convert)
    assert result == PreparedNotebook(path=notebook, state="existing", source_newer=False)
    assert _hashes(folder) == before
    assert convert.calls == []
    assert not (tmp_path / "scratch").exists()


def test_existing_notebook_reports_a_newer_source(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    notebook = folder / NOTEBOOK_NAME
    notebook.write_text("# my edits\n", encoding="utf-8")
    os.utime(notebook, (1_000, 1_000))
    os.utime(folder / SOURCE_NAME, (2_000, 2_000))
    result = _prepare(folder, tmp_path / "scratch", _Converter())
    assert result.state == "existing"
    assert result.source_newer is True


def test_existing_notebook_without_source_is_not_stale(tmp_path: Path) -> None:
    folder = _folder(tmp_path, source=False)
    (folder / NOTEBOOK_NAME).write_text("# my edits\n", encoding="utf-8")
    result = _prepare(folder, tmp_path / "scratch", _Converter())
    assert result.state == "existing"
    assert result.source_newer is False


def test_prepare_refuses_a_notebook_link_and_converts_nothing(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    target = tmp_path / "elsewhere.py"
    target.write_text(_TEMPLATE, encoding="utf-8")
    (folder / NOTEBOOK_NAME).symlink_to(target)
    convert = _Converter()
    with pytest.raises(EditorRefusal) as caught:
        _prepare(folder, tmp_path / "scratch", convert)
    assert caught.value.reason == "notebook_not_regular"
    assert convert.calls == []
    assert target.read_text(encoding="utf-8") == _TEMPLATE


# --- prepare_notebook: conversion ------------------------------------------------


def test_conversion_writes_the_notebook_through_a_private_folder(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    scratch = tmp_path / "run" / "convert"
    convert = _Converter()
    result = _prepare(folder, scratch, convert)
    notebook = folder / NOTEBOOK_NAME
    assert result == PreparedNotebook(path=notebook, state="converted", source_newer=False)
    assert notebook.read_bytes() == _CONVERTED_TEXT
    [(source, output)] = convert.calls
    assert source == folder / SOURCE_NAME
    assert output.name == NOTEBOOK_NAME
    assert output.parent.parent == scratch
    assert convert.output_mode == 0o700
    assert stat.S_IMODE(scratch.stat().st_mode) == 0o700
    assert list(scratch.iterdir()) == []


def test_conversion_creates_the_notebook_exclusively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder(tmp_path)
    flags: list[int] = []
    real_open = os.open

    def spy(path: str | os.PathLike[str], flag: int, mode: int = 0o777, **kw: Any) -> int:
        if Path(path).name == NOTEBOOK_NAME and Path(path).parent == folder:
            flags.append(flag)
        return real_open(path, flag, mode, **kw)

    monkeypatch.setattr(experiment_editor.os, "open", spy)
    _prepare(folder, tmp_path / "scratch", _Converter())
    assert len(flags) == 1
    assert flags[0] & os.O_CREAT
    assert flags[0] & os.O_EXCL


def test_notebook_that_appears_during_conversion_is_kept(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    notebook = folder / NOTEBOOK_NAME

    def racing(source: Path, output: Path) -> tuple[int, str]:
        notebook.write_text("# user notebook\n", encoding="utf-8")
        output.write_bytes(_CONVERTED_TEXT)
        return 0, ""

    result = prepare_notebook(
        folder, convert=racing, scratch_parent=tmp_path / "scratch", template=_TEMPLATE
    )
    assert result.state == "existing"
    assert notebook.read_text(encoding="utf-8") == "# user notebook\n"
    assert list((tmp_path / "scratch").iterdir()) == []


def test_link_that_appears_during_conversion_is_refused(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    target = tmp_path / "elsewhere.py"
    target.write_text("# outside\n", encoding="utf-8")

    def racing(source: Path, output: Path) -> tuple[int, str]:
        (folder / NOTEBOOK_NAME).symlink_to(target)
        output.write_bytes(_CONVERTED_TEXT)
        return 0, ""

    with pytest.raises(EditorRefusal) as caught:
        prepare_notebook(
            folder, convert=racing, scratch_parent=tmp_path / "scratch", template=_TEMPLATE
        )
    assert caught.value.reason == "notebook_not_regular"
    assert target.read_text(encoding="utf-8") == "# outside\n"


def test_missing_jupytext_is_refused_and_leaves_no_file(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    before = _hashes(folder)
    scratch = tmp_path / "scratch"
    convert = _Converter(1, f"Traceback\n{_JUPYTEXT_ERROR.upper()}\n")
    with pytest.raises(EditorRefusal) as caught:
        _prepare(folder, scratch, convert)
    refusal = caught.value
    assert refusal.reason == "converter_missing"
    assert JUPYTEXT_HINT in refusal.message
    assert refusal.output_tail == convert.output
    assert _hashes(folder) == before
    assert list(scratch.iterdir()) == []


def test_other_conversion_failure_is_refused_and_leaves_no_file(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    before = _hashes(folder)
    scratch = tmp_path / "scratch"
    convert = _Converter(2, "SyntaxError: invalid syntax")
    with pytest.raises(EditorRefusal) as caught:
        _prepare(folder, scratch, convert)
    refusal = caught.value
    assert refusal.reason == "conversion_failed"
    assert refusal.message == "marimo could not convert analysis.py."
    assert refusal.output_tail == "SyntaxError: invalid syntax"
    assert _hashes(folder) == before
    assert list(scratch.iterdir()) == []


def test_jupytext_word_with_success_code_is_not_a_failure(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    result = _prepare(folder, tmp_path / "scratch", _Converter(0, "jupytext 1.17 used"))
    assert result.state == "converted"


def test_success_code_without_output_file_is_refused(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    before = _hashes(folder)
    scratch = tmp_path / "scratch"
    with pytest.raises(EditorRefusal) as caught:
        _prepare(folder, scratch, _Converter(0, "done", write=False))
    assert caught.value.reason == "conversion_failed"
    assert _hashes(folder) == before
    assert list(scratch.iterdir()) == []


def test_converter_error_still_removes_the_private_folder(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    scratch = tmp_path / "scratch"

    def broken(source: Path, output: Path) -> tuple[int, str]:
        output.write_bytes(b"partial")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        prepare_notebook(folder, convert=broken, scratch_parent=scratch, template=_TEMPLATE)
    assert list(scratch.iterdir()) == []
    assert not (folder / NOTEBOOK_NAME).exists()


def test_failed_write_removes_the_partial_notebook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder(tmp_path)

    def failing_write(fd: int, data: bytes) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(experiment_editor.os, "write", failing_write)
    with pytest.raises(OSError, match="disk full"):
        _prepare(folder, tmp_path / "scratch", _Converter())
    assert not (folder / NOTEBOOK_NAME).exists()


# --- prepare_notebook: no analysis.py --------------------------------------------


def test_folder_without_source_gets_the_template(tmp_path: Path) -> None:
    folder = _folder(tmp_path, source=False)
    convert = _Converter()
    result = _prepare(folder, tmp_path / "scratch", convert)
    notebook = folder / NOTEBOOK_NAME
    assert result == PreparedNotebook(path=notebook, state="created", source_newer=False)
    assert notebook.read_text(encoding="utf-8") == _TEMPLATE
    assert convert.calls == []
    assert not (tmp_path / "scratch").exists()


def test_template_keeps_a_notebook_that_appeared_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder(tmp_path, source=False)
    notebook = folder / NOTEBOOK_NAME
    real_open = os.open

    def racing(path: str | os.PathLike[str], flag: int, mode: int = 0o777, **kw: Any) -> int:
        if Path(path) == notebook and not notebook.exists():
            notebook.write_text("# appeared\n", encoding="utf-8")
        return real_open(path, flag, mode, **kw)

    monkeypatch.setattr(experiment_editor.os, "open", racing)
    result = _prepare(folder, tmp_path / "scratch", _Converter())
    assert result.state == "existing"
    assert notebook.read_text(encoding="utf-8") == "# appeared\n"


# --- a real converted experiment (task 5.3) --------------------------------------


def test_real_converted_experiment_only_gains_the_notebook(tmp_path: Path) -> None:
    assert (_CONVERTED / SOURCE_NAME).is_file()
    folder = tmp_path / "experiments" / _CONVERTED.name
    shutil.copytree(_CONVERTED, folder, symlinks=True)
    before = _hashes(folder)
    assert NOTEBOOK_NAME not in before
    result = _prepare(folder, tmp_path / "scratch", _Converter())
    after = _hashes(folder)
    assert result.state == "converted"
    assert set(after) - set(before) == {NOTEBOOK_NAME}
    assert {name: after[name] for name in before} == before
