"""``GET /v1/runtimes`` lists a managed decision model under the router (router task 5.2).

A ``llamacpp`` decision model entry with ``server: "managed"`` in ``omrs.jsonc``
names a ``llamacpp_models`` entry; that model is a row of the ``router`` item
with the role ``decision``. No ``decision-<name>`` runtime exists. An external
entry is not a router model. The list starts nothing.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit import test_web_connections_edit as edit  # noqa: E402
from tests.unit.test_llamacpp_router_compose_support import (  # noqa: E402
    CLEF,
    RouterRig,
    composed_rig,
    write_config,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

harness = edit.harness


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from composed_rig(tmp_path, monkeypatch)


def _write_maps(rig: RouterRig) -> dict[str, Any]:
    """Write the model list and decision models to ``omrs.jsonc``; return launch overrides."""
    from omrs.integrations.llamacpp_runtime.hashes import hash_file

    entries = rig.entries()
    entries[2]["sha256"] = hash_file(entries[2]["file"])  # a decision entry needs one
    managed = {"kind": "llamacpp", "address": "http://127.0.0.1:8080", "model": CLEF,
               "server": "managed"}  # fmt: skip
    outside = {"kind": "llamacpp", "address": f"http://127.0.0.1:{rig.port + 1}", "model": "c"}
    write_config(
        llamacpp_models={f"m{i}": e for i, e in enumerate(entries)},
        decision_models={"clef": managed, "outside": outside},
    )
    return {
        "llamacpp_router_server": "managed",
        "llamacpp_router_url": f"http://127.0.0.1:{rig.port}/v1",
        "llamacpp_server_binary": str(rig.binary),
    }


def test_a_managed_decision_model_is_a_router_model(harness: Any, rig: RouterRig) -> None:
    with harness(**_write_maps(rig)) as h:
        response = h.client.get("/v1/runtimes")

    assert response.status_code == 200, response.text
    items = {item["id"]: item for item in response.json()["runtimes"]}
    assert list(items) == ["router"]
    assert "decision_models" in items["router"]["used_by"]
    rows = {row["model"]: row for row in items["router"]["models"]}
    assert (rows[CLEF]["roles"], rows[CLEF]["state"]) == (["decision"], "unloaded")
    assert "c" not in rows
    assert rig.starts() == 0
