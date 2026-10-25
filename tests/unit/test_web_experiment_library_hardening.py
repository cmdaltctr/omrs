"""Review fixes for the experiment library routes (experiments-in-web-workspace, review B).

Unreadable folders, links inside a project, case-variant duplicate projects and
encoded traversal in the URL.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_web_documents_support import ORIGIN  # noqa: E402
from tests.unit.test_web_experiment_library_support import (  # noqa: E402
    FIRST,
    SECOND,
    add_project,
    make_project,
    open_client,
)

HIDDEN_TEXT = "TOPSECRET"
_ROOT_USER = hasattr(os, "geteuid") and os.geteuid() == 0
needs_permissions = pytest.mark.skipif(_ROOT_USER, reason="root ignores file permissions")


@pytest.fixture
def web(tmp_path: Path, effective_settings: Any):  # type: ignore[no-untyped-def]
    with open_client(tmp_path, effective_settings()) as opened:
        yield opened


@contextmanager
def _mode(path: Path, mode: int) -> Iterator[None]:
    os.chmod(path, mode)
    try:
        yield
    finally:
        os.chmod(path, 0o700)


def _by_name(client: Any) -> dict[str, Any]:
    response = client.get("/v1/experiment-projects")
    assert response.status_code == 200, response.text
    return {p["name"]: p for p in response.json()["projects"]}


# ── 1. Unreadable folders ────────────────────────────────────────────────


@needs_permissions
@pytest.mark.parametrize("where", ["output", "experiments"])
def test_an_unreadable_folder_marks_only_that_project_unavailable(
    web: Any, tmp_path: Path, where: str
) -> None:
    client = web[0]
    add_project(client, make_project(tmp_path, "good"), "Good")
    root = make_project(tmp_path, "broken")
    broken = add_project(client, root, "Broken")["project_id"]
    target = root / "experiments" / FIRST / "output" if where == "output" else root / "experiments"
    with _mode(target, 0o311 if where == "experiments" else 0):
        projects = _by_name(client)
        notebooks = client.get("/v1/notebooks")
        listing = client.get(f"/v1/experiment-projects/{broken}/experiments")
    assert (projects["Good"]["available"], projects["Good"]["experiment_count"]) == (True, 2)
    assert (projects["Broken"]["available"], projects["Broken"]["experiment_count"]) == (
        False,
        None,
    )
    assert notebooks.status_code == 200
    assert listing.status_code == 200
    body = listing.json()
    assert body["project"]["available"] is False
    assert body["experiments"] == []
    assert [(f["code"], f["folder"]) for f in body["findings"]] == [("project-unreadable", None)]
    assert str(tmp_path) not in body["findings"][0]["message"]


@needs_permissions
def test_adding_an_unreadable_project_stores_nothing(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path)
    with _mode(root / "experiments", 0o311):
        response = client.post(
            "/v1/experiment-projects", json={"path": str(root), "name": "x"}, headers=ORIGIN
        )
    assert response.status_code == 400
    assert str(tmp_path) not in response.json()["message"]
    assert client.get("/v1/experiment-projects").json()["projects"] == []


# ── 2. and 3. Links inside an experiment folder ──────────────────────────


@pytest.fixture
def project(web: Any, tmp_path: Path) -> tuple[Any, Path, str]:
    root = make_project(tmp_path)
    project_id = add_project(web[0], root)["project_id"]
    return web[0], root / "experiments", f"/v1/experiment-projects/{project_id}/experiments"


@pytest.mark.parametrize("target", [".env", "output/x/secret.txt", "data.bin"])
def test_a_link_to_a_hidden_nested_or_binary_file_is_refused(project: Any, target: str) -> None:
    client, experiments, base = project
    folder = experiments / FIRST
    (folder / "output" / "x").mkdir()
    (folder / target).write_text(HIDDEN_TEXT, encoding="utf-8")
    (folder / "notes.md").symlink_to(folder / target)
    response = client.get(f"{base}/{FIRST}/files/notes.md")
    assert response.status_code == 400, response.text
    assert HIDDEN_TEXT not in response.text
    files = {f["name"]: f for f in client.get(f"{base}/{FIRST}").json()["files"]}
    assert files["notes.md"]["viewable"] is False


def test_a_link_to_a_text_file_in_the_same_folder_is_served(project: Any) -> None:
    client, experiments, base = project
    (experiments / FIRST / "notes.md").symlink_to(experiments / FIRST / "report.md")
    response = client.get(f"{base}/{FIRST}/files/notes.md")
    assert response.status_code == 200
    files = {f["name"]: f for f in client.get(f"{base}/{FIRST}").json()["files"]}
    assert files["notes.md"]["viewable"] is True


def test_an_output_link_to_another_place_is_not_listed(project: Any, tmp_path: Path) -> None:
    client, experiments, base = project
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private-name").write_text("x", encoding="utf-8")
    (experiments / SECOND / "output").symlink_to(outside, target_is_directory=True)
    assert client.get(f"{base}/{SECOND}").json()["output"] is None


# ── 4. Experiment folders that are links ─────────────────────────────────


def test_a_linked_experiment_folder_is_reported_and_not_listed(
    project: Any, tmp_path: Path
) -> None:
    client, experiments, base = project
    other = make_project(tmp_path, "other") / "experiments" / FIRST
    (experiments / "7-linked-2026-07-01").symlink_to(other, target_is_directory=True)
    body = client.get(base).json()
    assert "7-linked-2026-07-01" not in [e["folder"] for e in body["experiments"]]
    linked = [f for f in body["findings"] if f["code"] == "folder-link"]
    assert [(f["folder"], f["message"]) for f in linked] == [
        (None, "Folder 7-linked-2026-07-01 is a link to another place and is not listed.")
    ]
    assert all(f["folder"] != "7-linked-2026-07-01" for f in body["findings"])
    assert body["project"]["experiment_count"] == 2
    assert client.get(f"{base}/7-linked-2026-07-01").status_code == 404
    project_id = body["project"]["project_id"]
    entries = client.get(f"/v1/notebooks/project:{project_id}").json()["entries"]
    assert [e["folder"] for e in entries] == [FIRST, SECOND]


# ── 5. Case-variant duplicate projects ───────────────────────────────────


def test_a_second_spelling_of_the_same_project_is_a_duplicate(web: Any, tmp_path: Path) -> None:
    # A link alias stands in for a different-case spelling on macOS: both name the
    # same folder by another path, and the test runs on every file system.
    client = web[0]
    root = make_project(tmp_path, "omrs")
    variant = root.parent / "omrs-alias"
    variant.symlink_to(root, target_is_directory=True)
    add_project(client, root)
    response = client.post(
        "/v1/experiment-projects", json={"path": str(variant), "name": "Dup"}, headers=ORIGIN
    )
    assert response.status_code == 409
    assert len(client.get("/v1/experiment-projects").json()["projects"]) == 1


# ── 7. Encoded traversal in the URL ──────────────────────────────────────

TRAVERSAL = [
    f"{FIRST}/files/..%2Fsecret.md",
    f"{FIRST}/files/%2e%2e%2fsecret.md",
    f"{FIRST}/files/%2e%2e%2f%2e%2e%2fsecret.md",
    f"{FIRST}/files/%252e%252e%252fsecret.md",
    f"{FIRST}/files/..%5Csecret.md",
    f"{FIRST}/files/secret.md%00.md",
    f"{FIRST}/files/%EF%BC%8E%EF%BC%8E%EF%BC%8Fsecret.md",
    f"{FIRST}/files/..%E2%88%95secret.md",
    f"{FIRST}/../../secret.md",
    "..%2F..%2F/files/secret.md",
    "%2e%2e/files/secret.md",
    "%252e%252e/files/secret.md",
    "..%5C/files/secret.md",
    "%00/files/secret.md",
    "%EF%BC%8E%EF%BC%8E/files/secret.md",
    "../files/secret.md",
    "%2E/files/secret.md",
]


@pytest.mark.parametrize("suffix", TRAVERSAL)
def test_encoded_traversal_reads_no_file(project: Any, tmp_path: Path, suffix: str) -> None:
    client, experiments, base = project
    for place in (tmp_path, experiments.parent, experiments):
        (place / "secret.md").write_text(HIDDEN_TEXT, encoding="utf-8")
    response = client.get(f"{base}/{suffix}")
    assert response.status_code != 200, response.text
    assert HIDDEN_TEXT not in response.text
