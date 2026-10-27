"""The experiment purpose in the library API (reproducible-experiment-runtime, task 4.1)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_web_documents_support import ORIGIN  # noqa: E402
from tests.unit.test_web_experiment_library_support import (  # noqa: E402
    FIRST,
    add_project,
    make_project,
    open_client,
)

BODY = {"slug": "paper-run", "title": "Paper run", "category": "retrieval", "size": "Standard"}


@pytest.fixture
def web(tmp_path: Path, effective_settings: Any):  # type: ignore[no-untyped-def]
    with open_client(tmp_path, effective_settings()) as opened:
        yield opened


def _project(client: Any, tmp_path: Path) -> tuple[Path, str]:
    root = make_project(tmp_path)
    return root, add_project(client, root)["project_id"]


def _post(client: Any, project_id: str, **extra: Any) -> Any:
    url = f"/v1/experiment-projects/{project_id}/experiments"
    return client.post(url, json={**BODY, **extra}, headers=ORIGIN)


def _folder() -> str:
    return f"3-paper-run-{date.today().isoformat()}"


def _record(root: Path, folder: str) -> dict[str, Any]:
    return json.loads((root / "experiments" / folder / "experiment.json").read_text("utf-8"))


def _listed(client: Any, project_id: str) -> dict[str, str]:
    listing = client.get(f"/v1/experiment-projects/{project_id}/experiments").json()
    return {item["folder"]: item["purpose"] for item in listing["experiments"]}


def test_a_publication_request_creates_a_publication_record(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root, project_id = _project(client, tmp_path)
    response = _post(client, project_id, purpose="publication", size="Confirmatory")
    assert response.status_code == 201, response.text
    assert _record(root, _folder())["purpose"] == "publication"
    assert _listed(client, project_id)[_folder()] == "publication"


def test_a_request_without_a_purpose_creates_an_optimisation_record(
    web: Any, tmp_path: Path
) -> None:
    client = web[0]
    root, project_id = _project(client, tmp_path)
    assert _post(client, project_id).status_code == 201
    assert _record(root, _folder()).get("purpose", "optimisation") == "optimisation"
    assert _listed(client, project_id)[_folder()] == "optimisation"


def test_an_unknown_purpose_is_refused_and_writes_no_folder(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root, project_id = _project(client, tmp_path)
    before = sorted(path.name for path in (root / "experiments").iterdir())
    response = _post(client, project_id, purpose="paper")
    assert response.status_code == 400, response.text
    message = response.json()["message"]
    assert "optimisation" in message
    assert "publication" in message
    assert sorted(path.name for path in (root / "experiments").iterdir()) == before


def test_a_record_without_the_field_reads_as_optimisation(web: Any, tmp_path: Path) -> None:
    client = web[0]
    root, project_id = _project(client, tmp_path)
    record = _record(root, FIRST)
    record.pop("purpose", None)  # an old record, written before the field existed
    path = root / "experiments" / FIRST / "experiment.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    assert _listed(client, project_id)[FIRST] == "optimisation"
    detail = client.get(f"/v1/experiment-projects/{project_id}/experiments/{FIRST}").json()
    assert detail["experiment"]["purpose"] == "optimisation"


def test_the_detail_carries_a_publication_purpose(web: Any, tmp_path: Path) -> None:
    client = web[0]
    _, project_id = _project(client, tmp_path)
    _post(client, project_id, purpose="publication")
    detail = client.get(f"/v1/experiment-projects/{project_id}/experiments/{_folder()}").json()
    assert detail["experiment"]["purpose"] == "publication"
