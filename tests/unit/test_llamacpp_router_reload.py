"""A preset edit reloads only the changed model (task 4.3; design D7).

Under ``start.lock`` OMRS rewrites only the changed section of ``models.ini``
and calls ``GET /models?reload=1``. Another process that holds the model's
client lock makes the change fail for that model only (``version-busy``). Only
a router-argument change restarts the router.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from tests.fixtures.llamacpp.harness import pid_alive
from tests.unit.test_llamacpp_router_worker import (
    CHAT,
    CLEF,
    EMBED,
    RouterRig,
    as_entries,
    rig_fixture,
)

from omrs.integrations.llamacpp_runtime import children
from omrs.integrations.llamacpp_runtime.lease import RuntimeUnavailable
from omrs.integrations.llamacpp_runtime.model_reasons import ModelUnavailable
from omrs.integrations.llamacpp_runtime.preset_writer import read_preset, split_sections
from omrs.integrations.llamacpp_runtime.router_lease import open_router
from omrs.integrations.llamacpp_runtime.router_spec import router_dir
from omrs.integrations.llamacpp_runtime.state import read_server_record, state_root

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from rig_fixture(tmp_path, monkeypatch)


def _args(url: str, model: str) -> list[str]:
    items = httpx.get(f"{url}/v1/models", timeout=10).json()["data"]
    return next(i["status"]["args"] for i in items if i["id"] == model)


def _sections() -> dict[str, str]:
    return split_sections(read_preset(router_dir(state_root())))


def test_context_size_edit_reloads_only_that_model(rig: RouterRig) -> None:
    """Spec scenario "Context size edit"."""
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries(chat_ctx=8192)))
    for model in (EMBED, CHAT):
        with router.model_session(model):
            pass
    record = read_server_record(router_dir(state_root()))
    assert record is not None
    before = set(children.direct_children(record.pid))
    embed_text = _sections()[EMBED]

    result = router.update_entries(as_entries(rig.entries(chat_ctx=4096)))

    assert result == {EMBED: "unchanged", CHAT: "reloaded", CLEF: "unchanged"}
    assert _sections()[EMBED] == embed_text  # byte-identical
    assert "ctx-size = 4096" in _sections()[CHAT]
    after = set(children.direct_children(record.pid))
    assert len(before & after) == 1  # the embedding child kept its pid
    with router.model_session(CHAT) as url:
        args = _args(url, CHAT)
    assert args[args.index("--ctx-size") + 1] == "4096"
    assert rig.starts() == 1
    stored = read_server_record(router_dir(state_root()))
    assert stored is not None and stored.models[CHAT] != record.models[CHAT]
    assert stored.models[EMBED] == record.models[EMBED]


def test_model_in_use_elsewhere_is_version_busy(rig: RouterRig) -> None:
    """Spec scenario "Model in use elsewhere"."""
    cli = rig.worker(entries=rig.entries(chat_ctx=8192))
    assert cli.call("request", model=CHAT)["ok"]
    web = open_router(rig.manager(), rig.spec(), as_entries(rig.entries(chat_ctx=4096)))

    with pytest.raises(ModelUnavailable) as caught:
        with web.model_session(CHAT):
            pass
    assert caught.value.reason == "version-busy"
    with web.model_session(EMBED) as url:
        assert httpx.post(f"{url}/v1/embeddings", json={"model": EMBED}).status_code == 200
    assert "ctx-size = 8192" in _sections()[CHAT]
    assert cli.call("request", model=CHAT)["ok"]  # the CLI's model keeps running


def test_update_reports_version_busy_per_model(rig: RouterRig) -> None:
    cli = rig.worker()
    assert cli.call("request", model=CHAT)["ok"]
    web = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    web.join()

    result = web.update_entries(as_entries(rig.entries(chat_ctx=4096)))

    assert result[CHAT] == "version-busy"
    status = {item["model"]: item for item in web.model_status()}
    assert status[CHAT]["reload_pending"] is True
    assert status[EMBED]["reload_pending"] is False


def test_update_while_stopped_writes_at_next_start(rig: RouterRig) -> None:
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    assert router.update_entries(as_entries(rig.entries(chat_ctx=4096))) == {
        EMBED: "saved",
        CHAT: "saved",
        CLEF: "saved",
    }
    assert rig.starts() == 0
    router.join()
    assert "ctx-size = 4096" in _sections()[CHAT]


def test_removed_entry_section_goes(rig: RouterRig) -> None:
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    router.join()
    result = router.update_entries(as_entries(rig.entries()[:2]))
    assert result[CLEF] == "removed"
    assert CLEF not in _sections()


def test_router_argument_change_restarts_with_no_other_client(rig: RouterRig) -> None:
    """Spec scenario "Model limit edit": a new ``--models-max`` restarts the router."""
    manager = rig.manager()
    old = open_router(manager, rig.spec(models_max=4), as_entries(rig.entries()))
    old.join()
    first = read_server_record(router_dir(state_root()))
    assert first is not None

    new = open_router(manager, rig.spec(models_max=2), as_entries(rig.entries()))
    new.join()

    second = read_server_record(router_dir(state_root()))
    assert second is not None and second.pid != first.pid
    assert not pid_alive(first.pid)
    assert rig.starts() == 2


def test_router_argument_change_while_in_use_is_version_busy(rig: RouterRig) -> None:
    cli = rig.worker(spec=rig.spec(models_max=4))
    assert cli.call("request", model=CHAT)["ok"]
    web = open_router(rig.manager(), rig.spec(models_max=2), as_entries(rig.entries()))
    with pytest.raises(RuntimeUnavailable) as caught:
        web.join()
    assert caught.value.reason == "version-busy"
    assert web.restart_pending() is True


def test_restart_pending_false_when_args_match(rig: RouterRig) -> None:
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    router.join()
    assert router.restart_pending() is False
