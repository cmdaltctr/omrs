"""Projects and notebooks as the web workspace shows them (experiments-in-web-workspace D2, D5).

Every project is also a notebook of its experiments, with the id
``project:<project_id>``. It is not stored and cannot be renamed, deleted or
changed. User notebooks and their entries come from the injected
:class:`~omrs.core.workspace.experiment_library.ExperimentLibraryRepository`.
An entry whose folder is no longer detected is shown as missing and is not
removed on its own.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omrs.core.workspace.experiment_library import (
    EXPERIMENTS_DIR,
    PROJECT_NOTEBOOK_PREFIX,
    ExperimentLibraryRepository,
    ProjectPathError,
    check_project_path,
    project_experiments,
)
from omrs.core.workspace.experiment_pages import (
    ExperimentNotFoundError,
    ExperimentRefusedError,
    check_name,
    count_experiments,
    experiment_map,
    library,
)

#: The project-level finding of a project whose folders cannot be read.
UNREADABLE_FINDING: dict[str, Any] = {
    "severity": "error",
    "code": "project-unreadable",
    "folder": None,
    "message": "The experiments folder of this project, or a folder in it, cannot be read.",
}


def _unavailable(project: dict[str, Any]) -> dict[str, Any]:
    return {**project, "available": False, "experiment_count": None}


def project_view(project: dict[str, Any]) -> dict[str, Any]:
    """Check a stored project again and add ``available`` and ``experiment_count``.

    A project whose folders cannot be read is unavailable, so one bad project
    never breaks a listing.
    """
    experiments = project_experiments(project["root"])
    if experiments is None:
        return _unavailable(project)
    try:
        count = count_experiments(experiments)
    except OSError:
        return _unavailable(project)
    return {**project, "available": True, "experiment_count": count}


def project_listing(project: dict[str, Any]) -> dict[str, Any]:
    """Return ``{project, experiments, reserved, findings}`` for a stored project.

    An unavailable project lists nothing. A project that cannot be read lists
    nothing and has one project-level finding without a path.
    """
    experiments = project_experiments(project["root"])
    if experiments is None:
        return {"project": _unavailable(project), "experiments": [], "reserved": [], "findings": []}
    try:
        body = library(experiments)
    except OSError:
        return {
            "project": _unavailable(project),
            "experiments": [],
            "reserved": [],
            "findings": [dict(UNREADABLE_FINDING)],
        }
    view = {**project, "available": True, "experiment_count": len(body["experiments"])}
    return {"project": view, **body}


def check_new_project(path: str) -> tuple[Path, int]:
    """Check a path to add and count its experiments, before anything is stored.

    Returns:
        The resolved project folder and its experiment count.

    Raises:
        ProjectPathError: The path check of design D1 fails, or the folders
            cannot be read.
    """
    root = check_project_path(path)
    try:
        return root, count_experiments((root / EXPERIMENTS_DIR).resolve())
    except OSError:
        raise ProjectPathError(
            "The experiments folder of this project, or a folder in it, cannot be read."
        ) from None


def _project_notebook(project: dict[str, Any]) -> dict[str, Any]:
    view = project_view(project)
    return {
        "notebook_id": PROJECT_NOTEBOOK_PREFIX + project["project_id"],
        "name": project["name"],
        "kind": "project",
        "project_id": project["project_id"],
        "entry_count": view["experiment_count"] or 0,
        "created_at": None,
    }


def _user_notebook(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "notebook_id": row["notebook_id"],
        "name": row["name"],
        "kind": "user",
        "project_id": None,
        "entry_count": row["entry_count"],
        "created_at": row["created_at"],
    }


def list_notebooks(repo: ExperimentLibraryRepository) -> list[dict[str, Any]]:
    """Return the project notebooks first, then the user notebooks."""
    projects = [_project_notebook(project) for project in repo.list_projects()]
    return projects + [_user_notebook(row) for row in repo.list_notebooks()]


def user_notebook(repo: ExperimentLibraryRepository, notebook_id: str) -> dict[str, Any]:
    """Return one user notebook.

    Raises:
        ExperimentRefusedError: The id names a project notebook.
        KeyError: No user notebook has this id.
    """
    refuse_project_notebook(notebook_id)
    for row in repo.list_notebooks():
        if row["notebook_id"] == notebook_id:
            return _user_notebook(row)
    raise KeyError(notebook_id)


def refuse_project_notebook(notebook_id: str) -> None:
    """Refuse a change to a project notebook.

    Raises:
        ExperimentRefusedError: The id names a project notebook.
    """
    if notebook_id.startswith(PROJECT_NOTEBOOK_PREFIX):
        raise ExperimentRefusedError("A project notebook cannot be renamed, deleted or changed.")


class _Projects:
    """Scans each project at most once while one notebook is built."""

    def __init__(self, repo: ExperimentLibraryRepository) -> None:
        self._repo = repo
        self._maps: dict[str, dict[str, dict[str, Any]]] = {}

    def experiments(self, project_id: str) -> dict[str, dict[str, Any]]:
        if project_id not in self._maps:
            project = self._repo.get_project(project_id)
            directory = project_experiments(project["root"])
            try:
                found = {} if directory is None else experiment_map(directory)
            except OSError:
                found = {}  # an unreadable project shows its entries as missing
            self._maps[project_id] = found
        return self._maps[project_id]


def _entry(project: dict[str, Any], folder: str, added_at: str, experiment: Any) -> dict[str, Any]:
    return {
        "project_id": project["project_id"],
        "project_name": project["name"],
        "folder": folder,
        "added_at": added_at,
        "missing": experiment is None,
        "experiment": experiment,
    }


def get_notebook(repo: ExperimentLibraryRepository, notebook_id: str) -> dict[str, Any]:
    """Return ``{notebook, entries}`` for a project or user notebook.

    Raises:
        KeyError: No notebook or project has this id.
    """
    if notebook_id.startswith(PROJECT_NOTEBOOK_PREFIX):
        project = repo.get_project(notebook_id.removeprefix(PROJECT_NOTEBOOK_PREFIX))
        experiments = _Projects(repo).experiments(project["project_id"])
        entries = [
            _entry(project, folder, project["added_at"], view)
            for folder, view in experiments.items()
        ]
        return {"notebook": _project_notebook(project), "entries": entries}
    notebook = user_notebook(repo, notebook_id)
    projects = {project["project_id"]: project for project in repo.list_projects()}
    scans = _Projects(repo)
    entries = []
    for row in repo.list_entries(notebook_id):
        project = projects[row["project_id"]]
        view = scans.experiments(row["project_id"]).get(row["folder"])
        entries.append(_entry(project, row["folder"], row["added_at"], view))
    return {"notebook": notebook, "entries": entries}


def add_entry(
    repo: ExperimentLibraryRepository, notebook_id: str, project_id: str, folder: str
) -> dict[str, Any]:
    """Add a listed experiment to a user notebook and return the entry.

    Raises:
        ExperimentRefusedError: The id names a project notebook, or the folder
            name is not allowed.
        ExperimentNotFoundError: The project lists no experiment with this folder.
        KeyError: The notebook or the project does not exist.
    """
    refuse_project_notebook(notebook_id)
    check_name(folder, "folder name")
    project = repo.get_project(project_id)
    view = _Projects(repo).experiments(project_id).get(folder)
    if view is None:
        raise ExperimentNotFoundError(folder)
    stored = repo.add_entry(notebook_id, project_id, folder)
    return _entry(project, folder, stored["added_at"], view)


def remove_entry(
    repo: ExperimentLibraryRepository, notebook_id: str, project_id: str, folder: str
) -> None:
    """Remove one entry from a user notebook.

    Raises:
        ExperimentRefusedError: The id names a project notebook.
        KeyError: The notebook has no such entry.
    """
    refuse_project_notebook(notebook_id)
    repo.remove_entry(notebook_id, project_id, folder)


def experiments_of(project: dict[str, Any]) -> Path:
    """Return the resolved ``experiments`` directory of an available project.

    Raises:
        ExperimentNotFoundError: The project is not available.
    """
    directory = project_experiments(project["root"])
    if directory is None:
        raise ExperimentNotFoundError(project["project_id"])
    return directory
