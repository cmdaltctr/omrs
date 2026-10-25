"""Creating an experiment from the library (experiments-in-web-workspace D7, task 3.6)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_web_documents_support import ORIGIN, bearer  # noqa: E402
from tests.unit.test_web_experiment_library_support import (  # noqa: E402
    add_project,
    make_project,
    open_client,
)

BODY = {"slug": "ocr-text-quality", "title": "OCR text quality", "category": "ingestion"}


@pytest.fixture
def web(tmp_path: Path, effective_settings: Any):  # type: ignore[no-untyped-def]
    with open_client(tmp_path, effective_settings()) as opened:
        yield opened


def _post(client: Any, project_id: str, **extra: Any) -> Any:
    body = {**BODY, "size": "Standard", **extra}
    return client.post(
        f"/v1/experiment-projects/{project_id}/experiments", json=body, headers=ORIGIN
    )


def _folder() -> str:
    return f"3-ocr-text-quality-{date.today().isoformat()}"


def test_create_a_standard_experiment_and_write_the_index(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path)
    project_id = add_project(client, root)["project_id"]
    response = _post(client, project_id)
    assert response.status_code == 201, response.text
    assert response.json() == {"status": "ok", "folder": _folder(), "index": "written"}
    record = json.loads((root / "experiments" / _folder() / "experiment.json").read_text("utf-8"))
    assert record["status"] == "PLANNED"
    assert f"./{_folder()}/" in (root / "experiments" / "EXP_README.md").read_text("utf-8")
    listing = client.get(f"/v1/experiment-projects/{project_id}/experiments").json()
    assert _folder() in [e["folder"] for e in listing["experiments"]]


def test_a_readme_without_markers_is_left_alone(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path, readme="# Experiments\n")
    project_id = add_project(client, root)["project_id"]
    assert _post(client, project_id).json()["index"] == "no-markers"
    assert (root / "experiments" / "EXP_README.md").read_text("utf-8") == "# Experiments\n"


def test_a_project_without_a_readme_reports_it(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path, readme=None)
    project_id = add_project(client, root)["project_id"]
    assert _post(client, project_id, size="Quick").json()["index"] == "no-readme"
    assert not (root / "experiments" / "EXP_README.md").exists()


def test_a_follow_up_takes_the_next_letter(web: Any, tmp_path: Path) -> None:
    client = web[0]
    project_id = add_project(client, make_project(tmp_path))["project_id"]
    folder = _post(client, project_id, follow_up="1").json()["folder"]
    assert folder.startswith("1a-ocr-text-quality-")


def test_an_existing_folder_is_refused_and_nothing_changes(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path)
    project_id = add_project(client, root)["project_id"]
    # A file is not detected as an experiment, so the creator picks its name.
    (root / "experiments" / _folder()).write_text("taken", encoding="utf-8")
    readme = (root / "experiments" / "EXP_README.md").read_text("utf-8")
    response = _post(client, project_id)
    assert response.status_code == 400
    assert "already exists" in response.json()["message"]
    assert str(root) not in response.json()["message"]
    assert (root / "experiments" / _folder()).read_text("utf-8") == "taken"
    assert (root / "experiments" / "EXP_README.md").read_text("utf-8") == readme


def test_a_bad_slug_is_refused_and_writes_nothing(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root = make_project(tmp_path)
    project_id = add_project(client, root)["project_id"]
    before = sorted(p.name for p in (root / "experiments").iterdir())
    response = _post(client, project_id, slug="Bad Slug")
    assert response.status_code == 400
    assert "slug" in response.json()["message"]
    assert sorted(p.name for p in (root / "experiments").iterdir()) == before


@pytest.mark.parametrize("field", [{"category": "cooking"}, {"size": "Huge"}])
def test_unknown_category_or_size_is_400(web: Any, tmp_path: Path, field: Any) -> None:
    client = web[0]
    project_id = add_project(client, make_project(tmp_path))["project_id"]
    assert _post(client, project_id, **field).status_code == 400


def test_an_unknown_project_is_404(web: Any) -> None:
    assert _post(web[0], "nope").status_code == 404


def test_a_bearer_credential_cannot_create(web: Any, tmp_path: Path) -> None:
    client, policy, _ = web
    project_id = add_project(client, make_project(tmp_path))["project_id"]
    client.cookies.clear()
    headers = {**bearer(policy, "graph", "read", "run"), **ORIGIN}
    body = {**BODY, "size": "Quick"}
    response = client.post(
        f"/v1/experiment-projects/{project_id}/experiments", json=body, headers=headers
    )
    assert response.status_code == 403
