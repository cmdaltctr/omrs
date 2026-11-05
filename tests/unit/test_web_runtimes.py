"""``GET /v1/runtimes`` and ``POST /v1/runtimes/{runtime_id}/stop`` (task 7.2, design D8, D11).

A client process (``tests/fixtures/llamacpp/client.py``) starts the fake
``llama-server`` as another OMRS process would. The list reads the runtime
files only; the stop is an operator stop that a bearer token never reaches.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.fixtures.llamacpp.harness import (  # noqa: E402
    FakeRuntime,
    RuntimeEnv,
    pid_alive,
    runtime_env_fixture,
    wait_until,
)
from tests.fixtures.ocr_worker.runtime_engine import make_engine  # noqa: E402
from tests.unit import test_web_connections_edit as edit  # noqa: E402
from tests.unit.llamacpp_fake import free_port  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import (  # noqa: E402
    FAMILIES,
    ContractChecker,
)

from omrs.core.answer.settings import AnswerSettings  # noqa: E402
from omrs.integrations.llamacpp_runtime import (  # noqa: E402
    read_server_record,
    runtime_dir,
    state_root,
)
from omrs.transports.api import security  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

harness = edit.harness
ORIGIN = edit.ORIGIN
LIST = "/v1/runtimes"
FIELDS = {
    "id",
    "role",
    "mode",
    "state",
    "reason",
    "reason_text",
    "memory_bytes",
    "clients",
    "used_by",
    "address",
    "files_checked",
}


@pytest.fixture
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimeEnv]:
    yield from runtime_env_fixture(tmp_path, monkeypatch)


def _urls(**extra: Any) -> dict[str, Any]:
    """Loopback addresses where nothing listens, so no probe leaves this computer."""
    return {
        "llamacpp_chat_url": f"http://127.0.0.1:{free_port()}/v1",
        "llamacpp_embed_url": f"http://127.0.0.1:{free_port()}/v1",
        **extra,
    }


def _managed_chat(fake: FakeRuntime, port: int) -> dict[str, Any]:
    return _urls(
        llamacpp_chat_server="managed",
        llamacpp_server_binary=str(fake.binary),
        llamacpp_chat_url=f"http://127.0.0.1:{port}/v1",
        llamacpp_context_window=2048,
        answer=AnswerSettings(enabled=True, provider="llamacpp", model=str(fake.model)),
    )


def _items(h: Any) -> dict[str, dict[str, Any]]:
    response = h.client.get(LIST)
    assert response.status_code == 200, response.text
    return {item["id"]: item for item in response.json()["runtimes"]}


def _stop(h: Any, runtime_id: str, **kwargs: Any) -> Any:
    kwargs.setdefault("headers", ORIGIN)
    return h.client.post(f"{LIST}/{runtime_id}/stop", **kwargs)


def _snapshot(root: Path) -> dict[str, tuple[int, bytes]]:
    return {
        p.relative_to(root).as_posix(): (p.stat().st_mtime_ns, p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _running_chat(env: RuntimeEnv) -> tuple[FakeRuntime, int, Any]:
    """Start the managed Chat server from a client process; return the fake, port and client."""
    fake = env.fake()
    port = free_port()
    client = env.client()
    assert client.join(fake.chat(port))["ok"] is True
    return fake, port, client


# ── GET /v1/runtimes ─────────────────────────────────────────────────────


def test_the_default_list_holds_chat_and_embeddings_as_external(harness: Any) -> None:
    check = ContractChecker()
    with harness(**_urls()) as h:
        response = h.client.get(LIST)
        check.check(response, 200)
        items = {item["id"]: item for item in response.json()["runtimes"]}
    assert list(items) == ["chat", "embeddings"]
    for item in items.values():
        assert set(item) == FIELDS
        assert (item["mode"], item["state"], item["clients"]) == ("external", "stopped", "none")
    assert items["chat"]["used_by"] == ["llamacpp_chat_url", "llamacpp_classify_url"]
    assert items["embeddings"]["used_by"] == ["llamacpp_embed_url"]


def test_a_classification_address_of_its_own_does_not_use_the_chat_runtime(harness: Any) -> None:
    with harness(**_urls(llamacpp_classify_url=f"http://127.0.0.1:{free_port()}/v1")) as h:
        assert _items(h)["chat"]["used_by"] == ["llamacpp_chat_url"]


def test_classification_does_not_use_a_managed_chat_runtime_when_chat_is_not_llamacpp(
    harness: Any,
) -> None:
    """The server has no Chat model to load, so classification goes to the Chat address."""
    with harness(
        **_urls(
            llamacpp_chat_server="managed",
            answer=AnswerSettings(enabled=True, provider="openrouter", model="x/y"),
        )
    ) as h:
        assert _items(h)["chat"]["used_by"] == ["llamacpp_chat_url"]


def test_an_ocr_engine_that_declares_a_runtime_is_listed(harness: Any, tmp_path: Path) -> None:
    workers = tmp_path / "workers"
    make_engine(workers, "declares")
    make_engine(workers, "plain", runtime=False)
    routes = {"ocr_engine_primary": "declares", "ocr_engine_fallback": "plain"}
    with harness(**_urls(ocr_workers_dir=str(workers), **routes)) as h:
        items = _items(h)
    assert sorted(items) == ["chat", "embeddings", "ocr-declares"]
    ocr = items["ocr-declares"]
    assert (ocr["role"], ocr["mode"], ocr["files_checked"]) == ("ocr", "managed", True)
    assert ocr["used_by"] == ["ocr_engines"]


def test_an_external_ocr_runtime_says_its_files_are_not_checked(
    harness: Any, tmp_path: Path
) -> None:
    workers = tmp_path / "workers"
    make_engine(workers, "declares")
    external = f"http://127.0.0.1:{free_port()}"
    settings = _urls(
        ocr_workers_dir=str(workers),
        ocr_engine_primary="declares",
        ocr_engine_fallback="declares",
        ocr_runtime_url=external,
    )
    with harness(**settings) as h:
        ocr = _items(h)["ocr-declares"]
    assert (ocr["mode"], ocr["files_checked"]) == ("external", False)
    assert ocr["used_by"] == ["ocr_engines"]


def test_reading_starts_nothing_and_changes_no_runtime_file(
    harness: Any, runtime_env: RuntimeEnv
) -> None:
    idle = runtime_env.fake("idle")
    with harness(**_managed_chat(idle, free_port())) as h:
        assert _items(h)["chat"]["state"] == "stopped"
        assert not (state_root() / "runtimes").exists()
        assert idle.starts() == []

    fake, port, _client = _running_chat(runtime_env)
    before = _snapshot(state_root())
    with harness(**_managed_chat(fake, port)) as h:
        chat = _items(h)["chat"]
        _items(h)
    assert _snapshot(state_root()) == before
    assert len(fake.starts()) == 1
    assert (chat["mode"], chat["state"], chat["clients"]) == ("managed", "running", "some")
    assert chat["address"] == f"127.0.0.1:{port}"
    assert isinstance(chat["memory_bytes"], int) and chat["memory_bytes"] > 0


# ── POST /v1/runtimes/{runtime_id}/stop ──────────────────────────────────


def test_a_bearer_token_cannot_stop_a_runtime_and_no_signal_goes(
    harness: Any, runtime_env: RuntimeEnv
) -> None:
    fake, port, client = _running_chat(runtime_env)
    pid = int(fake.starts()[0]["pid"])
    before = _snapshot(state_root())
    with harness(**_managed_chat(fake, port)) as h:
        h.client.cookies.clear()
        header = edit.bearer(h.policy, "read", "graph", "run")  # every bearer scope
        response = _stop(h, "chat", headers=header)
    assert response.status_code == 403
    assert pid_alive(pid)
    assert _snapshot(state_root()) == before
    assert client.chat()["ok"] is True


def test_a_session_without_manage_cannot_stop_a_runtime(
    harness: Any, runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, port, _client = _running_chat(runtime_env)
    with harness(**_managed_chat(fake, port)) as h:
        monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"manage"})
        assert _stop(h, "chat").status_code == 403
    assert pid_alive(int(fake.starts()[0]["pid"]))


def test_an_external_runtime_gives_409_external_runtime(harness: Any) -> None:
    check = ContractChecker()
    with harness(**_urls()) as h:
        response = _stop(h, "embeddings")
        check.check(response, 409)
    body = response.json()
    assert (body["status"], body["reason"]) == ("error", "external-runtime")
    assert "external" not in body["message"].split()[0].lower()  # a plain sentence, not a code


@pytest.mark.parametrize("runtime_id", ["ocr-not-listed", "ocr-", "router", "chat%3Bx", "Chat"])
def test_an_unknown_or_malformed_id_is_404(harness: Any, runtime_id: str) -> None:
    check = ContractChecker()
    with harness(**_urls()) as h:
        response = _stop(h, runtime_id)
        if runtime_id == "ocr-not-listed":
            check.check(response, 404)
    assert response.status_code == 404


def test_stop_a_managed_runtime_returns_the_stopped_item(
    harness: Any, runtime_env: RuntimeEnv
) -> None:
    check = ContractChecker()
    fake, port, client = _running_chat(runtime_env)
    pid = int(fake.starts()[0]["pid"])
    with harness(**_managed_chat(fake, port)) as h:
        response = _stop(h, "chat")
        check.check(response, 200)
        check.check(h.client.get(LIST), 200)
    item = response.json()
    assert (item["id"], item["mode"], item["state"]) == ("chat", "managed", "stopped")
    assert wait_until(lambda: not pid_alive(pid))
    record = read_server_record(runtime_dir(state_root(), "chat"))
    assert record is not None and record.stopped_by == "operator"
    refused = client.chat()
    assert (refused["ok"], refused["reason"]) == (False, "operator-stop")
    assert check.operations >= FAMILIES["runtimes"]
