"""SQLite store for experiment projects and notebooks (experiments-in-web-workspace D2, D3).

This module is an integration leaf. It does not import ``omrs.core``, so the
limits below repeat the values in ``omrs.core.workspace.experiment_library``; a
test keeps them equal. Connections enforce foreign keys (``schema.connect``),
so removing a project or a notebook removes its entries through the cascade.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from omrs.integrations.workspace_sqlite.pipeline_sql import (
    new_id,
    read_connection,
    write_transaction,
)

MAX_PROJECT_NAME = 100
MAX_NOTEBOOK_NAME = 100

_PROJECTS = "SELECT * FROM experiment_projects ORDER BY added_at, rowid"
_NOTEBOOKS = """SELECT n.*, (SELECT COUNT(*) FROM notebook_entries e
    WHERE e.notebook_id = n.notebook_id) AS entry_count
    FROM notebooks AS n"""


class DuplicateError(ValueError):
    """A project with the same root, or a notebook with the same name, already exists."""


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _bounded(text: str, limit: int, what: str) -> str:
    """Return *text* stripped, or raise ``ValueError`` when empty or over *limit*."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError(f"A {what} cannot be empty.")
    if len(cleaned) > limit:
        raise ValueError(f"A {what} can have at most {limit} characters.")
    return cleaned


def _same_folder(root: str, other: str) -> bool:
    """Return True when *root* and the stored *other* name one folder; a gone root never does."""
    try:
        return os.path.samefile(root, other)
    except OSError:
        return False


def _project(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "project_id": row["project_id"],
        "name": row["name"],
        "root": row["root"],
        "added_at": row["added_at"],
    }


def _notebook(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "notebook_id": row["notebook_id"],
        "name": row["name"],
        "created_at": row["created_at"],
        "entry_count": int(row["entry_count"]),
    }


class SqliteExperimentLibrary:
    """Reads and writes projects and notebooks in an already migrated workspace database.

    Open ``SqliteWorkspaceRepository`` on the same file first, so migration 7
    has run. Each call uses a short-lived connection.

    Args:
        path: The workspace database file.
        clock: Returns the current time; tests inject a fixed clock.
    """

    def __init__(self, path: Path, *, clock: Callable[[], datetime] = _default_clock) -> None:
        """Remember the database file and the clock."""
        self.path = Path(path)
        self._clock = clock

    def _now(self) -> str:
        return self._clock().isoformat()

    # --- projects --------------------------------------------------------

    def list_projects(self) -> list[dict[str, Any]]:
        """Return every project, oldest first."""
        with read_connection(self.path) as conn:
            return [_project(row) for row in conn.execute(_PROJECTS)]

    def add_project(self, name: str, root: str) -> dict[str, Any]:
        """Store a project with an already resolved root.

        A different spelling of a stored folder, for example another letter case
        on a case-insensitive file system, is the same folder.

        Raises:
            ValueError: If the name is empty or too long.
            DuplicateError: If a project has the same root, or a stored root
                names the same folder.
        """
        cleaned = _bounded(name, MAX_PROJECT_NAME, "project name")
        project = {"project_id": new_id(), "name": cleaned, "root": root, "added_at": self._now()}
        try:
            with write_transaction(self.path) as conn:
                stored = [row[0] for row in conn.execute("SELECT root FROM experiment_projects")]
                if any(_same_folder(root, other) for other in stored):
                    raise sqlite3.IntegrityError("same folder")
                conn.execute(
                    "INSERT INTO experiment_projects VALUES (?, ?, ?, ?)",
                    tuple(project.values()),
                )
        except sqlite3.IntegrityError:
            raise DuplicateError("This folder is already an experiment project.") from None
        return project

    def get_project(self, project_id: str) -> dict[str, Any]:
        """Return one project.

        Raises:
            KeyError: If the project does not exist.
        """
        with read_connection(self.path) as conn:
            row = conn.execute(
                "SELECT * FROM experiment_projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise KeyError(project_id)
        return _project(row)

    def remove_project(self, project_id: str) -> None:
        """Remove a project and, through the cascade, its notebook entries.

        Raises:
            KeyError: If the project does not exist.
        """
        with write_transaction(self.path) as conn:
            deleted = conn.execute(
                "DELETE FROM experiment_projects WHERE project_id = ?", (project_id,)
            )
            if deleted.rowcount == 0:
                raise KeyError(project_id)

    # --- notebooks -------------------------------------------------------

    def list_notebooks(self) -> list[dict[str, Any]]:
        """Return every user notebook with its entry count, oldest first."""
        with read_connection(self.path) as conn:
            rows = conn.execute(f"{_NOTEBOOKS} ORDER BY n.created_at, n.rowid")
            return [_notebook(row) for row in rows]

    def create_notebook(self, name: str) -> dict[str, Any]:
        """Create a user notebook.

        Raises:
            ValueError: If the name is empty or too long.
            DuplicateError: If a notebook has the same name.
        """
        cleaned = _bounded(name, MAX_NOTEBOOK_NAME, "notebook name")
        notebook_id, now = new_id(), self._now()
        try:
            with write_transaction(self.path) as conn:
                conn.execute("INSERT INTO notebooks VALUES (?, ?, ?)", (notebook_id, cleaned, now))
        except sqlite3.IntegrityError:
            raise DuplicateError("A notebook with this name already exists.") from None
        return {"notebook_id": notebook_id, "name": cleaned, "created_at": now, "entry_count": 0}

    def rename_notebook(self, notebook_id: str, name: str) -> dict[str, Any]:
        """Rename a user notebook.

        Raises:
            ValueError: If the name is empty or too long.
            KeyError: If the notebook does not exist.
            DuplicateError: If another notebook has the name.
        """
        cleaned = _bounded(name, MAX_NOTEBOOK_NAME, "notebook name")
        try:
            with write_transaction(self.path) as conn:
                self._require_notebook(conn, notebook_id)
                conn.execute(
                    "UPDATE notebooks SET name = ? WHERE notebook_id = ?", (cleaned, notebook_id)
                )
                row = conn.execute(
                    f"{_NOTEBOOKS} WHERE n.notebook_id = ?",  # noqa: S608 - fixed SQL text
                    (notebook_id,),
                ).fetchone()
        except sqlite3.IntegrityError:
            raise DuplicateError("A notebook with this name already exists.") from None
        return _notebook(row)

    def delete_notebook(self, notebook_id: str) -> None:
        """Delete a user notebook and, through the cascade, its entries.

        Raises:
            KeyError: If the notebook does not exist.
        """
        with write_transaction(self.path) as conn:
            deleted = conn.execute("DELETE FROM notebooks WHERE notebook_id = ?", (notebook_id,))
            if deleted.rowcount == 0:
                raise KeyError(notebook_id)

    # --- entries ---------------------------------------------------------

    def add_entry(self, notebook_id: str, project_id: str, folder: str) -> dict[str, Any]:
        """Add one experiment to a notebook. Adding it again returns the stored entry.

        Raises:
            KeyError: If the notebook or the project does not exist.
        """
        with write_transaction(self.path) as conn:
            self._require_notebook(conn, notebook_id)
            known = conn.execute(
                "SELECT 1 FROM experiment_projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            if known is None:
                raise KeyError(project_id)
            key = (notebook_id, project_id, folder)
            conn.execute(
                "INSERT OR IGNORE INTO notebook_entries VALUES (?, ?, ?, ?)", (*key, self._now())
            )
            added_at = conn.execute(
                "SELECT added_at FROM notebook_entries "
                "WHERE notebook_id = ? AND project_id = ? AND folder = ?",
                key,
            ).fetchone()[0]
        return {
            "notebook_id": notebook_id,
            "project_id": project_id,
            "folder": folder,
            "added_at": added_at,
        }

    def remove_entry(self, notebook_id: str, project_id: str, folder: str) -> None:
        """Remove one entry from a notebook.

        Raises:
            KeyError: If the notebook has no such entry.
        """
        with write_transaction(self.path) as conn:
            deleted = conn.execute(
                "DELETE FROM notebook_entries "
                "WHERE notebook_id = ? AND project_id = ? AND folder = ?",
                (notebook_id, project_id, folder),
            )
            if deleted.rowcount == 0:
                raise KeyError(folder)

    def list_entries(self, notebook_id: str) -> list[dict[str, Any]]:
        """Return the entries of a notebook, oldest first.

        Raises:
            KeyError: If the notebook does not exist.
        """
        with read_connection(self.path) as conn:
            self._require_notebook(conn, notebook_id)
            rows = conn.execute(
                "SELECT project_id, folder, added_at FROM notebook_entries "
                "WHERE notebook_id = ? ORDER BY added_at, rowid",
                (notebook_id,),
            )
            return [dict(row) for row in rows]

    @staticmethod
    def _require_notebook(conn: sqlite3.Connection, notebook_id: str) -> None:
        found = conn.execute("SELECT 1 FROM notebooks WHERE notebook_id = ?", (notebook_id,))
        if found.fetchone() is None:
            raise KeyError(notebook_id)
