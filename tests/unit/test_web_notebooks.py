"""Notebook routes (experiments-in-web-workspace D2 and D5, task 3.5)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_web_documents_support import ORIGIN, bearer  # noqa: E402
from tests.unit.test_web_experiment_library_support import (  # noqa: E402
    FIRST,
    SECOND,
    add_project,
    make_project,
    open_client,
)


@pytest.fixture
def web(tmp_path: Path, effective_settings: Any):  # type: ignore[no-untyped-def]
    with open_client(tmp_path, effective_settings()) as opened:
        yield opened


def _create(client: Any, name: str = "Paper 1") -> dict[str, Any]:
    response = client.post("/v1/notebooks", json={"name": name}, headers=ORIGIN)
    assert response.status_code == 201, response.text
    return response.json()["notebook"]


def _put(client: Any, notebook_id: str, project_id: str, folder: str) -> Any:
    body = {"project_id": project_id, "folder": folder}
    return client.put(f"/v1/notebooks/{notebook_id}/entries", json=body, headers=ORIGIN)


def test_projects_are_listed_first_as_project_notebooks(web: Any, tmp_path: Path) -> None:
    client = web[0]
    project = add_project(client, make_project(tmp_path))
    user = _create(client)
    listed = client.get("/v1/notebooks").json()["notebooks"]
    assert listed == [
        {
            "notebook_id": f"project:{project['project_id']}",
            "name": "OMRS",
            "kind": "project",
            "project_id": project["project_id"],
            "entry_count": 2,
            "created_at": None,
        },
        user,
    ]
    assert user["kind"] == "user"
    assert user["project_id"] is None
    assert user["entry_count"] == 0


def test_a_project_notebook_lists_every_experiment(web: Any, tmp_path: Path) -> None:
    client = web[0]
    project = add_project(client, make_project(tmp_path))
    body = client.get(f"/v1/notebooks/project:{project['project_id']}").json()
    assert body["notebook"]["kind"] == "project"
    assert [e["folder"] for e in body["entries"]] == [FIRST, SECOND]
    assert all(e["missing"] is False for e in body["entries"])
    assert body["entries"][0]["project_name"] == "OMRS"
    assert body["entries"][0]["experiment"]["title"] == "First run"


def test_a_cross_project_notebook(web: Any, tmp_path: Path) -> None:
    client = web[0]
    one = add_project(client, make_project(tmp_path, "one"), "One")["project_id"]
    two = add_project(client, make_project(tmp_path, "two"), "Two")["project_id"]
    notebook = _create(client)["notebook_id"]
    entry = _put(client, notebook, one, FIRST).json()["entry"]
    assert set(entry) == {
        "project_id",
        "project_name",
        "folder",
        "added_at",
        "missing",
        "experiment",
    }
    _put(client, notebook, two, SECOND)
    body = client.get(f"/v1/notebooks/{notebook}").json()
    assert [(e["project_name"], e["folder"]) for e in body["entries"]] == [
        ("One", FIRST),
        ("Two", SECOND),
    ]
    assert body["notebook"]["entry_count"] == 2


def test_adding_the_same_entry_twice_keeps_one(web: Any, tmp_path: Path) -> None:
    client = web[0]
    project = add_project(client, make_project(tmp_path))["project_id"]
    notebook = _create(client)["notebook_id"]
    assert _put(client, notebook, project, FIRST).status_code == 200
    assert _put(client, notebook, project, FIRST).status_code == 200
    assert len(client.get(f"/v1/notebooks/{notebook}").json()["entries"]) == 1


def test_a_renamed_folder_is_shown_as_missing_and_stays(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path)
    project = add_project(client, root)["project_id"]
    notebook = _create(client)["notebook_id"]
    _put(client, notebook, project, FIRST)
    (root / "experiments" / FIRST).rename(root / "experiments" / "1-renamed-2026-01-01")
    entries = client.get(f"/v1/notebooks/{notebook}").json()["entries"]
    assert [(e["folder"], e["missing"], e["experiment"]) for e in entries] == [(FIRST, True, None)]
    assert len(client.get(f"/v1/notebooks/{notebook}").json()["entries"]) == 1
    removed = client.delete(f"/v1/notebooks/{notebook}/entries/{project}/{FIRST}", headers=ORIGIN)
    assert removed.json() == {"status": "ok", "removed": True}
    assert client.get(f"/v1/notebooks/{notebook}").json()["entries"] == []


def test_adding_an_unknown_folder_or_project_is_404(web: Any, tmp_path: Path) -> None:
    client = web[0]
    project = add_project(client, make_project(tmp_path))["project_id"]
    notebook = _create(client)["notebook_id"]
    assert _put(client, notebook, project, "9-nope-2026-01-01").status_code == 404
    assert _put(client, notebook, "nope", FIRST).status_code == 404
    assert _put(client, "nope", project, FIRST).status_code == 404


def test_a_duplicate_notebook_name_is_refused(web: Any) -> None:
    client = web[0]
    _create(client)
    response = client.post("/v1/notebooks", json={"name": "Paper 1"}, headers=ORIGIN)
    assert response.status_code == 409
    assert len(client.get("/v1/notebooks").json()["notebooks"]) == 1


def _tree_digest(experiments: Path) -> list[tuple[str, str]]:
    """Return ``(relative path, SHA-256)`` for every file below *experiments*, sorted."""
    return sorted(
        (path.relative_to(experiments).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest())
        for path in experiments.rglob("*")
        if path.is_file()
    )


def test_rename_and_delete_a_user_notebook(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path)
    project = add_project(client, root)["project_id"]
    notebook = _create(client)["notebook_id"]
    _put(client, notebook, project, FIRST)
    renamed = client.patch(f"/v1/notebooks/{notebook}", json={"name": "Paper 2"}, headers=ORIGIN)
    assert renamed.json()["notebook"]["name"] == "Paper 2"
    assert renamed.json()["notebook"]["entry_count"] == 1
    before = _tree_digest(root / "experiments")
    deleted = client.delete(f"/v1/notebooks/{notebook}", headers=ORIGIN)
    assert deleted.json() == {"status": "ok", "removed": True}
    assert client.get(f"/v1/notebooks/{notebook}").status_code == 404
    # Deleting a notebook changes no experiment file.
    assert before, "the project has no files to compare"
    assert _tree_digest(root / "experiments") == before


def test_rename_to_a_taken_name_is_409(web: Any) -> None:
    client = web[0]
    _create(client, "A")
    second = _create(client, "B")["notebook_id"]
    response = client.patch(f"/v1/notebooks/{second}", json={"name": "A"}, headers=ORIGIN)
    assert response.status_code == 409


def test_a_project_notebook_cannot_be_changed(web: Any, tmp_path: Path) -> None:
    client = web[0]
    project = add_project(client, make_project(tmp_path))["project_id"]
    notebook = f"project:{project}"
    responses = [
        client.patch(f"/v1/notebooks/{notebook}", json={"name": "x"}, headers=ORIGIN),
        client.delete(f"/v1/notebooks/{notebook}", headers=ORIGIN),
        _put(client, notebook, project, FIRST),
        client.delete(f"/v1/notebooks/{notebook}/entries/{project}/{FIRST}", headers=ORIGIN),
    ]
    assert [r.status_code for r in responses] == [400, 400, 400, 400]


def test_unknown_notebooks_are_404(web: Any) -> None:
    client = web[0]
    responses = [
        client.get("/v1/notebooks/nope"),
        client.get("/v1/notebooks/project:nope"),
        client.patch("/v1/notebooks/nope", json={"name": "x"}, headers=ORIGIN),
        client.delete("/v1/notebooks/nope", headers=ORIGIN),
        client.delete(f"/v1/notebooks/nope/entries/p/{FIRST}", headers=ORIGIN),
    ]
    assert [r.status_code for r in responses] == [404, 404, 404, 404, 404]


def test_removing_a_project_removes_its_entries(web: Any, tmp_path: Path) -> None:
    client = web[0]
    project = add_project(client, make_project(tmp_path))["project_id"]
    notebook = _create(client)["notebook_id"]
    _put(client, notebook, project, FIRST)
    client.delete(f"/v1/experiment-projects/{project}", headers=ORIGIN)
    assert client.get(f"/v1/notebooks/{notebook}").json()["entries"] == []


def test_a_blank_name_is_400(web: Any) -> None:
    client = web[0]
    assert client.post("/v1/notebooks", json={"name": "  "}, headers=ORIGIN).status_code == 400


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/v1/notebooks"),
        ("post", "/v1/notebooks"),
        ("get", "/v1/notebooks/x"),
        ("patch", "/v1/notebooks/x"),
        ("delete", "/v1/notebooks/x"),
        ("put", "/v1/notebooks/x/entries"),
        ("delete", "/v1/notebooks/x/entries/p/f"),
    ],
)
def test_a_bearer_credential_is_refused(web: Any, method: str, path: str) -> None:
    client, policy, _ = web
    client.cookies.clear()
    headers = {**bearer(policy, "graph", "read", "run"), **ORIGIN}
    response = client.request(method, path, headers=headers, json={"name": "x"})
    assert response.status_code == 403, response.text
