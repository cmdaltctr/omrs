"""Document router routes: list, save, rename and delete (document-reading-routers, task 4.1).

Each test follows a scenario of the ``document-routers`` and
``workspace-settings`` deltas. A fake profile catalogue stands in for the
workspace. Nothing contacts a model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import ORIGIN, bearer  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import (  # noqa: E402
    FAMILIES,
    ContractChecker,
)
from tests.unit.test_web_router_maps_support import (  # noqa: E402
    FILE,
    FakeCatalogue,
    Harness,
    make_harness,
    refused,
    send,
    signed_in,
)

URL = "/v1/settings/document-routers"
ROUTER = {"model": "clef-local", "question": "Is the text right?", "threshold": 0.3}


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return make_harness(tmp_path, monkeypatch)


@pytest.fixture
def client(harness: Harness) -> TestClient:
    return signed_in(harness)


def routers(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in body["routers"]}


def with_host(name: str) -> str:
    return FILE.replace(
        '"document_routers": {', f'"document_router": "{name}",\n  "document_routers": {{', 1
    )


# ── List ─────────────────────────────────────────────────────────────────


def test_list_shows_each_router_and_whether_it_runs(harness: Harness, client: TestClient) -> None:
    harness.write(with_host("handwriting"))
    harness.profiles(FakeCatalogue({"Theses": "handwriting", "Plain": None}))
    response = client.get(URL)
    assert response.status_code == 200, response.text
    found = routers(response.json())
    local, hosted = found["handwriting"], found["hosted"]
    assert local["will_run"] is True and local["will_not_run_reason"] is None
    assert (local["hosted"], local["experimental"], local["model_kind"]) == (
        False,
        False,
        "llamacpp",
    )
    assert (local["host"], local["used_by"]) == (True, ["Theses"])
    assert (local["threshold"], local["max_chars"], local["send_off_machine"]) == (
        0.172,
        2000,
        False,
    )
    assert (hosted["hosted"], hosted["experimental"], hosted["model_kind"]) == (
        True,
        True,
        "typesafe",
    )
    assert (hosted["will_run"], hosted["will_not_run_reason"]) == (False, "needs-opt-in")
    assert (hosted["host"], hosted["used_by"]) == (False, [])


def test_a_hosted_router_with_the_opt_in_will_run(harness: Harness, client: TestClient) -> None:
    harness.write(
        FILE.replace('"threshold": 0.21,', '"threshold": 0.21, "send_off_machine": true,')
    )
    hosted = routers(client.get(URL).json())["hosted"]
    assert (hosted["will_run"], hosted["will_not_run_reason"]) == (True, None)


def test_a_router_on_an_unknown_model_will_not_run(harness: Harness, client: TestClient) -> None:
    harness.write(FILE.replace('"model": "clef-local", "question"', '"model": "gone", "question"'))
    local = routers(client.get(URL).json())["handwriting"]
    assert (local["will_run"], local["will_not_run_reason"], local["model_kind"]) == (
        False,
        "unknown-model",
        None,
    )
    assert local["hosted"] is False


def test_list_reads_without_profiles(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    harness.profiles(FakeCatalogue({}, broken=True))
    response = client.get(URL)
    assert response.status_code == 200
    assert routers(response.json())["handwriting"]["used_by"] == []


# ── Save ─────────────────────────────────────────────────────────────────


def test_save_a_router_keeps_comments(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    response = send(
        client, "PUT", f"{URL}/notes", {"entry": ROUTER, "revision": harness.revision()}
    )
    assert response.status_code == 200, response.text
    saved = harness.data()["document_routers"]["notes"]
    assert saved["question"] == ROUTER["question"] and saved["threshold"] == 0.3
    assert "// decision models" in harness.text()
    assert routers(response.json())["notes"]["will_run"] is True


@pytest.mark.parametrize(
    ("name", "entry"),
    [("none", ROUTER), ("bad", {**ROUTER, "threshold": 1.5}), ("bad", {**ROUTER, "scope": "x"})],
)
def test_a_broken_router_is_refused(
    harness: Harness, client: TestClient, name: str, entry: dict[str, Any]
) -> None:
    harness.write(FILE)
    response = send(
        client, "PUT", f"{URL}/{name}", {"entry": entry, "revision": harness.revision()}
    )
    refused(response, 400)
    assert harness.text() == FILE


def test_writes_refuse_a_bearer_credential(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    harness.profiles(FakeCatalogue({}))
    client.cookies.clear()
    headers = {**ORIGIN, **bearer(harness.policy, "read", "run", "graph")}
    revision = harness.revision()
    put = client.put(f"{URL}/x", json={"entry": ROUTER, "revision": revision}, headers=headers)
    rename = client.post(
        f"{URL}/hosted/rename", json={"new_name": "y", "revision": revision}, headers=headers
    )
    delete = client.request("DELETE", f"{URL}/hosted", json={"revision": revision}, headers=headers)
    assert (put.status_code, rename.status_code, delete.status_code) == (403, 403, 403)
    assert client.get(URL, headers=bearer(harness.policy, "read")).status_code == 200
    assert harness.text() == FILE


# ── Delete ───────────────────────────────────────────────────────────────


def test_delete_a_router_in_use_by_a_profile_names_the_profile(
    harness: Harness, client: TestClient
) -> None:
    harness.write(FILE)
    harness.profiles(FakeCatalogue({"Theses": "handwriting"}))
    response = send(client, "DELETE", f"{URL}/handwriting", {"revision": harness.revision()})
    assert "Theses" in refused(response, 409, "in-use")
    assert harness.text() == FILE


def test_delete_the_host_router_is_refused(harness: Harness, client: TestClient) -> None:
    harness.write(with_host("handwriting"))
    harness.profiles(FakeCatalogue({}))
    before = harness.text()
    response = send(client, "DELETE", f"{URL}/handwriting", {"revision": harness.revision()})
    assert "document_router" in refused(response, 409, "in-use")
    assert harness.text() == before


@pytest.mark.parametrize("broken", [True, False])
def test_delete_without_readable_profiles_is_refused(
    harness: Harness, client: TestClient, broken: bool
) -> None:
    harness.write(FILE)
    if broken:
        harness.profiles(FakeCatalogue({}, broken=True))
    response = send(client, "DELETE", f"{URL}/hosted", {"revision": harness.revision()})
    message = refused(response, 409, "profiles-unreadable")
    assert "database is locked" not in message
    assert harness.text() == FILE


def test_delete_an_unused_router(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    harness.profiles(FakeCatalogue({"Theses": "handwriting"}))
    response = send(client, "DELETE", f"{URL}/hosted", {"revision": harness.revision()})
    assert response.status_code == 200, response.text
    assert "hosted" not in harness.data()["document_routers"]
    assert sorted(routers(response.json())) == ["handwriting"]


def test_delete_an_unknown_router_gets_404(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    harness.profiles(FakeCatalogue({}))
    refused(send(client, "DELETE", f"{URL}/missing", {"revision": harness.revision()}), 404)


# ── Rename ───────────────────────────────────────────────────────────────


def test_rename_moves_the_fields_in_one_write(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    harness.profiles(FakeCatalogue({}))
    before = harness.data()["document_routers"]["hosted"]
    body = {"new_name": "typesafe-check", "revision": harness.revision()}
    response = send(client, "POST", f"{URL}/hosted/rename", body)
    assert response.status_code == 200, response.text
    after = harness.data()["document_routers"]
    assert "hosted" not in after
    assert {k: v for k, v in after["typesafe-check"].items() if k in before} == before
    assert "// decision models" in harness.text()
    assert sorted(routers(response.json())) == ["handwriting", "typesafe-check"]


def test_rename_to_a_name_in_use_is_refused(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    harness.profiles(FakeCatalogue({}))
    body = {"new_name": "handwriting", "revision": harness.revision()}
    refused(send(client, "POST", f"{URL}/hosted/rename", body), 409, "name-taken")
    assert harness.text() == FILE


def test_rename_a_router_a_profile_names_is_refused(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    harness.profiles(FakeCatalogue({"Scans": "hosted"}))
    body = {"new_name": "other", "revision": harness.revision()}
    assert "Scans" in refused(send(client, "POST", f"{URL}/hosted/rename", body), 409, "in-use")
    assert harness.text() == FILE


@pytest.mark.parametrize("new_name", ["none", "-bad", "a b"])
def test_rename_to_a_bad_name_is_refused(
    harness: Harness, client: TestClient, new_name: str
) -> None:
    harness.write(FILE)
    harness.profiles(FakeCatalogue({}))
    body = {"new_name": new_name, "revision": harness.revision()}
    assert refused(send(client, "POST", f"{URL}/hosted/rename", body), 400).startswith("new_name:")
    assert harness.text() == FILE


# ── Contract ─────────────────────────────────────────────────────────────


def test_responses_conform_to_the_contract(harness: Harness, client: TestClient) -> None:
    check = ContractChecker()
    harness.write(with_host("handwriting"))
    harness.profiles(FakeCatalogue({"Theses": "hosted"}))
    body = check.check(client.get(URL), 200)
    rev = body["revision"]
    body = check.check(send(client, "PUT", f"{URL}/notes", {"entry": ROUTER, "revision": rev}), 200)
    rev = body["revision"]
    check.check(send(client, "PUT", f"{URL}/none", {"entry": ROUTER, "revision": rev}), 400)
    check.check(send(client, "PUT", f"{URL}/notes", {"entry": ROUTER, "revision": "stale"}), 409)
    check.check(send(client, "DELETE", f"{URL}/handwriting", {"revision": rev}), 409)
    check.check(send(client, "DELETE", f"{URL}/missing", {"revision": rev}), 404)
    rename = {"new_name": "hosted", "revision": rev}
    check.check(send(client, "POST", f"{URL}/notes/rename", rename), 409)
    check.check(send(client, "POST", f"{URL}/missing/rename", rename), 404)
    check.check(send(client, "POST", f"{URL}/notes/rename", {**rename, "new_name": "none"}), 400)
    body = check.check(
        send(client, "POST", f"{URL}/notes/rename", {**rename, "new_name": "notes-2"}), 200
    )
    check.check(send(client, "DELETE", f"{URL}/notes-2", {"revision": body["revision"]}), 200)
    assert check.operations >= FAMILIES["document_routers"]
