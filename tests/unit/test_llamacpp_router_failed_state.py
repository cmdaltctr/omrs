"""A failed model load shows as the model state ``failed`` (one-llamacpp-router).

llama.cpp b11941 never sends the status value ``failed``. A failed load reads
``unloaded`` with ``failed: true`` and the child's ``exit_code``
(``server-models.cpp`` ~2162, ``is_failed()`` in ``server-models.h``). The panel
state reads that flag. A fake router ``llama-server`` stands in; no network is used.
"""

from __future__ import annotations

import sys
from typing import Any

import httpx
import pytest

pytest.importorskip("fastapi")

from tests.fixtures.llamacpp.harness import wait_until  # noqa: E402
from tests.fixtures.llamacpp.install import write_fake_env  # noqa: E402
from tests.unit import test_web_llamacpp_router_support as support  # noqa: E402

from omrs.config.llamacpp_models import CLASSIFY_MODEL  # noqa: E402
from omrs.transports.api.llamacpp_server import _live_state  # noqa: E402

rig = support.rig
harness = support.harness

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")


@pytest.mark.parametrize(
    ("status", "state"),
    [
        ({"value": "unloaded", "failed": True, "exit_code": 1}, "failed"),
        ({"value": "unloaded"}, "unloaded"),
        ({"value": "loading"}, "loading"),
        ({"value": "loaded"}, "loaded"),
        (None, "unloaded"),
    ],
)
def test_the_failed_flag_is_the_failed_model_state(
    status: dict[str, Any] | None, state: str
) -> None:
    assert _live_state(status) == state


def test_a_model_whose_load_failed_shows_failed_in_the_panel(rig: Any) -> None:
    with rig() as r:
        r.save_files()
        write_fake_env(
            r.binary, FAKE_LLAMA_STARTS=str(r.starts_file), FAKE_LLAMA_LOAD_FAIL=CLASSIFY_MODEL
        )
        assert r.post("start").json()["state"] == "running"
        base = f"http://127.0.0.1:{r.port}"
        assert httpx.post(f"{base}/models/load", json={"model": CLASSIFY_MODEL}).status_code == 200

        assert wait_until(lambda: r.entry("qwen3-4b")["state"] == "failed", 15), r.get()
        assert r.entry("qwen3-embedding-4b")["state"] == "unloaded"
