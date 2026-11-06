"""``GET /v1/runtimes`` and ``POST /v1/runtimes/{runtime_id}/stop`` (one-llamacpp-router, 3.7).

The list holds one ``router`` item with its models, then the OCR runtimes. A
worker process (``tests/unit/test_llamacpp_router_worker.py``) starts the fake
router as another OMRS process would. The list reads the runtime files only;
the stop is an operator stop that a bearer token never reaches.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.fixtures.llamacpp.harness import pid_alive, wait_until  # noqa: E402
from tests.fixtures.ocr_worker.runtime_engine import make_engine  # noqa: E402
from tests.unit import test_web_connections_edit as edit  # noqa: E402
from tests.unit.test_llamacpp_router_compose_support import (  # noqa: E402
    CHAT,
    RouterRig,
    composed_rig,
    write_config,
)
from tests.unit.test_web_openapi_conformance_support import (  # noqa: E402
    FAMILIES,
    ContractChecker,
)

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
    "id", "role", "mode", "state", "reason", "reason_text", "memory_bytes",
    "clients", "used_by", "address", "files_checked", "models",
}  # fmt: skip


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from composed_rig(tmp_path, monkeypatch)


def _managed(rig: RouterRig, **extra: Any) -> dict[str, Any]:
    """Settings of a managed router on the rig's fake, with the rig's three entries."""
    write_config(llamacpp_models={f"m{i}": e for i, e in enumerate(rig.entries())})
    return {
        "llamacpp_router_server": "managed",
        "llamacpp_router_url": f"http://127.0.0.1:{rig.port}/v1",
        "llamacpp_server_binary": str(rig.binary),
        "llamacpp_router_memory_margin_mib": 0,
        **extra,
    }


def _external(rig: RouterRig) -> dict[str, Any]:
    return _managed(rig, llamacpp_router_server="external")


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


def _running_router(rig: RouterRig) -> tuple[Any, int]:
    """Start the managed router from a worker process; return the worker and router pid."""
    worker = rig.worker()
    assert worker.call("request", model=CHAT)["ok"] is True
    record = read_server_record(runtime_dir(state_root(), "router"))
    assert record is not None
    return worker, record.pid


# ── GET /v1/runtimes ─────────────────────────────────────────────────────


def test_the_list_holds_one_router_item_with_its_models(harness: Any, rig: RouterRig) -> None:
    check = ContractChecker()
    with harness(**_managed(rig)) as h:
        response = h.client.get(LIST)
        check.check(response, 200)
        items = {item["id"]: item for item in response.json()["runtimes"]}
    assert list(items) == ["router"]
    router = items["router"]
    assert set(router) == FIELDS
    assert (router["role"], router["mode"], router["state"]) == ("router", "managed", "stopped")
    assert [row["model"] for row in router["models"]] == [e["model"] for e in rig.entries()]


def test_an_external_router_is_listed_as_external(harness: Any, rig: RouterRig) -> None:
    with harness(**_external(rig)) as h:
        router = _items(h)["router"]
    assert (router["mode"], router["state"], router["clients"]) == ("external", "stopped", "none")


def test_an_ocr_engine_that_declares_a_runtime_is_listed(
    harness: Any, rig: RouterRig, tmp_path: Path
) -> None:
    workers = tmp_path / "workers"
    make_engine(workers, "declares")
    make_engine(workers, "plain", runtime=False)
    routes = {"ocr_engine_primary": "declares", "ocr_engine_fallback": "plain"}
    with harness(**_external(rig), ocr_workers_dir=str(workers), **routes) as h:
        items = _items(h)
    assert sorted(items) == ["ocr-declares", "router"]
    ocr = items["ocr-declares"]
    assert (ocr["role"], ocr["mode"], ocr["files_checked"]) == ("ocr", "managed", True)
    assert (ocr["used_by"], ocr["models"]) == (["ocr_engines"], [])


def test_an_external_ocr_runtime_says_its_files_are_not_checked(
    harness: Any, rig: RouterRig, tmp_path: Path
) -> None:
    workers = tmp_path / "workers"
    make_engine(workers, "declares")
    settings = {
        **_external(rig),
        "ocr_workers_dir": str(workers),
        "ocr_engine_primary": "declares",
        "ocr_engine_fallback": "declares",
        "ocr_runtime_url": f"http://127.0.0.1:{rig.port + 1}",
    }
    with harness(**settings) as h:
        ocr = _items(h)["ocr-declares"]
    assert (ocr["mode"], ocr["files_checked"]) == ("external", False)
    assert ocr["used_by"] == ["ocr_engines"]


def test_reading_starts_nothing_and_changes_no_runtime_file(harness: Any, rig: RouterRig) -> None:
    with harness(**_managed(rig)) as h:
        assert _items(h)["router"]["state"] == "stopped"
    assert rig.starts() == 0

    _worker, _pid = _running_router(rig)
    before = _snapshot(state_root())
    with harness(**_managed(rig)) as h:
        router = _items(h)["router"]
        _items(h)
    assert _snapshot(state_root()) == before
    assert rig.starts() == 1
    assert (router["mode"], router["state"], router["clients"]) == ("managed", "running", "some")
    assert router["address"] == f"127.0.0.1:{rig.port}"
    assert isinstance(router["memory_bytes"], int) and router["memory_bytes"] > 0
    states = {row["model"]: row["state"] for row in router["models"]}
    assert states[CHAT] == "loaded"


# ── POST /v1/runtimes/{runtime_id}/stop ──────────────────────────────────


def test_a_bearer_token_cannot_stop_the_router_and_no_signal_goes(
    harness: Any, rig: RouterRig
) -> None:
    """Spec "Stop refused for a bearer token"."""
    worker, pid = _running_router(rig)
    before = _snapshot(state_root())
    with harness(**_managed(rig)) as h:
        h.client.cookies.clear()
        header = edit.bearer(h.policy, "read", "graph", "run")  # every bearer scope
        response = _stop(h, "router", headers=header)
    assert response.status_code == 403
    assert pid_alive(pid)
    assert _snapshot(state_root()) == before
    assert worker.call("request", model=CHAT)["ok"] is True


def test_a_session_without_manage_cannot_stop_the_router(
    harness: Any, rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    _worker, pid = _running_router(rig)
    with harness(**_managed(rig)) as h:
        monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"manage"})
        assert _stop(h, "router").status_code == 403
    assert pid_alive(pid)


def test_an_external_router_gives_409_external_runtime(harness: Any, rig: RouterRig) -> None:
    """Spec "External runtime"."""
    check = ContractChecker()
    with harness(**_external(rig)) as h:
        response = _stop(h, "router")
        check.check(response, 409)
    body = response.json()
    assert (body["status"], body["reason"]) == ("error", "external-runtime")
    assert "external" not in body["message"].split()[0].lower()  # a plain sentence, not a code


@pytest.mark.parametrize(
    "runtime_id", ["ocr-not-listed", "ocr-", "chat", "embeddings", "decision-clef", "Router"]
)
def test_an_unknown_old_or_malformed_id_is_404(
    harness: Any, rig: RouterRig, runtime_id: str
) -> None:
    """Spec "Old id unknown"."""
    check = ContractChecker()
    with harness(**_external(rig)) as h:
        response = _stop(h, runtime_id)
        if runtime_id == "ocr-not-listed":
            check.check(response, 404)
    assert response.status_code == 404


def test_stop_the_managed_router_returns_the_stopped_item(harness: Any, rig: RouterRig) -> None:
    check = ContractChecker()
    worker, pid = _running_router(rig)
    with harness(**_managed(rig)) as h:
        response = _stop(h, "router")
        check.check(response, 200)
        check.check(h.client.get(LIST), 200)
    item = response.json()
    assert (item["id"], item["mode"], item["state"]) == ("router", "managed", "stopped")
    assert wait_until(lambda: not pid_alive(pid))
    record = read_server_record(runtime_dir(state_root(), "router"))
    assert record is not None and record.stopped_by == "operator"
    refused = worker.call("request", model=CHAT)
    assert (refused["ok"], refused["reason"]) == (False, "operator-stop")
    assert check.operations >= FAMILIES["runtimes"]
