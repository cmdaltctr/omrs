"""Experiment project and library routes (experiments-in-web-workspace tasks 3.2 and 3.3)."""

from __future__ import annotations

import shutil
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


# ── Projects (task 3.2) ─────────────────────────────────────────────────


def test_add_and_list_a_project(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path)
    project = add_project(client, root)
    assert project["root"] == str(root.resolve())
    assert project["available"] is True
    assert project["experiment_count"] == 2
    assert set(project) == {
        "project_id",
        "name",
        "root",
        "added_at",
        "available",
        "experiment_count",
    }
    listed = client.get("/v1/experiment-projects").json()["projects"]
    assert [p["project_id"] for p in listed] == [project["project_id"]]


def test_a_project_survives_a_restart(tmp_path: Path, effective_settings: Any) -> None:
    root = make_project(tmp_path)
    with open_client(tmp_path, effective_settings()) as (client, _, _):
        add_project(client, root)
    with open_client(tmp_path, effective_settings()) as (client, _, _):
        names = [p["name"] for p in client.get("/v1/experiment-projects").json()["projects"]]
    assert names == ["OMRS"]


def test_a_folder_without_experiments_is_refused_and_not_stored(web: Any, tmp_path: Path) -> None:
    client = web[0]
    response = client.post(
        "/v1/experiment-projects", json={"path": str(tmp_path), "name": "x"}, headers=ORIGIN
    )
    assert response.status_code == 400
    assert "`experiments` directory" in response.json()["message"]
    assert client.get("/v1/experiment-projects").json()["projects"] == []


def test_an_experiments_link_out_of_the_project_is_refused(web: Any, tmp_path: Path) -> None:
    client = web[0]
    outside = make_project(tmp_path, "outside") / "experiments"
    root = tmp_path / "linked"
    root.mkdir()
    (root / "experiments").symlink_to(outside, target_is_directory=True)
    response = client.post(
        "/v1/experiment-projects", json={"path": str(root), "name": "x"}, headers=ORIGIN
    )
    assert response.status_code == 400
    assert client.get("/v1/experiment-projects").json()["projects"] == []


def test_a_relative_path_is_refused(web: Any) -> None:
    client = web[0]
    body = {"path": "relative/omrs", "name": "x"}
    response = client.post("/v1/experiment-projects", json=body, headers=ORIGIN)
    assert response.status_code == 400


def test_the_same_folder_twice_is_a_conflict(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path)
    add_project(client, root)
    body = {"path": str(root / "experiments" / ".."), "name": "Again"}
    response = client.post("/v1/experiment-projects", json=body, headers=ORIGIN)
    assert response.status_code == 409


def test_remove_a_project_leaves_the_files(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path)
    project_id = add_project(client, root)["project_id"]
    response = client.delete(f"/v1/experiment-projects/{project_id}", headers=ORIGIN)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "removed": True}
    assert (root / "experiments" / FIRST / "experiment.json").is_file()
    assert client.get("/v1/experiment-projects").json()["projects"] == []
    assert client.delete(f"/v1/experiment-projects/{project_id}", headers=ORIGIN).status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/v1/experiment-projects"),
        ("delete", "/v1/experiment-projects/x"),
        ("get", "/v1/experiment-projects"),
        ("get", "/v1/experiment-projects/x/experiments"),
        ("post", "/v1/experiment-projects/x/experiments"),
    ],
)
def test_a_bearer_credential_is_refused(web: Any, method: str, path: str) -> None:
    client, policy, _ = web
    client.cookies.clear()
    headers = {**bearer(policy, "graph", "read", "run"), **ORIGIN}
    response = client.request(method, path, headers=headers, json={"path": "/x", "name": "x"})
    assert response.status_code == 403, response.text


def test_a_removed_project_folder_is_listed_as_unavailable(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path)
    project_id = add_project(client, root)["project_id"]
    shutil.rmtree(root)
    project = client.get("/v1/experiment-projects").json()["projects"][0]
    assert (project["available"], project["experiment_count"]) == (False, None)
    listing = client.get(f"/v1/experiment-projects/{project_id}/experiments").json()
    assert listing["project"]["available"] is False
    assert (listing["experiments"], listing["reserved"], listing["findings"]) == ([], [], [])


# ── Library listing and one experiment (task 3.3) ──────────────────────


def test_list_experiments_with_records_findings_and_reserved(web: Any, tmp_path: Path) -> None:
    client = web[0]
    project_id = add_project(client, make_project(tmp_path))["project_id"]
    body = client.get(f"/v1/experiment-projects/{project_id}/experiments").json()
    assert body["project"]["project_id"] == project_id
    assert [e["folder"] for e in body["experiments"]] == [FIRST, SECOND]
    first = body["experiments"][0]
    assert first == {
        "folder": FIRST,
        "number": "1",
        "title": "First run",
        "date": "2026-01-01",
        "category": "retrieval",
        "size": "Standard",
        "purpose": "optimisation",
        "status": "PLANNED",
        "superseded_by": None,
        "finding": "",
        "refs": {"adrs": [], "changes": [], "tasks": []},
        "migrated": False,
        "findings": [],
    }
    assert body["reserved"] == [{"number": "9", "reason": "Planned later", "ref": "task 9"}]
    codes = {(f["code"], f["folder"]) for f in body["findings"]}
    assert ("index-stale", None) in codes  # the README index is empty


def test_findings_are_grouped_under_their_experiment(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path)
    (root / "experiments" / FIRST / "protocol.md").unlink()
    project_id = add_project(client, root)["project_id"]
    body = client.get(f"/v1/experiment-projects/{project_id}/experiments").json()
    first = body["experiments"][0]
    assert [(f["severity"], f["code"], f["folder"]) for f in first["findings"]] == [
        ("warning", "files-missing", FIRST)
    ]
    assert all(f["folder"] is None for f in body["findings"])


def test_a_folder_without_a_valid_record_is_reported_but_not_listed(
    web: Any, tmp_path: Path
) -> None:
    client = web[0]
    root = make_project(tmp_path)
    (root / "experiments" / "3-broken-2026-03-01").mkdir()
    project_id = add_project(client, root)["project_id"]
    body = client.get(f"/v1/experiment-projects/{project_id}/experiments").json()
    assert "3-broken-2026-03-01" not in [e["folder"] for e in body["experiments"]]
    assert ("record-missing", "3-broken-2026-03-01") in {
        (f["code"], f["folder"]) for f in body["findings"]
    }


def test_one_experiment_with_files_and_output(web: Any, tmp_path: Path) -> None:
    client = web[0]
    project_id = add_project(client, make_project(tmp_path))["project_id"]
    body = client.get(f"/v1/experiment-projects/{project_id}/experiments/{FIRST}").json()
    assert body["experiment"]["folder"] == FIRST
    assert body["project"]["project_id"] == project_id
    files = {f["name"]: f for f in body["files"]}
    assert set(files) == {"experiment.json", "plan.json", "protocol.md", "report.md", "review.html"}
    assert files["protocol.md"]["viewable"] is True
    assert files["review.html"]["viewable"] is False
    assert files["review.html"]["size"] == len("<script>alert(1)</script>")
    assert body["output"] == ["chroma_index", "scores.json"]
    second = client.get(f"/v1/experiment-projects/{project_id}/experiments/{SECOND}").json()
    assert second["output"] is None


@pytest.mark.parametrize("folder", ["nope-2026-01-01", "a..b", ".hidden", "_lib"])
def test_an_unknown_or_unsafe_folder_is_refused(web: Any, tmp_path: Path, folder: str) -> None:
    client = web[0]
    root = make_project(tmp_path)
    (root / "experiments" / "_lib").mkdir()
    project_id = add_project(client, root)["project_id"]
    response = client.get(f"/v1/experiment-projects/{project_id}/experiments/{folder}")
    assert response.status_code in {400, 404}, response.text
    assert response.json()["status"] == "error"


def test_an_unknown_project_is_404(web: Any) -> None:
    client = web[0]
    assert client.get("/v1/experiment-projects/nope/experiments").status_code == 404
    assert client.get(f"/v1/experiment-projects/nope/experiments/{FIRST}").status_code == 404


def test_one_experiment_of_an_unavailable_project_is_404(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path)
    project_id = add_project(client, root)["project_id"]
    shutil.rmtree(root)
    response = client.get(f"/v1/experiment-projects/{project_id}/experiments/{FIRST}")
    assert response.status_code == 404
