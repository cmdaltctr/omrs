"""Project path check for experiment projects (experiments-in-web-workspace D1, task 2.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from omrs.core.workspace.experiment_library import (
    ProjectPathError,
    check_project_path,
    project_experiments,
)


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "omrs"
    (root / "experiments").mkdir(parents=True)
    return root


def test_valid_project_returns_the_resolved_root(tmp_path: Path) -> None:
    root = _project(tmp_path)
    assert check_project_path(str(root)) == root.resolve()


def test_link_to_the_project_resolves_to_the_real_folder(tmp_path: Path) -> None:
    root = _project(tmp_path)
    link = tmp_path / "alias"
    link.symlink_to(root, target_is_directory=True)
    assert check_project_path(str(link)) == root.resolve()


@pytest.mark.parametrize("path", ["", "   ", "relative/omrs", "omrs"])
def test_empty_or_relative_paths_are_refused(path: str) -> None:
    with pytest.raises(ProjectPathError, match="absolute"):
        check_project_path(path)


def test_a_nul_character_is_refused() -> None:
    with pytest.raises(ProjectPathError):
        check_project_path("/work/om\x00rs")


def test_a_missing_folder_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ProjectPathError, match="does not exist"):
        check_project_path(str(tmp_path / "missing"))


def test_a_file_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(ProjectPathError, match="not a folder"):
        check_project_path(str(target))


def test_a_folder_without_experiments_names_the_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ProjectPathError, match="`experiments` directory"):
        check_project_path(str(tmp_path))


def test_an_experiments_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / "experiments").write_text("x", encoding="utf-8")
    with pytest.raises(ProjectPathError, match="not a directory"):
        check_project_path(str(tmp_path))


def test_an_experiments_link_that_leaves_the_project_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "omrs"
    root.mkdir()
    (root / "experiments").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProjectPathError, match="outside the project"):
        check_project_path(str(root))


def test_an_experiments_link_inside_the_project_is_kept(tmp_path: Path) -> None:
    root = tmp_path / "omrs"
    (root / "research" / "runs").mkdir(parents=True)
    (root / "experiments").symlink_to(root / "research" / "runs", target_is_directory=True)
    assert check_project_path(str(root)) == root.resolve()


def test_refusal_messages_do_not_repeat_the_path(tmp_path: Path) -> None:
    with pytest.raises(ProjectPathError) as caught:
        check_project_path(str(tmp_path / "missing"))
    assert str(tmp_path) not in str(caught.value)


def test_project_experiments_reports_the_directory_or_none(tmp_path: Path) -> None:
    root = _project(tmp_path)
    assert project_experiments(str(root)) == (root / "experiments").resolve()
    (root / "experiments").rmdir()
    assert project_experiments(str(root)) is None
    assert project_experiments(str(tmp_path / "gone")) is None
