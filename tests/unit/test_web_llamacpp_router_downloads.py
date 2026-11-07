"""``GET /v1/llamacpp/router/downloads-needed`` (one-llamacpp-router, decision B).

Before a first Start, the Router panel asks which listed models have no file and how big
they are, so one dialog can say "Download 2 models, 8.6 GB?". The route reads the model
host only when it is called, never at a status read. Hugging Face is faked at
``huggingface_models``; a fake router ``llama-server`` stands in; no network is used.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit import test_web_connections_edit as edit  # noqa: E402
from tests.unit import test_web_llamacpp_router_support as support  # noqa: E402
from tests.unit.test_web_llamacpp_router_support import URL  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

from omrs.config.llamacpp_models import CLASSIFY_MODEL, EMBED_MODEL  # noqa: E402
from omrs.integrations import huggingface_models as hf  # noqa: E402

harness = support.harness
rig = support.rig

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

NEEDED = f"{URL}/downloads-needed"
REV = "d" * 40
EMBED_BYTES = 4_300_000_000
CHAT_BYTES = 4_400_000_000
FILES = {
    "Qwen/Qwen3-Embedding-4B-GGUF": (
        ("Qwen3-Embedding-4B-Q4_K_M.gguf", 2_500_000_000),
        ("Qwen3-Embedding-4B-Q8_0.gguf", EMBED_BYTES),
    ),
    "Qwen/Qwen3-4B-GGUF": (
        ("Qwen3-4B-Q4_K_M.gguf", 2_600_000_000),
        ("Qwen3-4B-Q8_0-00001-of-00002.gguf", 3_000_000_000),
        ("Qwen3-4B-Q8_0-00002-of-00002.gguf", 1_400_000_000),
    ),
}


class FakeHub:
    """Hugging Face file listings; every call is recorded."""

    def __init__(self) -> None:
        self.listed: list[str] = []
        self.refuse = False

    def list_repo_files(self, repo: str, *, revision: str | None = None, client: Any = None) -> Any:
        self.listed.append(repo)
        if self.refuse:
            raise hf.ModelHostError("network")
        return hf.RepoFiles(repo, REV, False, FILES[repo])


@pytest.fixture
def hub(monkeypatch: pytest.MonkeyPatch) -> FakeHub:
    fake = FakeHub()
    monkeypatch.setattr(hf, "list_repo_files", fake.list_repo_files)
    return fake


def _needed(r: Any) -> Any:
    return r.client.get(NEEDED)


def test_the_two_shipped_models_are_named_with_their_sizes_and_the_total(
    rig: Any, hub: FakeHub
) -> None:
    with rig() as r:
        body = _needed(r).json()

        assert body["models"] == [
            {"id": "qwen3-embedding-4b", "model": EMBED_MODEL, "size_bytes": EMBED_BYTES},
            {"id": "qwen3-4b", "model": CLASSIFY_MODEL, "size_bytes": CHAT_BYTES},
        ]
        assert body["total_bytes"] == EMBED_BYTES + CHAT_BYTES
        assert sorted(hub.listed) == sorted(FILES)


def test_a_model_with_a_file_is_not_listed(rig: Any, hub: FakeHub) -> None:
    with rig() as r:
        body = {"model": CLASSIFY_MODEL, "file": r.model_file("c.gguf")}
        assert r.put_model("qwen3-4b", body).status_code == 200

        needed = _needed(r).json()

        assert [m["id"] for m in needed["models"]] == ["qwen3-embedding-4b"]
        assert needed["total_bytes"] == EMBED_BYTES
        assert hub.listed == ["Qwen/Qwen3-Embedding-4B-GGUF"]


def test_with_every_file_present_nothing_is_listed_and_the_host_is_not_read(
    rig: Any, hub: FakeHub
) -> None:
    with rig() as r:
        r.save_files()

        needed = _needed(r).json()

        assert (needed["models"], needed["total_bytes"]) == ([], 0)
        assert hub.listed == []


def test_an_unreachable_host_gives_the_names_and_no_size(rig: Any, hub: FakeHub) -> None:
    hub.refuse = True
    with rig() as r:
        response = _needed(r)

        assert response.status_code == 200
        body = response.json()
        assert [m["id"] for m in body["models"]] == ["qwen3-embedding-4b", "qwen3-4b"]
        assert [m["size_bytes"] for m in body["models"]] == [None, None]
        assert body["total_bytes"] is None


def test_one_unknown_size_makes_the_total_unknown(rig: Any, hub: FakeHub) -> None:
    with rig() as r:
        body = {"model": "Qwen/Qwen3-4B-GGUF:Q2_K", "file": None}
        assert r.put_model("qwen3-4b", body).status_code == 200  # a label the repo lacks

        needed = _needed(r).json()

        sizes = {m["id"]: m["size_bytes"] for m in needed["models"]}
        assert sizes == {"qwen3-embedding-4b": EMBED_BYTES, "qwen3-4b": None}
        assert needed["total_bytes"] is None


def test_a_status_read_never_contacts_the_model_host(rig: Any, hub: FakeHub) -> None:
    with rig() as r:
        r.get()
        r.get()

        assert hub.listed == []


def test_the_route_starts_nothing_and_writes_nothing(rig: Any, hub: FakeHub) -> None:
    with rig() as r:
        before = r.file_text()

        _needed(r)

        assert r.file_text() == before
        assert r.pids() == []
        assert r.preset_text() == ""


def test_an_external_router_gives_409_and_reads_nothing(rig: Any, hub: FakeHub) -> None:
    with rig(llamacpp_router_server="external") as r:
        response = _needed(r)

        assert response.status_code == 409
        assert response.json()["reason"] == "external-server"
        assert hub.listed == []


def test_it_needs_a_browser_session_with_manage(
    rig: Any, hub: FakeHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs.transports.api import security

    with rig() as r:
        scopes = security.SESSION_SCOPES
        monkeypatch.setattr(security, "SESSION_SCOPES", scopes - {"manage"})
        assert _needed(r).status_code == 403
        monkeypatch.setattr(security, "SESSION_SCOPES", scopes)
        r.client.cookies.clear()
        header = edit.bearer(r.h.policy, "read", "graph", "run")
        assert r.client.get(NEEDED, headers=header).status_code == 403
        assert r.client.get(NEEDED).status_code == 401
        assert hub.listed == []


def test_the_response_conforms_to_the_contract(rig: Any, hub: FakeHub) -> None:
    check = ContractChecker()
    with rig() as r:
        check.check(_needed(r), 200)
        hub.refuse = True
        check.check(_needed(r), 200)
        r.save_files()
        check.check(_needed(r), 200)
    with rig(llamacpp_router_server="external") as r:
        check.check(_needed(r), 409)
    assert "getLlamacppRouterDownloads" in check.operations
    assert "getLlamacppRouterDownloads" in FAMILIES["llamacpp_router"]


@pytest.mark.parametrize("name", ["no-colon", "../x/y:Q8_0", "org/name:", "a b/c:Q8_0", "/n:Q8_0"])
def test_a_name_that_breaks_the_naming_rules_is_never_sent_to_the_host(
    hub: FakeHub, name: str
) -> None:
    from omrs.transports.api.routes.llamacpp_router_downloads import model_size

    assert model_size(name) is None
    assert hub.listed == []
