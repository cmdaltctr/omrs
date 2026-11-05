"""``GET /v1/runtimes`` lists a managed decision runtime (document-reading-routers, task 2.4).

A ``llamacpp`` decision model entry with ``server: "managed"`` in
``omrs.jsonc`` is the runtime ``decision-<entry name>``, role ``decision``. An
external entry is not a runtime. The list starts nothing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit import test_web_connections_edit as edit  # noqa: E402
from tests.unit.llamacpp_fake import free_port  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

harness = edit.harness
SHA = "c" * 64


def _write_maps(tmp_path: Path) -> dict[str, Any]:
    """Write the decision models to the test's ``omrs.jsonc``; return launch overrides."""
    port = free_port()
    model, projector = tmp_path / "clef-q8_0.gguf", tmp_path / "mmproj.gguf"
    managed = {
        "kind": "llamacpp", "address": f"http://127.0.0.1:{port}", "model": "clef-flash",
        "images": True, "server": "managed", "model_file": str(model),
        "projector_file": str(projector), "model_sha256": SHA, "projector_sha256": SHA,
    }  # fmt: skip
    external = {"kind": "llamacpp", "address": f"http://127.0.0.1:{free_port()}", "model": "c"}
    data = {"decision_models": {"clef": managed, "outside": external}}
    folder = Path(os.environ["OMRS_CONFIG_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "omrs.jsonc").write_text(json.dumps(data), encoding="utf-8")
    return {
        "llamacpp_chat_url": f"http://127.0.0.1:{free_port()}/v1",
        "llamacpp_embed_url": f"http://127.0.0.1:{free_port()}/v1",
        "llamacpp_server_binary": str(tmp_path / "bin" / "llama-server"),
    }


def test_a_managed_decision_entry_is_listed_as_a_decision_runtime(
    harness: Any, tmp_path: Path
) -> None:
    with harness(**_write_maps(tmp_path)) as h:
        response = h.client.get("/v1/runtimes")

    assert response.status_code == 200, response.text
    items = {item["id"]: item for item in response.json()["runtimes"]}
    assert sorted(items) == ["chat", "decision-clef", "embeddings"]
    decision = items["decision-clef"]
    assert (decision["role"], decision["mode"], decision["state"]) == (
        "decision", "managed", "stopped",
    )  # fmt: skip
    assert decision["files_checked"] is True
    assert decision["used_by"] == ["decision_models"]
