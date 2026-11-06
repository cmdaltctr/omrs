"""Router start, adoption, stop, memory and child environment (tasks 3.5 and 3.6).

The fake router (``tests/fixtures/llamacpp``) runs one real child process per
loaded model in the router's process group. No real ``llama-server`` starts.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.fixtures.llamacpp.harness import pid_alive, wait_until
from tests.unit.test_llamacpp_router_worker import (
    CHAT,
    CLEF,
    EMBED,
    RouterRig,
    as_entries,
    rig_fixture,
)

from omrs.integrations.llamacpp_runtime import children, process
from omrs.integrations.llamacpp_runtime.preset_writer import (
    read_preset,
    section_digest,
    split_sections,
)
from omrs.integrations.llamacpp_runtime.router_lease import open_router
from omrs.integrations.llamacpp_runtime.router_spec import (
    EMPTY_CACHE_DIR,
    EMPTY_CONFIG_DIR,
    router_dir,
    router_environment,
)
from omrs.integrations.llamacpp_runtime.state import read_server_record, state_root

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from rig_fixture(tmp_path, monkeypatch)


def _children(pid: int) -> list[int]:
    return children.direct_children(pid)


def _load(url: str, model: str) -> None:
    assert httpx.post(f"{url}/models/load", json={"model": model}, timeout=10).status_code == 200

    def loaded() -> bool:
        items = httpx.get(f"{url}/v1/models", timeout=10).json()["data"]
        return any(i["id"] == model and i["status"]["value"] == "loaded" for i in items)

    assert wait_until(loaded, 15)


def test_start_writes_the_state_folder_layout(rig: RouterRig) -> None:
    """D8 layout: models.ini, hashes.json, server.json, both empty folders."""
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    router.join()
    folder = router_dir(state_root())
    names = {p.name for p in folder.iterdir()}
    assert {"start.lock", "clients.lock", "server.json", "server.log", "models.ini"} <= names
    assert (folder / EMPTY_CACHE_DIR).is_dir() and not any((folder / EMPTY_CACHE_DIR).iterdir())
    assert (folder / EMPTY_CONFIG_DIR).is_dir() and not any((folder / EMPTY_CONFIG_DIR).iterdir())
    assert list(split_sections(read_preset(folder))) == [EMBED, CHAT, CLEF]


def test_server_json_records_the_model_digests(rig: RouterRig) -> None:
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    router.join()
    folder = router_dir(state_root())
    record = read_server_record(folder)
    assert record is not None
    sections = split_sections(read_preset(folder))
    assert record.models == {name: section_digest(text) for name, text in sections.items()}
    stored = json.loads((folder / "server.json").read_text(encoding="utf-8"))
    assert stored["models"] == record.models


def test_router_digest_ignores_the_preset(rig: RouterRig) -> None:
    """D8: the router digest is the binary and the argument list only."""
    one = open_router(rig.manager(), rig.spec(), as_entries(rig.entries(chat_ctx=8192)))
    two = open_router(rig.manager(), rig.spec(), as_entries(rig.entries(chat_ctx=4096)))
    assert one.spec.digest == two.spec.digest


def test_orphan_router_is_adopted(rig: RouterRig) -> None:
    """Spec scenario "Client killed, server adopted": no second router starts."""
    first = rig.worker()
    assert first.call("request", model=CHAT)["ok"] is True
    first.send("abandon")
    first.proc.wait(timeout=15)
    record = read_server_record(router_dir(state_root()))
    assert record is not None and pid_alive(record.pid)

    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    with router.model_session(CHAT) as url:
        assert httpx.post(f"{url}/v1/chat/completions", json={"model": CHAT}).status_code == 200
    assert rig.starts() == 1


def test_preset_edit_is_not_a_new_router_version(rig: RouterRig) -> None:
    """Spec scenario "Preset edit is not a new router version"."""
    holder = rig.worker()
    assert holder.call("request", model=EMBED, path="/v1/embeddings")["ok"] is True
    record = read_server_record(router_dir(state_root()))
    assert record is not None
    embed_child = _children(record.pid)

    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries(chat_ctx=4096)))
    with router.model_session(CHAT) as url:
        assert httpx.post(f"{url}/v1/chat/completions", json={"model": CHAT}).status_code == 200

    assert rig.starts() == 1
    after = read_server_record(router_dir(state_root()))
    assert after is not None and after.pid == record.pid
    assert "ctx-size = 4096" in split_sections(read_preset(router_dir(state_root())))[CHAT]
    assert set(embed_child) <= set(_children(record.pid))  # the embedding child kept its pid


def test_group_stop_reaches_every_child(rig: RouterRig) -> None:
    """Spec scenario "No child survives"."""
    manager = rig.manager()
    router = open_router(manager, rig.spec(), as_entries(rig.entries()))
    url = router.join()
    _load(url, EMBED)
    _load(url, CHAT)
    record = read_server_record(router_dir(state_root()))
    assert record is not None
    kids = _children(record.pid)
    assert len(kids) == 2

    assert manager.stop("router") is True

    assert wait_until(lambda: not any(pid_alive(p) for p in [record.pid, *kids]), 15)


def test_direct_children_lists_the_loaded_models(rig: RouterRig) -> None:
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    url = router.join()
    record = read_server_record(router_dir(state_root()))
    assert record is not None
    assert _children(record.pid) == []
    _load(url, CHAT)
    assert len(_children(record.pid)) == 1


def test_memory_sums_router_and_children(rig: RouterRig, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec scenario "Memory sums children": router RSS plus two children."""
    manager = rig.manager()
    spec = rig.spec()
    router = open_router(manager, spec, as_entries(rig.entries()))
    url = router.join()
    _load(url, EMBED)
    _load(url, CHAT)
    record = read_server_record(router_dir(state_root()))
    assert record is not None
    sizes = {record.pid: 1_000_000, **{kid: 10_000 for kid in _children(record.pid)}}
    monkeypatch.setattr(process, "rss_bytes", lambda pid: sizes.get(pid))

    item = manager.status([spec])[0]

    assert item["memory_bytes"] == 1_020_000


def test_memory_skips_a_child_without_the_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(children, "direct_children", lambda pid: [11, 12])
    monkeypatch.setattr(process, "owns", lambda pid, binary: pid in (10, 11))
    monkeypatch.setattr(process, "rss_bytes", lambda pid: {10: 100, 11: 5, 12: 7}[pid])
    assert children.tree_rss(10, "/b/llama-server") == 105


def test_router_child_environment(tmp_path: Path) -> None:
    """Spec scenarios "Minimal environment", "Cache variables" and "No user config file"."""
    environ = {
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "LANG": "C",
        "TMPDIR": "/tmp",
        "OPENROUTER_API_KEY": "k1",
        "ANTHROPIC_API_KEY": "k2",
        "OPENAI_COMPATIBLE_API_KEY": "k3",
        "HF_TOKEN": "t",
        "HF_HOME": "/hf",
        "HF_HUB_CACHE": "/hub",
        "LLAMA_CACHE": "/data/cache",
        "XDG_CONFIG_HOME": "/home/u/.config",
    }
    folder = tmp_path / "runtimes" / "router"
    (folder / EMPTY_CONFIG_DIR / "llama.cpp").mkdir(parents=True)
    (folder / EMPTY_CONFIG_DIR / "llama.cpp" / "config.ini").write_text("x", encoding="utf-8")

    env = router_environment(environ, folder)

    assert env == {
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "LANG": "C",
        "TMPDIR": "/tmp",
        "LLAMA_CACHE": str(folder / EMPTY_CACHE_DIR),
        "XDG_CONFIG_HOME": str(folder / EMPTY_CONFIG_DIR),
    }
    assert list((folder / EMPTY_CONFIG_DIR).iterdir()) == []
    assert list((folder / EMPTY_CACHE_DIR).iterdir()) == []


def test_start_passes_the_router_environment(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, str]] = []
    real = process.launch

    def spy(argv: Any, env: Any, log_path: Path) -> Any:
        seen.append(dict(env))
        return real(argv, env, log_path)

    monkeypatch.setattr(process, "launch", spy)
    manager = rig.manager()
    path = os.environ["PATH"]
    manager._environ = {"PATH": path, "HF_TOKEN": "t", "OPENROUTER_API_KEY": "k"}
    open_router(manager, rig.spec(), as_entries(rig.entries())).join()
    folder = router_dir(state_root())
    assert seen == [
        {
            "PATH": path,
            "LLAMA_CACHE": str(folder / EMPTY_CACHE_DIR),
            "XDG_CONFIG_HOME": str(folder / EMPTY_CONFIG_DIR),
        }
    ]


def test_old_build_refused(rig: RouterRig) -> None:
    """Spec scenario "Old user build": ``wrong-build`` and no process starts."""
    from omrs.integrations.llamacpp_runtime.lease import RuntimeUnavailable

    rig.set_env(FAKE_LLAMA_BUILD="11510")
    with pytest.raises(RuntimeUnavailable) as caught:
        open_router(rig.manager(), rig.spec(), as_entries(rig.entries())).join()
    assert caught.value.reason == "wrong-build"
    assert rig.starts() == 0


def test_no_usable_entry_is_not_configured(rig: RouterRig) -> None:
    """Spec "Start moves to running or failed": a list with no usable entry."""
    from omrs.integrations.llamacpp_runtime.lease import RuntimeUnavailable

    entries = rig.entries()
    for item in entries:
        item["file"] = None
    with pytest.raises(RuntimeUnavailable) as caught:
        open_router(rig.manager(), rig.spec(), as_entries(entries)).join()
    assert caught.value.reason == "not-configured"
    assert rig.starts() == 0
