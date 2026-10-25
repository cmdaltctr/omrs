"""Experiment projects and notebooks of the web workspace (experiments-in-web-workspace D1, D3).

A project is a folder that holds an ``experiments/`` directory. The user adds
it from the browser, so the path check here is a trust decision like
``omrs web --root``. The workspace database keeps only the user's choices
(projects, notebooks and notebook entries). The experiment folders on disk stay
the record, and nothing here writes to them.

Composition injects an :class:`ExperimentLibraryRepository`. Records are plain
dictionaries that match the JSON the HTTP routes return.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

#: The directory a project folder must hold.
EXPERIMENTS_DIR = "experiments"
#: Longest project name, in characters.
MAX_PROJECT_NAME = 100
#: Longest notebook name, in characters.
MAX_NOTEBOOK_NAME = 100
#: Longest project path, in characters.
MAX_PROJECT_PATH = 4096
#: Longest experiment folder name, in characters.
MAX_FOLDER_NAME = 255
#: The id prefix of the notebook that the API makes for each project.
PROJECT_NOTEBOOK_PREFIX = "project:"


class ProjectPathError(ValueError):
    """The path cannot be an experiment project. Nothing was stored.

    The message does not repeat the path, so an error response shows no
    folder names that the request did not already hold.
    """


def check_project_path(path: str) -> Path:
    """Return the resolved project folder, or refuse the path (design D1).

    Args:
        path: The absolute path the user gave.

    Returns:
        The real path of the project folder.

    Raises:
        ProjectPathError: The path is not absolute, does not exist, is not a
            folder, has no ``experiments`` directory, or that directory
            resolves outside the project folder.
    """
    text = path.strip()
    if "\x00" in text:
        raise ProjectPathError("The project path holds a character that is not allowed.")
    candidate = Path(text)
    if not text or not candidate.is_absolute():
        raise ProjectPathError("The project path must be absolute, for example /work/omrs.")
    try:
        root = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ProjectPathError("The project folder does not exist.") from None
    if not root.is_dir():
        raise ProjectPathError("The project path is not a folder.")
    entry = root / EXPERIMENTS_DIR
    try:
        experiments = entry.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ProjectPathError(
            f"The project folder has no `{EXPERIMENTS_DIR}` directory."
        ) from None
    if not experiments.is_dir():
        raise ProjectPathError(f"The `{EXPERIMENTS_DIR}` entry is not a directory.")
    if experiments == root or not experiments.is_relative_to(root):
        raise ProjectPathError(
            f"The `{EXPERIMENTS_DIR}` directory links to a place outside the project folder."
        )
    return root


def project_experiments(root: str) -> Path | None:
    """Check a stored project again and return its resolved ``experiments`` directory.

    Args:
        root: The stored project path.

    Returns:
        The directory, or None when the project is no longer available.
    """
    try:
        resolved = check_project_path(root)
    except ProjectPathError:
        return None
    return (resolved / EXPERIMENTS_DIR).resolve()


@runtime_checkable
class ExperimentLibraryRepository(Protocol):
    """Persistence for experiment projects, user notebooks and notebook entries.

    An unknown project, notebook or entry raises ``KeyError``. An empty or too
    long name raises ``ValueError``. A second project with the same root, or a
    second notebook with the same name, raises the store's duplicate error, a
    ``ValueError`` subclass.
    """

    def list_projects(self) -> list[dict[str, Any]]:
        """Return every project ``{project_id, name, root, added_at}``, oldest first."""
        ...

    def add_project(self, name: str, root: str) -> dict[str, Any]:
        """Store a project. *root* is the resolved path from :func:`check_project_path`."""
        ...

    def get_project(self, project_id: str) -> dict[str, Any]:
        """Return one project."""
        ...

    def remove_project(self, project_id: str) -> None:
        """Remove a project and its entries in user notebooks. No file changes."""
        ...

    def list_notebooks(self) -> list[dict[str, Any]]:
        """Return every user notebook ``{notebook_id, name, created_at, entry_count}``."""
        ...

    def create_notebook(self, name: str) -> dict[str, Any]:
        """Create a user notebook."""
        ...

    def rename_notebook(self, notebook_id: str, name: str) -> dict[str, Any]:
        """Rename a user notebook."""
        ...

    def delete_notebook(self, notebook_id: str) -> None:
        """Delete a user notebook and its entries."""
        ...

    def add_entry(self, notebook_id: str, project_id: str, folder: str) -> dict[str, Any]:
        """Add one experiment to a notebook. Adding it again returns the stored entry."""
        ...

    def remove_entry(self, notebook_id: str, project_id: str, folder: str) -> None:
        """Remove one entry from a notebook."""
        ...

    def list_entries(self, notebook_id: str) -> list[dict[str, Any]]:
        """Return the entries ``{project_id, folder, added_at}`` of a notebook, oldest first."""
        ...
