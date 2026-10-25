"""Migration 7: experiment projects and notebooks (experiments-in-web-workspace D2, task 2.3)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from omrs.integrations.workspace_sqlite import SCHEMA_MIGRATIONS, SqliteWorkspaceRepository
from omrs.integrations.workspace_sqlite.schema import connect

_V6 = SCHEMA_MIGRATIONS[:6]
_TABLES = {"experiment_projects", "notebooks", "notebook_entries"}


def _names(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    finally:
        conn.close()


def _user_version(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def test_migration_seven_is_the_latest() -> None:
    assert SCHEMA_MIGRATIONS[6][0] == 7


def test_v6_file_upgrades_to_v7_with_a_backup_and_keeps_its_rows(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    old = SqliteWorkspaceRepository(path, migrations=_V6)
    pipeline_id = old.create_pipeline("Kept")["pipeline_id"]
    conn = connect(path)
    try:
        conn.execute("INSERT INTO chat_folders VALUES ('f1', 'Work', 't', 1)")
    finally:
        conn.close()
    assert _user_version(path) == 6
    assert not _TABLES & _names(path)

    upgraded = SqliteWorkspaceRepository(path)

    assert _user_version(path) == 7
    assert _TABLES <= _names(path)
    assert upgraded.get_pipeline(pipeline_id)["title"] == "Kept"
    conn = connect(path)
    try:
        assert conn.execute("SELECT name FROM chat_folders").fetchone()[0] == "Work"
    finally:
        conn.close()
    assert len(list(tmp_path.glob("app.sqlite3.v6-to-v7.*.bak"))) == 1


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO experiment_projects VALUES ('p1', 'OMRS', '/work/omrs', 't')")
    conn.execute("INSERT INTO notebooks VALUES ('n1', 'Paper 1', 't')")
    conn.execute("INSERT INTO notebook_entries VALUES ('n1', 'p1', '01-a-2026-01-01', 't')")


def _entries(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM notebook_entries").fetchone()[0])


@pytest.mark.parametrize("table", ["experiment_projects", "notebooks"])
def test_deleting_a_parent_row_cascades_to_entries(tmp_path: Path, table: str) -> None:
    path = tmp_path / "app.sqlite3"
    SqliteWorkspaceRepository(path)
    conn = connect(path)
    try:
        _seed(conn)
        conn.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed table names
        assert _entries(conn) == 0
    finally:
        conn.close()


def test_project_roots_and_notebook_names_are_unique(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    SqliteWorkspaceRepository(path)
    conn = connect(path)
    try:
        _seed(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO experiment_projects VALUES ('p2', 'Again', '/work/omrs', 't')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO notebooks VALUES ('n2', 'Paper 1', 't')")
    finally:
        conn.close()


def test_an_entry_needs_a_known_notebook_and_project(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    SqliteWorkspaceRepository(path)
    conn = connect(path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO notebook_entries VALUES ('nope', 'nope', 'f', 't')")
    finally:
        conn.close()
