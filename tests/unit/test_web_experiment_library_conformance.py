"""Experiment library responses against the OpenAPI contract (experiments-in-web-workspace 3.7)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_web_documents_support import ORIGIN  # noqa: E402
from tests.unit.test_web_experiment_library_support import (  # noqa: E402
    FIRST,
    SECOND,
    make_project,
    open_client,
)
from tests.unit.test_web_openapi_conformance_support import (  # noqa: E402
    FAMILIES,
    ContractChecker,
)


def test_experiment_library_responses_conform_to_the_contract(
    tmp_path: Path, effective_settings: Any
) -> None:
    root = make_project(tmp_path)
    gone = make_project(tmp_path, "gone")
    check = ContractChecker()
    with open_client(tmp_path, effective_settings()) as (client, _, _):
        add = "/v1/experiment-projects"
        project = check.check(
            client.post(add, json={"path": str(root), "name": "OMRS"}, headers=ORIGIN), 201
        )["project"]["project_id"]
        other = check.check(
            client.post(add, json={"path": str(gone), "name": "Gone"}, headers=ORIGIN), 201
        )["project"]["project_id"]
        check.check(client.post(add, json={"path": str(root), "name": "x"}, headers=ORIGIN), 409)
        check.check(client.post(add, json={"path": "relative", "name": "x"}, headers=ORIGIN), 400)
        shutil.rmtree(gone)
        check.check(client.get(add), 200)
        base = f"{add}/{project}/experiments"
        check.check(client.get(base), 200)
        check.check(client.get(f"{add}/{other}/experiments"), 200)
        check.check(client.get(f"{add}/nope/experiments"), 404)
        check.check(client.get(f"{base}/{FIRST}"), 200)
        check.check(client.get(f"{base}/{SECOND}"), 200)
        check.check(client.get(f"{base}/.hidden"), 400)
        protocol = f"{base}/{FIRST}/files/protocol.md"
        revision = check.check(client.get(protocol), 200)["revision"]
        save = {"text": "# Protocol\n\nChanged.\n", "base_revision": revision}
        check.check(client.put(protocol, json=save, headers=ORIGIN), 200)
        check.check(client.put(protocol, json=save, headers=ORIGIN), 409)
        plan = f"{base}/{FIRST}/files/plan.json"
        check.check(client.put(plan, json=save, headers=ORIGIN), 400)
        check.check(client.get(f"{base}/{FIRST}/files/review.html"), 400)
        check.check(client.get(f"{base}/{FIRST}/files/absent.md"), 404)
        body = {"slug": "new-run", "title": "New run", "category": "graph", "size": "Quick"}
        check.check(client.post(base, json=body, headers=ORIGIN), 201)
        check.check(client.post(base, json={**body, "slug": "Bad"}, headers=ORIGIN), 400)
        editor = f"{base}/{SECOND}/editor"  # marimo is not registered here
        check.check(client.post(editor, json={"consent": True}, headers=ORIGIN), 409)

        notebook = check.check(
            client.post("/v1/notebooks", json={"name": "Paper 1"}, headers=ORIGIN), 201
        )["notebook"]["notebook_id"]
        check.check(client.post("/v1/notebooks", json={"name": "Paper 1"}, headers=ORIGIN), 409)
        entry = {"project_id": project, "folder": FIRST}
        entries = f"/v1/notebooks/{notebook}/entries"
        check.check(client.put(entries, json=entry, headers=ORIGIN), 200)
        check.check(
            client.put(entries, json={**entry, "folder": "9-x-2026-01-01"}, headers=ORIGIN), 404
        )
        (root / "experiments" / FIRST).rename(root / "experiments" / "1-moved-2026-01-01")
        check.check(client.get(f"/v1/notebooks/{notebook}"), 200)  # a missing entry
        check.check(client.get(f"/v1/notebooks/project:{project}"), 200)
        check.check(client.get("/v1/notebooks"), 200)
        check.check(client.get("/v1/notebooks/nope"), 404)
        rename = f"/v1/notebooks/{notebook}"
        check.check(client.patch(rename, json={"name": "Paper 2"}, headers=ORIGIN), 200)
        check.check(
            client.patch(f"/v1/notebooks/project:{project}", json={"name": "x"}, headers=ORIGIN),
            400,
        )
        check.check(client.delete(f"{entries}/{project}/{FIRST}", headers=ORIGIN), 200)
        check.check(client.delete(f"{entries}/{project}/{FIRST}", headers=ORIGIN), 404)
        check.check(client.delete(rename, headers=ORIGIN), 200)
        check.check(client.delete(rename, headers=ORIGIN), 404)
        check.check(client.delete(f"{add}/{other}", headers=ORIGIN), 200)
        check.check(client.delete(f"{add}/{other}", headers=ORIGIN), 404)
    assert check.operations >= FAMILIES["experiment_library"]
