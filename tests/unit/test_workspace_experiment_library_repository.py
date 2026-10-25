"""SQLite store for experiment projects and notebooks (experiments-in-web-workspace task 2.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from omrs.core.workspace import experiment_library as core
from omrs.core.workspace.experiment_library import ExperimentLibraryRepository
from omrs.integrations.workspace_sqlite import SqliteWorkspaceRepository
from omrs.integrations.workspace_sqlite import experiment_library as store
from omrs.integrations.workspace_sqlite.experiment_library import (
    DuplicateError,
    SqliteExperimentLibrary,
)

FOLDER = "01-first-2026-01-01"


@pytest.fixture
def library(tmp_path: Path) -> SqliteExperimentLibrary:
    path = tmp_path / "app.sqlite3"
    SqliteWorkspaceRepository(path)
    return SqliteExperimentLibrary(path, clock=lambda: datetime(2026, 10, 25, tzinfo=UTC))


def test_implements_the_protocol(library: SqliteExperimentLibrary) -> None:
    assert isinstance(library, ExperimentLibraryRepository)


def test_limits_match_the_core_contract() -> None:
    assert store.MAX_PROJECT_NAME == core.MAX_PROJECT_NAME
    assert store.MAX_NOTEBOOK_NAME == core.MAX_NOTEBOOK_NAME


def test_add_list_get_and_remove_projects(library: SqliteExperimentLibrary) -> None:
    first = library.add_project(" OMRS ", "/work/omrs")
    second = library.add_project("Other", "/work/other")
    assert first["name"] == "OMRS"
    assert first["added_at"] == "2026-10-25T00:00:00+00:00"
    assert set(first) == {"project_id", "name", "root", "added_at"}
    assert [p["project_id"] for p in library.list_projects()] == [
        first["project_id"],
        second["project_id"],
    ]
    assert library.get_project(first["project_id"]) == first
    library.remove_project(first["project_id"])
    assert [p["name"] for p in library.list_projects()] == ["Other"]
    with pytest.raises(KeyError):
        library.get_project(first["project_id"])


def test_a_second_project_with_the_same_root_is_a_duplicate(
    library: SqliteExperimentLibrary,
) -> None:
    library.add_project("OMRS", "/work/omrs")
    with pytest.raises(DuplicateError):
        library.add_project("Again", "/work/omrs")
    assert len(library.list_projects()) == 1


def test_duplicate_error_is_a_value_error() -> None:
    assert issubclass(DuplicateError, ValueError)


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_bad_project_names_are_refused(library: SqliteExperimentLibrary, name: str) -> None:
    with pytest.raises(ValueError):
        library.add_project(name, "/work/omrs")


def test_unknown_project_ids_raise_key_error(library: SqliteExperimentLibrary) -> None:
    with pytest.raises(KeyError):
        library.remove_project("nope")


def test_create_rename_and_delete_notebooks(library: SqliteExperimentLibrary) -> None:
    notebook = library.create_notebook("Paper 1")
    assert notebook == {
        "notebook_id": notebook["notebook_id"],
        "name": "Paper 1",
        "created_at": "2026-10-25T00:00:00+00:00",
        "entry_count": 0,
    }
    renamed = library.rename_notebook(notebook["notebook_id"], "Paper 2")
    assert renamed["name"] == "Paper 2"
    assert [n["name"] for n in library.list_notebooks()] == ["Paper 2"]
    library.delete_notebook(notebook["notebook_id"])
    assert library.list_notebooks() == []


def test_notebook_names_are_unique(library: SqliteExperimentLibrary) -> None:
    first = library.create_notebook("Paper 1")
    other = library.create_notebook("Paper 2")
    with pytest.raises(DuplicateError):
        library.create_notebook("Paper 1")
    with pytest.raises(DuplicateError):
        library.rename_notebook(other["notebook_id"], "Paper 1")
    assert library.rename_notebook(first["notebook_id"], "Paper 1")["name"] == "Paper 1"


def test_unknown_notebook_ids_raise_key_error(library: SqliteExperimentLibrary) -> None:
    with pytest.raises(KeyError):
        library.rename_notebook("nope", "x")
    with pytest.raises(KeyError):
        library.delete_notebook("nope")
    with pytest.raises(KeyError):
        library.list_entries("nope")


def test_add_and_remove_entries(library: SqliteExperimentLibrary) -> None:
    project = library.add_project("OMRS", "/work/omrs")["project_id"]
    notebook = library.create_notebook("Paper 1")["notebook_id"]
    entry = library.add_entry(notebook, project, FOLDER)
    assert entry == {
        "notebook_id": notebook,
        "project_id": project,
        "folder": FOLDER,
        "added_at": "2026-10-25T00:00:00+00:00",
    }
    assert library.add_entry(notebook, project, FOLDER) == entry  # adding again keeps one
    assert library.list_entries(notebook) == [
        {"project_id": project, "folder": FOLDER, "added_at": entry["added_at"]}
    ]
    assert library.list_notebooks()[0]["entry_count"] == 1
    library.remove_entry(notebook, project, FOLDER)
    assert library.list_entries(notebook) == []
    with pytest.raises(KeyError):
        library.remove_entry(notebook, project, FOLDER)


def test_an_entry_needs_a_known_notebook_and_project(library: SqliteExperimentLibrary) -> None:
    project = library.add_project("OMRS", "/work/omrs")["project_id"]
    notebook = library.create_notebook("Paper 1")["notebook_id"]
    with pytest.raises(KeyError):
        library.add_entry("nope", project, FOLDER)
    with pytest.raises(KeyError):
        library.add_entry(notebook, "nope", FOLDER)


def test_removing_a_project_removes_its_entries(library: SqliteExperimentLibrary) -> None:
    kept = library.add_project("Kept", "/work/kept")["project_id"]
    gone = library.add_project("Gone", "/work/gone")["project_id"]
    notebook = library.create_notebook("Paper 1")["notebook_id"]
    library.add_entry(notebook, kept, FOLDER)
    library.add_entry(notebook, gone, FOLDER)
    library.remove_project(gone)
    assert [e["project_id"] for e in library.list_entries(notebook)] == [kept]


def test_deleting_a_notebook_removes_its_entries(
    library: SqliteExperimentLibrary, tmp_path: Path
) -> None:
    project = library.add_project("OMRS", "/work/omrs")["project_id"]
    notebook = library.create_notebook("Paper 1")["notebook_id"]
    library.add_entry(notebook, project, FOLDER)
    library.delete_notebook(notebook)
    again = library.create_notebook("Paper 1")["notebook_id"]
    assert library.list_entries(again) == []
    assert library.list_projects()[0]["project_id"] == project  # the project stays


def test_another_spelling_of_a_stored_root_is_a_duplicate(
    library: SqliteExperimentLibrary, tmp_path: Path
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    library.add_project("Real", str(real))
    with pytest.raises(DuplicateError):
        library.add_project("Alias", str(alias))
    assert len(library.list_projects()) == 1


def test_a_stored_root_that_is_gone_does_not_block_a_new_project(
    library: SqliteExperimentLibrary, tmp_path: Path
) -> None:
    library.add_project("Gone", str(tmp_path / "gone"))
    other = tmp_path / "other"
    other.mkdir()
    assert library.add_project("Other", str(other))["root"] == str(other)
