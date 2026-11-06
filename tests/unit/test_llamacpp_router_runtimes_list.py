"""``GET /v1/runtimes`` items from the router (one-llamacpp-router, tasks 3.7 and 5.2).

``compose_runtimes.list_runtimes`` gives one ``router`` item with a ``models``
list (per-model state, roles, memory when known) and the OCR items unchanged.
The retired ids ``chat``, ``embeddings`` and ``decision-<name>`` are gone.
Reading starts nothing and writes nothing.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_llamacpp_router_compose_support import (
    CHAT,
    CLEF,
    EMBED,
    RouterRig,
    composed_rig,
    point_at,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

#: The fields of every item (spec llamacpp-runtimes "A route lists the runtimes").
ITEM_FIELDS = {
    "id", "role", "mode", "state", "reason", "reason_text", "memory_bytes",
    "clients", "used_by", "address", "files_checked", "models",
}  # fmt: skip
MODEL_FIELDS = {"model", "roles", "state", "reason", "memory_bytes"}
CLEF_DECISION = {
    "clef-local": {
        "kind": "llamacpp", "address": "http://127.0.0.1:8080", "model": CLEF,
        "images": False, "server": "managed",
    }
}  # fmt: skip


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from composed_rig(tmp_path, monkeypatch)


def _items() -> dict[str, dict[str, Any]]:
    from omrs import compose_runtimes

    return {item["id"]: item for item in compose_runtimes.list_runtimes()}


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    if not root.exists():
        return {}
    return {
        str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def test_one_router_item_and_no_retired_ids(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec "Old runtime ids gone" and "List shape"."""
    point_at(rig, monkeypatch, decision=CLEF_DECISION)

    items = _items()

    assert list(items) == ["router"]
    router = items["router"]
    assert set(router) == ITEM_FIELDS
    assert (router["role"], router["mode"], router["state"]) == ("router", "managed", "stopped")
    assert router["address"] is None


def test_the_router_lists_each_model_with_its_roles(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec "Router models listed": embedding and classification models, each with roles."""
    from omrs.integrations.llamacpp_runtime.hashes import hash_file

    entries = rig.entries()
    entries[2]["sha256"] = hash_file(entries[2]["file"])  # a decision entry needs one
    point_at(rig, monkeypatch, entries=entries, decision=CLEF_DECISION)

    models = {row["model"]: row for row in _items()["router"]["models"]}

    assert list(models) == [EMBED, CHAT, CLEF]
    assert all(set(row) == MODEL_FIELDS for row in models.values())
    assert models[EMBED]["roles"] == ["embeddings"]
    assert models[CHAT]["roles"] == ["classification"]
    assert models[CLEF]["roles"] == ["decision"]
    assert {row["state"] for row in models.values()} == {"unloaded"}


def test_a_decision_entry_without_a_recorded_sha256_is_refused(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    point_at(rig, monkeypatch, decision=CLEF_DECISION)

    rows = {row["model"]: row for row in _items()["router"]["models"]}

    assert (rows[CLEF]["state"], rows[CLEF]["reason"]) == ("failed", "model-invalid")
    assert rows[EMBED]["state"] == "unloaded"


def test_used_by_names_the_settings_whose_roles_run_on_the_router(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    point_at(rig, monkeypatch, decision=CLEF_DECISION)

    assert _items()["router"]["used_by"] == [
        "decision_models",
        "llamacpp_chat_model",
        "llamacpp_embed_model",
    ]


def test_an_entry_with_no_file_is_not_downloaded(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec llamacpp-server "Lifecycle states": a listed entry with no file."""
    entries = rig.entries()
    entries[1]["file"] = None
    point_at(rig, monkeypatch, entries=entries)

    rows = {row["model"]: row for row in _items()["router"]["models"]}

    assert (rows[CHAT]["state"], rows[CHAT]["reason"]) == ("not-downloaded", None)
    assert rows[EMBED]["state"] == "unloaded"


def test_a_broken_entry_is_failed_with_its_fixed_reason(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    entries = rig.entries()
    entries[1]["sha256"] = "0" * 64  # not the file's SHA-256
    point_at(rig, monkeypatch, entries=entries)

    rows = {row["model"]: row for row in _items()["router"]["models"]}

    assert (rows[CHAT]["state"], rows[CHAT]["reason"]) == ("failed", "file-changed")


def test_reading_starts_nothing_and_writes_nothing(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec "Reading starts nothing", also with files whose SHA-256 is recorded."""
    from omrs.integrations.llamacpp_runtime.hashes import hash_file
    from omrs.integrations.llamacpp_runtime.state import state_root

    entries = rig.entries()
    for item in entries:
        item["sha256"] = hash_file(item["file"])
    point_at(rig, monkeypatch, entries=entries)
    before = _snapshot(state_root())

    _items()
    _items()

    assert _snapshot(state_root()) == before
    assert rig.starts() == 0


def test_a_running_router_shows_its_loaded_model_and_address(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose, compose_runtimes
    from omrs.core.providers.embeddings import llamacpp

    point_at(rig, monkeypatch)
    compose_runtimes.install_gates(None)
    llamacpp.build(compose.get_settings()).get_text_embedding("hello")

    router = _items()["router"]
    states = {row["model"]: row["state"] for row in router["models"]}

    assert (router["state"], router["clients"]) == ("running", "some")
    assert router["address"] == f"127.0.0.1:{rig.port}"
    assert isinstance(router["memory_bytes"], int) and router["memory_bytes"] > 0
    assert states == {EMBED: "loaded", CHAT: "unloaded", CLEF: "unloaded"}


def test_an_external_router_lists_its_models_without_file_checks(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    point_at(rig, monkeypatch, LLAMACPP_ROUTER_SERVER="external")

    router = _items()["router"]

    assert (router["mode"], router["files_checked"]) == ("external", False)
    assert [row["model"] for row in router["models"]] == [EMBED, CHAT, CLEF]
    assert rig.starts() == 0


def test_find_runtime_knows_the_router_and_not_the_old_ids(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose_runtimes

    point_at(rig, monkeypatch, decision=CLEF_DECISION)

    assert compose_runtimes.find_runtime("router") is not None
    for old in ("chat", "embeddings", "decision-clef-local"):
        assert compose_runtimes.find_runtime(old) is None


def test_model_memory_comes_from_the_router_figure_when_it_reports_one() -> None:
    """Design D9: the per-model row shows the router's own memory figure when there is one."""
    from omrs.compose_runtimes import model_memory_bytes

    device = {"kind": "device", "model": 100, "context": 20, "compute": 3}
    host = {"kind": "host", "model": 4, "context": 0, "compute": 5}
    measured = {"status": "measured", "effective": {"n_ctx": 1, "devices": [device, host]}}

    assert model_memory_bytes({"memory": measured}) == 132
    assert model_memory_bytes({"memory": {"status": "measuring", "effective": None}}) is None
    assert model_memory_bytes({}) is None
