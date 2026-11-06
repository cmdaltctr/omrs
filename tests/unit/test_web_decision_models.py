"""Decision model routes: list, save, delete and Test (document-reading-routers, task 4.1).

Each test follows a scenario of the ``decision-model-providers`` and
``workspace-settings`` deltas. No test contacts a model: the Test route's
check function is replaced by a fake.
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
    Harness,
    make_harness,
    refused,
    send,
    signed_in,
)

from omrs import compose_decision  # noqa: E402

URL = "/v1/settings/decision-models"
KEY_VALUE = "zz-secret-key-zz"
LOCAL = {"kind": "llamacpp", "address": "http://127.0.0.1:9200", "model": "clef-q8_0"}


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return make_harness(tmp_path, monkeypatch)


@pytest.fixture
def client(harness: Harness) -> TestClient:
    return signed_in(harness)


def models(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in body["models"]}


# ── List ─────────────────────────────────────────────────────────────────


def test_list_shows_each_entry_without_a_key(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROUTER_TEST_KEY", KEY_VALUE)
    harness.write(FILE)
    response = client.get(URL)
    assert response.status_code == 200, response.text
    assert KEY_VALUE not in response.text and "env://" not in response.text
    found = models(response.json())
    assert sorted(found) == ["cf", "clef-local", "jev"]
    local, jev, cf = found["clef-local"], found["jev"], found["cf"]
    assert (local["hosted"], local["key_state"], local["used_by"]) == (
        False,
        "not-needed",
        ["handwriting"],
    )
    assert (jev["hosted"], jev["key_state"], jev["used_by"]) == (True, "resolvable", ["hosted"])
    assert (cf["hosted"], cf["key_state"], cf["not_yet_tested"]) == (True, "not-set", True)
    assert local["not_yet_tested"] is False
    kinds = {kind["name"]: kind["not_yet_tested"] for kind in response.json()["kinds"]}
    assert kinds == {"cloudflare": True, "llamacpp": False, "ollama": True, "typesafe": False}


def test_an_env_reference_that_is_not_set_is_unresolvable(
    harness: Harness, client: TestClient
) -> None:
    harness.write(FILE)
    assert models(client.get(URL).json())["jev"]["key_state"] == "unresolvable"


@pytest.mark.parametrize(
    ("reference", "state"),
    [("keychain://typesafe", "reference-set"), ("file://{secrets}/jev.key", "resolvable")],
)
def test_keychain_and_file_references(
    harness: Harness, client: TestClient, reference: str, state: str
) -> None:
    secrets = harness.folder / "secrets"
    secrets.mkdir(mode=0o700)
    (secrets / "jev.key").write_text(KEY_VALUE, encoding="utf-8")
    harness.write(FILE.replace("env://ROUTER_TEST_KEY", reference.format(secrets=secrets)))
    response = client.get(URL)
    assert models(response.json())["jev"]["key_state"] == state
    assert KEY_VALUE not in response.text


def test_list_with_no_file(harness: Harness, client: TestClient) -> None:
    body = client.get(URL).json()
    assert (body["revision"], body["models"]) == ("absent", [])


def test_page_load_contacts_no_model(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a model was contacted")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    harness.write(FILE)
    assert client.get(URL).status_code == 200


# ── Access ───────────────────────────────────────────────────────────────


def test_writes_and_test_refuse_a_bearer_credential(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    client.cookies.clear()
    headers = {**ORIGIN, **bearer(harness.policy, "read", "run", "graph")}
    body = {"entry": LOCAL, "revision": harness.revision()}
    assert client.put(f"{URL}/new", json=body, headers=headers).status_code == 403
    assert client.post(f"{URL}/jev/test", headers=headers).status_code == 403
    delete = {"revision": harness.revision()}
    assert client.request("DELETE", f"{URL}/cf", json=delete, headers=headers).status_code == 403
    assert client.get(URL, headers=bearer(harness.policy, "read")).status_code == 200
    assert harness.text() == FILE


# ── Save ─────────────────────────────────────────────────────────────────


def test_add_a_local_entry_keeps_comments(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    entry = {**LOCAL, "server": "managed"}  # the file lives in llamacpp_models (router D3)
    response = send(
        client, "PUT", f"{URL}/clef-two", {"entry": entry, "revision": harness.revision()}
    )
    assert response.status_code == 200, response.text
    assert harness.data()["decision_models"]["clef-two"] == {**entry, "images": False}
    assert "// decision models" in harness.text()
    assert models(response.json())["clef-two"]["server"] == "managed"
    assert response.json()["revision"] == harness.revision()


def test_an_edit_without_a_key_keeps_the_saved_reference(
    harness: Harness, client: TestClient
) -> None:
    harness.write(FILE)
    entry = {"kind": "typesafe", "address": "https://api.example.test", "model": "jev-2"}
    response = send(client, "PUT", f"{URL}/jev", {"entry": entry, "revision": harness.revision()})
    assert response.status_code == 200, response.text
    saved = harness.data()["decision_models"]["jev"]
    assert saved["model"] == "jev-2"
    assert saved["key"] == "env://ROUTER_TEST_KEY"


def test_an_edit_with_a_null_key_clears_the_reference(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    entry = {"kind": "typesafe", "address": "https://api.example.test", "model": "jev", "key": None}
    response = send(client, "PUT", f"{URL}/jev", {"entry": entry, "revision": harness.revision()})
    assert response.status_code == 200, response.text
    assert "key" not in harness.data()["decision_models"]["jev"]


def test_a_literal_key_is_refused_and_nothing_is_written(
    harness: Harness, client: TestClient
) -> None:
    harness.write(FILE)
    entry = {**LOCAL, "address": "https://api.example.test", "key": KEY_VALUE}
    response = send(client, "PUT", f"{URL}/jev2", {"entry": entry, "revision": harness.revision()})
    message = refused(response, 400)
    assert KEY_VALUE not in response.text
    assert "key" in message
    assert harness.text() == FILE


def test_a_stale_revision_gets_409_without_a_reason(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    response = send(client, "PUT", f"{URL}/x", {"entry": LOCAL, "revision": "stale"})
    refused(response, 409, None)
    assert harness.text() == FILE


# ── Delete ───────────────────────────────────────────────────────────────


def test_remove_an_entry_in_use_is_refused_naming_the_router(
    harness: Harness, client: TestClient
) -> None:
    harness.write(FILE)
    response = send(client, "DELETE", f"{URL}/clef-local", {"revision": harness.revision()})
    message = refused(response, 409, "in-use")
    assert "handwriting" in message
    assert harness.text() == FILE


def test_remove_an_unused_entry(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    response = send(client, "DELETE", f"{URL}/cf", {"revision": harness.revision()})
    assert response.status_code == 200, response.text
    assert "cf" not in harness.data()["decision_models"]
    assert "cf" not in models(response.json())


def test_remove_an_unknown_entry_gets_404(harness: Harness, client: TestClient) -> None:
    harness.write(FILE)
    refused(send(client, "DELETE", f"{URL}/missing", {"revision": harness.revision()}), 404)


# ── Test ─────────────────────────────────────────────────────────────────


def _fake_test(seen: list[Any], result: dict[str, Any]) -> Any:
    def test_decision_model(settings: Any, name: str, *, transport: Any = None) -> dict:
        seen.append((dict(settings.decision_models), name))
        return result

    return test_decision_model


def test_test_runs_the_checks_on_the_entry_saved_now(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []
    result = {
        "status": "ok",
        "quantisation": "Q8_0: accepted",
        "projector": "Projector loaded",
        "build": None,
        "key": KEY_VALUE,
        "reply": "raw reply body",
    }
    monkeypatch.setattr(
        compose_decision, "test_decision_model", _fake_test(seen, result), raising=False
    )
    harness.write(FILE)
    response = send(client, "POST", f"{URL}/clef-local/test")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "ok",
        "name": "clef-local",
        "result": "ok",
        "quantisation": "Q8_0: accepted",
        "projector": "Projector loaded",
        "build": None,
    }
    assert KEY_VALUE not in response.text and "raw reply" not in response.text
    entries, name = seen[0]
    assert name == "clef-local" and set(entries) == {"cf", "clef-local", "jev"}


def test_test_gives_the_fixed_reason(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = {"status": "unreachable", "quantisation": "Quantisation not checked"}
    monkeypatch.setattr(
        compose_decision, "test_decision_model", _fake_test([], result), raising=False
    )
    harness.write(FILE)
    body = send(client, "POST", f"{URL}/clef-local/test").json()
    assert (body["result"], body["projector"], body["build"]) == ("unreachable", None, None)


def test_test_maps_an_unknown_reason_to_request_failed(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = {"status": "Traceback: secret detail", "quantisation": "x"}
    monkeypatch.setattr(
        compose_decision, "test_decision_model", _fake_test([], result), raising=False
    )
    harness.write(FILE)
    response = send(client, "POST", f"{URL}/clef-local/test")
    assert response.json()["result"] == "request-failed"
    assert "secret detail" not in response.text


def test_test_of_an_unknown_entry_gets_404(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(
        compose_decision, "test_decision_model", _fake_test(seen, {}), raising=False
    )
    harness.write(FILE)
    refused(send(client, "POST", f"{URL}/missing/test"), 404)
    assert seen == []


# ── Contract ─────────────────────────────────────────────────────────────


def test_responses_conform_to_the_contract(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = {"status": "ok", "quantisation": "Q8_0", "projector": None, "build": "b11941"}
    monkeypatch.setattr(
        compose_decision, "test_decision_model", _fake_test([], result), raising=False
    )
    check = ContractChecker()
    harness.write(FILE)
    body = check.check(client.get(URL), 200)
    body = check.check(
        send(client, "PUT", f"{URL}/new", {"entry": LOCAL, "revision": body["revision"]}), 200
    )
    check.check(send(client, "PUT", f"{URL}/new", {"entry": {"kind": "x"}, "revision": "r"}), 400)
    check.check(send(client, "PUT", f"{URL}/new", {"entry": LOCAL, "revision": "stale"}), 409)
    check.check(send(client, "DELETE", f"{URL}/clef-local", {"revision": body["revision"]}), 409)
    check.check(send(client, "DELETE", f"{URL}/missing", {"revision": body["revision"]}), 404)
    check.check(send(client, "DELETE", f"{URL}/new", {"revision": body["revision"]}), 200)
    check.check(send(client, "POST", f"{URL}/clef-local/test"), 200)
    check.check(send(client, "POST", f"{URL}/missing/test"), 404)
    assert check.operations >= FAMILIES["decision_models"]
