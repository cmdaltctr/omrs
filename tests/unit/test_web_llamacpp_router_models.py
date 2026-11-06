"""``PUT`` and ``DELETE /v1/llamacpp/router/models/{id}`` (tasks 7.1 and 7.2).

The list lives in ``omrs.jsonc`` as ``llamacpp_models``. A fake router
``llama-server`` stands in for the real one. No test downloads a model.
"""

from __future__ import annotations

import hashlib
import sys
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit import test_web_connections_edit as edit  # noqa: E402
from tests.unit import test_web_llamacpp_router_support as support  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

from omrs.config.llamacpp_models import CLASSIFY_MODEL, EMBED_MODEL  # noqa: E402
from omrs.transports.api import security  # noqa: E402

harness = support.harness
rig = support.rig

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

NEW_MODEL = "Qwen/Qwen3-1.7B-GGUF:Q8_0"


def sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ── Add, replace and edit ────────────────────────────────────────────────


def test_the_first_edit_writes_the_shipped_list_plus_the_edit(rig: Any) -> None:
    with rig() as r:
        assert "llamacpp_models" not in r.file_text()
        response = r.put_model("qwen3-4b", {"preset": {"ctx-size": 16384, "parallel": 2}})
        assert response.status_code == 200, response.text
        saved = r.jsonc()["llamacpp_models"]
        assert set(saved) == {"qwen3-embedding-4b", "qwen3-4b"}
        assert saved["qwen3-4b"]["preset"] == {"ctx-size": 16384, "parallel": 2}
        assert saved["qwen3-embedding-4b"]["preset"]["pooling"] == "last"  # shipped, kept whole
        assert r.entry("qwen3-4b")["ctx_size"] == 16384
        assert r.entry("qwen3-4b")["roles"] == ["classification"]


def test_use_this_model_adds_an_entry_with_its_hash_and_changes_no_role(rig: Any) -> None:
    with rig() as r:
        path = r.model_file("q17.gguf")
        response = r.put_model("qwen3-1-7b", {"model": NEW_MODEL, "file": path})
        assert response.status_code == 200, response.text
        saved = r.jsonc()
        entry = saved["llamacpp_models"]["qwen3-1-7b"]
        assert (entry["model"], entry["file"], entry["sha256"]) == (NEW_MODEL, path, sha(path))
        assert "answer" not in saved and "llamacpp_chat_model" not in saved
        listed = r.entry("qwen3-1-7b")
        assert (listed["roles"], listed["state"], listed["file"]) == ([], "unloaded", path)
        chat = r.client.get("/v1/settings/chat").json()
        assert chat["model"] == ""  # Use this model changes no role setting


def test_use_this_model_keeps_a_hash_the_download_status_gave(rig: Any) -> None:
    with rig() as r:
        path = r.model_file("q17.gguf")
        given = "ab" * 32
        body = {"model": NEW_MODEL, "file": path, "sha256": given}
        assert r.put_model("qwen3-1-7b", body).status_code == 200
        assert r.jsonc()["llamacpp_models"]["qwen3-1-7b"]["sha256"] == given


def test_replacing_the_file_of_an_entry_keeps_its_preset(rig: Any) -> None:
    with rig() as r:
        old = r.model_file("c.gguf")
        r.put_model("qwen3-4b", {"model": CLASSIFY_MODEL, "file": old})
        new = r.model_file("c2.gguf", b"GGUF other")
        body = {"model": "Qwen/Qwen3-4B-GGUF:Q4_K_M", "file": new}
        assert r.put_model("qwen3-4b", body).status_code == 200
        entry = r.jsonc()["llamacpp_models"]["qwen3-4b"]
        assert (entry["model"], entry["file"], entry["sha256"]) == (
            "Qwen/Qwen3-4B-GGUF:Q4_K_M",
            new,
            sha(new),
        )
        assert entry["preset"] == {"ctx-size": 32768, "parallel": 2}


def test_a_projector_and_its_hash_are_saved_and_cleared_with_null(rig: Any) -> None:
    with rig() as r:
        model, projector = r.model_file("m.gguf"), r.model_file("mmproj-m.gguf")
        body = {"model": NEW_MODEL, "file": model, "projector": projector}
        assert r.put_model("clef", body).status_code == 200
        entry = r.jsonc()["llamacpp_models"]["clef"]
        assert entry["projector"] == projector
        assert r.put_model("clef", {"projector": None}).status_code == 200
        assert "projector" not in r.jsonc()["llamacpp_models"]["clef"]


# ── Scopes ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("key", ["model", "file", "projector", "sha256", "projector_sha256"])
def test_changing_a_model_file_or_hash_needs_credentials(
    rig: Any, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    with rig() as r:
        values = {
            "model": NEW_MODEL,
            "file": r.model_file("c.gguf"),
            "projector": r.model_file("mmproj-c.gguf"),
            "sha256": "cd" * 32,
            "projector_sha256": "ef" * 32,
        }
        monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"credentials"})
        response = r.put_model("qwen3-4b", {key: values[key]})
        assert response.status_code == 403
        assert r.file_text() == ""


def test_a_preset_edit_needs_manage_only(rig: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    with rig() as r:
        monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"credentials"})
        response = r.put_model("qwen3-4b", {"preset": {"ctx-size": 4096}})
        assert response.status_code == 200, response.text
        monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"manage"})
        assert r.put_model("qwen3-4b", {"preset": {"ctx-size": 2048}}).status_code == 403


def test_removing_an_entry_needs_credentials(rig: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    with rig() as r:
        r.put_model("spare", {"model": NEW_MODEL, "file": r.model_file("s.gguf")})
        monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"credentials"})
        assert r.delete_model("spare").status_code == 403
        assert "spare" in r.jsonc()["llamacpp_models"]


# ── Rules ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {"file": "models/q.gguf"},  # relative
        {"file": "/no/such/dir/q.gguf"},  # missing, router is managed
        {"model": "Qwen/Qwen3-4B-GGUF"},  # no quantisation tag
        {"model": "--flag"},
        {"model": None},
        {"preset": {"ctx-size": 100}},  # below 512
        {"preset": {"embeddings": False}},
        {"preset": {"cache-prompt": 1}},
        {"preset": {"cache-prompt": "maybe"}},
        {"preset": {"pooling": "last --api-key x"}},
        {"preset": {"batch-size": 64, "ubatch-size": 128}},
        {"preset": "not an object"},
        {"sha256": "xyz"},
        {"ctx_size": 4096},  # not a field of the entry
    ],
)
def test_a_rule_failure_is_400_and_saves_nothing(rig: Any, body: dict[str, Any]) -> None:
    with rig() as r:
        response = r.put_model("qwen3-4b", body)
        assert response.status_code == 400, response.text
        assert r.file_text() == ""


def test_a_file_that_is_not_gguf_or_names_a_projector_is_400(rig: Any, tmp_path: Any) -> None:
    with rig() as r:
        text = tmp_path / "models" / "weights.bin"
        text.parent.mkdir(exist_ok=True)
        text.write_bytes(b"x")
        assert r.put_model("qwen3-4b", {"file": str(text)}).status_code == 400
        assert r.put_model("qwen3-4b", {"file": r.model_file("mmproj-x.gguf")}).status_code == 400
        assert r.file_text() == ""


@pytest.mark.parametrize(
    "key",
    ["sleep-idle-seconds", "api-key", "host", "port", "connect", "connect-code", "models-max"],
)
def test_a_reserved_preset_key_is_400_preset_key_unknown(rig: Any, key: str) -> None:
    with rig() as r:
        response = r.put_model("qwen3-4b", {"preset": {"ctx-size": 4096, key: "x"}})
        assert response.status_code == 400
        assert response.json()["reason"] == "preset-key-unknown"
        assert r.file_text() == ""
        assert r.preset_text() == ""


def test_every_allowed_preset_key_is_accepted(rig: Any) -> None:
    preset = {
        "ctx-size": 8192,
        "batch-size": 4096,
        "ubatch-size": 2048,
        "parallel": 2,
        "kv-unified": False,
        "flash-attn": "on",
        "n-gpu-layers": "all",
        "fit": "off",
        "cache-type-k": "q8_0",
        "cache-type-v": "f16",
        "cache-prompt": True,
        "cache-reuse": 256,
        "image-min-tokens": 4,
        "image-max-tokens": 1024,
    }
    with rig() as r:
        assert r.put_model("qwen3-4b", {"preset": preset}).status_code == 200
        assert r.jsonc()["llamacpp_models"]["qwen3-4b"]["preset"] == preset


def test_an_id_outside_the_pattern_is_400(rig: Any) -> None:
    with rig() as r:
        for bad in ("Bad_ID", "x" * 41):
            assert r.put_model(bad, {"model": NEW_MODEL}).status_code == 400, bad
        assert r.file_text() == ""


def test_two_entries_cannot_list_the_same_model(rig: Any) -> None:
    with rig() as r:
        response = r.put_model("twin", {"model": CLASSIFY_MODEL})
        assert response.status_code == 400
        assert "already lists" in response.json()["message"]
        assert r.file_text() == ""


def test_a_new_entry_needs_a_model(rig: Any) -> None:
    with rig() as r:
        assert r.put_model("fresh", {"preset": {"ctx-size": 4096}}).status_code == 400
        assert r.file_text() == ""


def test_an_embedding_entry_without_pooling_is_400_preset_invalid(rig: Any) -> None:
    with rig() as r:
        preset = {
            k: v for k, v in r.entry("qwen3-embedding-4b")["preset"].items() if k != "pooling"
        }
        response = r.put_model("qwen3-embedding-4b", {"preset": preset})
        assert response.status_code == 400
        assert response.json()["reason"] == "preset-invalid"
        assert r.file_text() == ""


def test_a_chat_entry_cannot_become_an_embedding_entry(rig: Any) -> None:
    with rig() as r:
        preset = {**r.entry("qwen3-4b")["preset"], "embeddings": True}
        response = r.put_model("qwen3-4b", {"preset": preset})
        assert response.status_code == 400
        assert response.json()["reason"] == "role-mismatch"
        assert r.file_text() == ""


def test_an_unknown_body_key_is_400(rig: Any) -> None:
    with rig() as r:
        assert r.put_model("qwen3-4b", {"args": ["--x"]}).status_code == 400


def test_an_external_router_takes_a_name_with_no_file(rig: Any) -> None:
    with rig(llamacpp_router_server="external") as r:
        assert r.put_model("remote", {"model": NEW_MODEL}).status_code == 200
        assert r.jsonc()["llamacpp_models"]["remote"] == {"model": NEW_MODEL}


def test_a_stale_revision_is_409(rig: Any) -> None:
    with rig() as r:
        body = {"preset": {"ctx-size": 4096}, "revision": "0" * 64}
        response = r.put_model("qwen3-4b", body)
        assert response.status_code == 409
        assert r.file_text() == ""


def test_the_model_list_is_not_saved_through_the_configuration_page(rig: Any) -> None:
    with rig() as r:
        entry = {"x": {"model": NEW_MODEL}}
        response = r.client.put(
            "/v1/settings/configuration",
            json={"revision": r.get()["revision"], "changes": {"llamacpp_models": entry}},
            headers=edit.ORIGIN,
        )
        assert response.status_code == 400
        assert r.file_text() == ""


# ── DELETE ───────────────────────────────────────────────────────────────


def test_an_entry_without_a_role_can_be_removed(rig: Any) -> None:
    with rig() as r:
        r.put_model("spare", {"model": NEW_MODEL, "file": r.model_file("s.gguf")})
        response = r.delete_model("spare")
        assert response.status_code == 200, response.text
        assert set(r.jsonc()["llamacpp_models"]) == {"qwen3-embedding-4b", "qwen3-4b"}
        assert [m["id"] for m in response.json()["models"]] == ["qwen3-embedding-4b", "qwen3-4b"]


@pytest.mark.parametrize("entry_id", ["qwen3-embedding-4b", "qwen3-4b"])
def test_an_entry_that_holds_a_role_cannot_be_removed(rig: Any, entry_id: str) -> None:
    with rig() as r:
        response = r.delete_model(entry_id)
        assert response.status_code == 409
        assert response.json()["reason"] == "in-use"
        assert r.file_text() == ""


def test_an_unknown_entry_is_404(rig: Any) -> None:
    with rig() as r:
        assert r.delete_model("nothing").status_code == 404
        assert r.file_text() == ""


def test_a_stale_revision_on_a_delete_is_409(rig: Any) -> None:
    with rig() as r:
        r.put_model("spare", {"model": NEW_MODEL, "file": r.model_file("s.gguf")})
        assert r.delete_model("spare", revision="0" * 64).status_code == 409
        assert "spare" in r.jsonc()["llamacpp_models"]


def test_removing_the_first_entry_of_the_shipped_list_writes_the_rest(rig: Any) -> None:
    with rig(llamacpp_chat_model="", llamacpp_embed_model=EMBED_MODEL) as r:
        response = r.delete_model("qwen3-4b")
        assert response.status_code == 200, response.text
        assert set(r.jsonc()["llamacpp_models"]) == {"qwen3-embedding-4b"}


# ── A saved change reaches the running router (design D7) ────────────────


def test_a_preset_edit_rewrites_one_section_and_keeps_the_router_running(rig: Any) -> None:
    with rig() as r:
        r.save_files()
        r.post("start")
        r.wait_state("running")
        first = r.pids()
        assert "ctx-size = 32768" in r.preset_text()
        response = r.put_model("qwen3-4b", {"preset": {"ctx-size": 4096, "parallel": 2}})
        assert response.status_code == 200, response.text
        assert "ctx-size = 4096" in r.preset_text()
        assert "ctx-size = 8192" in r.preset_text()  # the embedding section is untouched
        assert r.pids() == first  # the router was not restarted
        assert r.get()["state"] == "running"


def test_an_added_entry_reaches_the_running_router(rig: Any) -> None:
    with rig() as r:
        r.save_files()
        r.post("start")
        r.wait_state("running")
        path = r.model_file("q17.gguf")
        assert r.put_model("qwen3-1-7b", {"model": NEW_MODEL, "file": path}).status_code == 200
        assert f"[{NEW_MODEL}]" in r.preset_text()
        assert len(r.pids()) == 1


def test_a_save_while_a_restart_is_pending_leaves_the_router_alone(rig: Any) -> None:
    with rig() as r:
        r.save_files()
        r.post("start")
        r.wait_state("running")
        first = r.pids()
        r.put({"models_max": 2})  # saved arguments now differ from the running ones
        assert r.put_model("qwen3-4b", {"preset": {"ctx-size": 4096}}).status_code == 200
        assert r.pids() == first
        assert r.get()["state"] == "running"
        entry = r.entry("qwen3-4b")
        assert entry["ctx_size"] == 4096
        assert entry["reload_pending"] is True  # the running router still holds the old value


def test_a_changed_entry_shows_reload_pending_until_the_reload_runs(rig: Any) -> None:
    with rig() as r:
        r.save_files()
        r.post("start")
        r.wait_state("running")
        assert r.entry("qwen3-4b")["reload_pending"] is False
        r.put_model("qwen3-4b", {"preset": {"ctx-size": 4096, "parallel": 2}})
        assert r.entry("qwen3-4b")["reload_pending"] is False  # the reload ran at the save


# ── Contract ─────────────────────────────────────────────────────────────


def test_the_responses_conform_to_the_contract(rig: Any) -> None:
    check = ContractChecker()
    with rig() as r:
        path = r.model_file("q17.gguf")
        check.check(r.put_model("qwen3-4b", {"preset": {"ctx-size": 100}}), 400)
        check.check(r.put_model("qwen3-4b", {"preset": {"api-key": "x"}}), 400)
        check.check(r.put_model("qwen3-4b", {"preset": {"ctx-size": 4096}}), 200)
        check.check(r.put_model("qwen3-1-7b", {"model": NEW_MODEL, "file": path}), 200)
        check.check(r.delete_model("qwen3-4b"), 409)
        check.check(r.delete_model("qwen3-1-7b"), 200)
        check.check(r.delete_model("nothing"), 404)
        check.check(r.put_model("qwen3-4b", {"preset": {"ctx-size": 4096}, "revision": "x"}), 409)
        assert {"saveLlamacppRouterModel", "deleteLlamacppRouterModel"} <= check.operations
