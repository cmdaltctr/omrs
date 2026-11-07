"""Shared helpers of the compose-level router tests (one-llamacpp-router, tasks 3.7 to 5.2).

The file has no tests of its own. It points the process settings at the fake
router of :class:`tests.unit.test_llamacpp_router_worker.RouterRig`: the
environment holds the router mode, address and program, and ``omrs.jsonc`` in
the test's ``OMRS_CONFIG_DIR`` holds ``llamacpp_models`` and
``decision_models``. No real ``llama-server`` starts.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_llamacpp_router_worker import CHAT, CLEF, EMBED, RouterRig, rig_fixture

__all__ = ["CHAT", "CLEF", "EMBED", "RouterRig", "composed_rig", "point_at", "write_config"]


def write_config(**maps: Any) -> Path:
    """Write *maps* as ``omrs.jsonc`` in the test's config folder; return the file."""
    folder = Path(os.environ["OMRS_CONFIG_DIR"])
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = folder / "omrs.jsonc"
    path.write_text(json.dumps(maps), encoding="utf-8")
    return path


def point_at(
    rig: RouterRig,
    monkeypatch: pytest.MonkeyPatch,
    *,
    entries: list[dict[str, Any]] | None = None,
    decision: dict[str, Any] | None = None,
    **env: str,
) -> None:
    """Point the process settings at *rig*'s fake router as a managed router.

    Args:
        rig: The fake router install.
        monkeypatch: The test's monkeypatch.
        entries: The ``llamacpp_models`` entries; the rig's three by default.
        decision: The ``decision_models`` map, when any.
        **env: More environment values (they win over the defaults here).
    """
    items = rig.entries() if entries is None else entries
    maps: dict[str, Any] = {
        "llamacpp_models": {f"m{i}": item for i, item in enumerate(items)},
    }
    if decision is not None:
        maps["decision_models"] = decision
    write_config(**maps)
    values = {
        "LLAMACPP_ROUTER_SERVER": "managed",
        "LLAMACPP_ROUTER_URL": f"http://127.0.0.1:{rig.port}/v1",
        "LLAMACPP_SERVER_BINARY": str(rig.binary),
        "LLAMACPP_ROUTER_MEMORY_MARGIN_MIB": "0",
        "LLAMACPP_EMBED_MODEL": EMBED,
        "LLAMACPP_CHAT_MODEL": CHAT,
        **env,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def composed_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    """Body of a fixture: a router rig, with the process composition reset at the end."""
    from omrs import compose_runtimes

    rig_iter = rig_fixture(tmp_path, monkeypatch)
    rig = next(rig_iter)
    try:
        yield rig
    finally:
        compose_runtimes.reset()
        for _ in rig_iter:  # runs the rig's cleanup
            pass
