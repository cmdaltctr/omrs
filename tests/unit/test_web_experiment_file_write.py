"""Saving experiment files through the route (edit-experiment-files-in-library, task 5.2, D6)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_web_documents_support import ORIGIN, bearer  # noqa: E402
from tests.unit.test_web_experiment_library_support import (  # noqa: E402
    FIRST,
    add_project,
    make_project,
    open_client,
)
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

from omrs.transports.api import security  # noqa: E402
from omrs.transports.api.routes.experiment_library import EDIT_REASONS  # noqa: E402

OLD = b"# Protocol\n\nOld text.\n"


@pytest.fixture
def web(tmp_path: Path, effective_settings: Any):  # type: ignore[no-untyped-def]
    root = make_project(tmp_path)
    folder = root / "experiments" / FIRST
    (folder / "protocol.md").write_bytes(OLD)
    with open_client(tmp_path, effective_settings()) as (client, policy, _):
        project_id = add_project(client, root)["project_id"]
        url = f"/v1/experiment-projects/{project_id}/experiments/{FIRST}/files"
        yield client, policy, folder, url


def _put(web: Any, name: str, text: str, revision: str | None = None, **headers: str) -> Any:
    client, _, folder, url = web
    if revision is None:
        revision = hashlib.sha256((folder / name).read_bytes()).hexdigest()
    body = {"text": text, "base_revision": revision}
    return client.put(f"{url}/{name}", json=body, headers={**ORIGIN, **headers})


def test_a_session_saves_and_the_answer_matches_the_contract(web: Any) -> None:
    response = _put(web, "protocol.md", "# Protocol\n\nNew text.\n")
    body = ContractChecker().check(response, 200)
    data = (web[2] / "protocol.md").read_bytes()
    assert data == b"# Protocol\n\nNew text.\n"
    assert body["name"] == "protocol.md"
    assert body["changed"] is True
    assert body["revision"] == hashlib.sha256(data).hexdigest()
    assert body["size"] == len(data)
    assert body["last_edited"]["status"] == "PLANNED"
    assert body["last_edited"]["edited_at"].endswith("Z")
    (line,) = (web[2] / "edits.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(line)["tool"].startswith("omrs web ")
    read = web[0].get(f"{web[3]}/protocol.md").json()
    assert read["revision"] == body["revision"]
    assert read["last_edited"] == body["last_edited"]


def test_unchanged_text_answers_changed_false(web: Any) -> None:
    response = _put(web, "protocol.md", OLD.decode())
    assert ContractChecker().check(response, 200)["changed"] is False
    assert not (web[2] / "edits.jsonl").exists()


def test_a_session_without_manage_gets_403(web: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"manage"})
    assert _put(web, "protocol.md", "new\n").status_code == 403
    assert (web[2] / "protocol.md").read_bytes() == OLD


def test_a_bearer_credential_gets_403(web: Any) -> None:
    client, policy, folder, url = web
    revision = hashlib.sha256(OLD).hexdigest()
    headers = {**ORIGIN, **bearer(policy, "graph", "read", "run")}
    client.cookies.clear()
    response = client.put(
        f"{url}/protocol.md", json={"text": "new\n", "base_revision": revision}, headers=headers
    )
    assert response.status_code == 403
    assert (folder / "protocol.md").read_bytes() == OLD


def test_a_foreign_origin_gets_403(web: Any) -> None:
    response = _put(web, "protocol.md", "new\n", Origin="https://evil.example")
    assert response.status_code == 403
    assert (web[2] / "protocol.md").read_bytes() == OLD


def test_unknown_project_or_folder_gets_404(web: Any) -> None:
    client, _, _, url = web
    body = {"text": "x", "base_revision": "0" * 64}
    checker = ContractChecker()
    checker.check(
        client.put(
            "/v1/experiment-projects/nope/experiments/x/files/report.md", json=body, headers=ORIGIN
        ),
        404,
    )
    other = url.replace(FIRST, "9-nope-2026-01-01")
    checker.check(client.put(f"{other}/report.md", json=body, headers=ORIGIN), 404)


@pytest.mark.parametrize("name", ["plan.json", "analysis.py", ".hidden.md", "notes.md"])
def test_a_refused_name_gets_400(web: Any, name: str) -> None:
    client, _, folder, url = web
    (folder / "notes.md").write_bytes(b"notes\n")
    body = {"text": "x", "base_revision": "0" * 64}
    response = client.put(f"{url}/{name}", json=body, headers=ORIGIN)
    ContractChecker().check(response, 400)
    assert (folder / "notes.md").read_bytes() == b"notes\n"


def test_a_stale_revision_gets_409_changed_on_disk(web: Any) -> None:
    response = _put(web, "protocol.md", "new\n", revision="0" * 64)
    body = ContractChecker().check(response, 409)
    assert body["reason"] == "changed_on_disk"
    assert body["message"] == EDIT_REASONS["changed_on_disk"]
    assert (web[2] / "protocol.md").read_bytes() == OLD


def test_an_edit_log_link_gets_409_edit_log_unusable(web: Any, tmp_path: Path) -> None:
    target = tmp_path / "elsewhere.jsonl"
    target.write_bytes(b"")
    (web[2] / "edits.jsonl").symlink_to(target)
    body = ContractChecker().check(_put(web, "protocol.md", "new\n"), 409)
    assert body["reason"] == "edit_log_unusable"
    assert (web[2] / "protocol.md").read_bytes() == OLD


def test_a_failed_log_append_gets_500_and_keeps_the_old_text(
    web: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs.core.workspace import experiment_file_edits as edits

    def broken(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(edits, "append_edit", broken)
    response = _put(web, "protocol.md", "new\n")
    body = ContractChecker().check(response, 500)
    assert body["message"] == edits.NOT_SAVED
    assert (web[2] / "protocol.md").read_bytes() == OLD


def test_an_extra_body_key_is_refused(web: Any) -> None:
    client, _, folder, url = web
    body = {"text": "x", "base_revision": hashlib.sha256(OLD).hexdigest(), "path": "/etc"}
    assert client.put(f"{url}/protocol.md", json=body, headers=ORIGIN).status_code in (400, 422)
    assert (folder / "protocol.md").read_bytes() == OLD
