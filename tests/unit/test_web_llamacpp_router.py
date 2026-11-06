"""``/v1/llamacpp/router`` settings, scopes and lifecycle (task 7.1).

A fake router ``llama-server`` stands in for the real one (``tests/fixtures/llamacpp``).
The keychain is a fake in memory and no real provider is contacted. The entry
routes have their own file, ``test_web_llamacpp_router_models.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.fixtures.llamacpp.harness import wait_until  # noqa: E402
from tests.unit import test_web_connections_edit as edit  # noqa: E402
from tests.unit import test_web_llamacpp_router_support as support  # noqa: E402
from tests.unit.test_web_llamacpp_router_support import ORIGIN, URL, alive  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

from omrs.config.llamacpp_models import CLASSIFY_MODEL, EMBED_MODEL  # noqa: E402
from omrs.transports.api import security  # noqa: E402

harness = support.harness
rig = support.rig

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

ROUTES_SOURCE = Path(__file__).parents[2] / "src/omrs/transports/api/routes"


# ── GET shape and defaults ───────────────────────────────────────────────


def test_the_default_status(rig: Any) -> None:
    with rig() as r:
        body = r.get()
        assert (body["state"], body["reason"], body["mode"]) == ("stopped", None, "managed")
        assert (body["running_with"], body["pending_restart"]) == (None, False)
        assert body["revision"] == "absent"
        saved = body["saved"]
        assert set(saved) == {
            "binary",
            "router_server",
            "router_url",
            "models_max",
            "memory_margin_mib",
        }
        assert (saved["models_max"]["value"], saved["models_max"]["source"]) == (4, "default")
        assert (saved["models_max"]["min"], saved["models_max"]["max"]) == (1, 16)
        assert saved["models_max"]["default"] == 4
        margin = saved["memory_margin_mib"]
        assert (margin["value"], margin["default"], margin["min"], margin["max"]) == (
            8192,
            8192,
            0,
            262144,
        )
        assert saved["router_server"]["value"] == "managed"
        assert all(entry["locked"] is False for entry in saved.values())


def test_the_default_list_is_the_shipped_list_with_its_roles(rig: Any) -> None:
    with rig() as r:
        models = {m["id"]: m for m in r.get()["models"]}
        assert set(models) == {"qwen3-embedding-4b", "qwen3-4b"}
        embed, text = models["qwen3-embedding-4b"], models["qwen3-4b"]
        assert (embed["model"], embed["roles"], embed["state"]) == (
            EMBED_MODEL,
            ["embeddings"],
            "not-downloaded",
        )
        assert (text["model"], text["roles"], text["state"]) == (
            CLASSIFY_MODEL,
            ["classification"],
            "not-downloaded",
        )
        assert (embed["file"], embed["ctx_size"], text["ctx_size"]) == (None, 8192, 32768)
        assert text["reload_pending"] is False
        assert text["preset"] == {"ctx-size": 32768, "parallel": 2}


def test_get_needs_read_and_a_read_bearer_can_see_it(rig: Any) -> None:
    with rig() as r:
        r.client.cookies.clear()
        assert r.client.get(URL).status_code == 401
        header = edit.bearer(r.h.policy, "read")
        assert r.client.get(URL, headers=header).status_code == 200


def test_the_old_server_routes_are_gone(rig: Any) -> None:
    with rig() as r:
        assert r.client.get("/v1/llamacpp/server").status_code == 404
        assert r.client.put("/v1/llamacpp/server", json={}, headers=ORIGIN).status_code == 404
        assert r.client.post("/v1/llamacpp/server/start", headers=ORIGIN).status_code == 404


# ── PUT ──────────────────────────────────────────────────────────────────


def test_save_the_settings_then_read_them_with_source_config_file(rig: Any) -> None:
    with rig() as r:
        response = r.put({"models_max": 2, "memory_margin_mib": 4096})
        assert response.status_code == 200, response.text
        text = r.file_text()
        assert '"llamacpp_router_models_max": 2' in text
        assert '"llamacpp_router_memory_margin_mib": 4096' in text
        saved = r.get()["saved"]
        assert (saved["models_max"]["value"], saved["models_max"]["source"]) == (2, "config-file")
        assert saved["memory_margin_mib"]["value"] == 4096
        assert saved["models_max"]["locked"] is False


def test_the_program_and_the_address_are_saved(rig: Any) -> None:
    with rig() as r:
        body = {"binary": str(r.binary), "router_url": "http://127.0.0.1:9931/v1"}
        assert r.put(body).status_code == 200
        saved = r.get()["saved"]
        assert saved["binary"]["value"] == str(r.binary)
        assert saved["router_url"]["value"] == "http://127.0.0.1:9931/v1"
        assert saved["router_url"]["source"] == "config-file"


def test_the_router_mode_is_saved(rig: Any) -> None:
    with rig() as r:
        assert r.put({"router_server": "external"}).status_code == 200
        saved = r.get()["saved"]["router_server"]
        assert (saved["value"], saved["source"]) == ("external", "config-file")
        assert r.get()["mode"] == "external"


def test_the_engine_takes_a_router_mode_change(rig: Any) -> None:
    with rig() as r:
        assert r.put({"router_server": "external"}).status_code == 200


def test_a_null_clears_a_saved_value(rig: Any) -> None:
    with rig() as r:
        assert r.put({"models_max": 2}).status_code == 200
        assert r.put({"models_max": None}).status_code == 200
        entry = r.get()["saved"]["models_max"]
        assert (entry["value"], entry["source"]) == (4, "default")
        assert "llamacpp_router_models_max" not in r.file_text()


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("models_max", 0),
        ("models_max", 17),
        ("models_max", "abc"),
        ("models_max", 3.5),
        ("models_max", True),
        ("memory_margin_mib", -1),
        ("memory_margin_mib", 262145),
        ("memory_margin_mib", "lots"),
    ],
)
def test_a_value_out_of_range_is_400_and_saves_nothing(rig: Any, key: str, bad: Any) -> None:
    with rig() as r:
        response = r.put({key: bad})
        assert response.status_code == 400
        assert "whole number from" in response.json()["message"]
        assert r.file_text() == ""


def test_an_unknown_mode_is_400_and_names_the_accepted_words(rig: Any) -> None:
    with rig() as r:
        response = r.put({"router_server": "auto"})
        assert response.status_code == 400
        message = response.json()["message"]
        assert "external" in message and "managed" in message and "auto" not in message
        assert r.file_text() == ""


def test_a_managed_router_needs_a_loopback_address(rig: Any) -> None:
    with rig() as r:
        response = r.put({"router_url": "http://192.168.1.20:8080/v1"})
        assert response.status_code == 400
        assert "192.168" not in response.text
        assert r.file_text() == ""
        both = {"router_server": "external", "router_url": "http://192.168.1.20:8080/v1"}
        assert r.put(both).status_code == 200  # an external router may be anywhere


@pytest.mark.parametrize(
    "bad", ["relative/llama-server", "/bin/sh", "/no/such/zz-marker/llama-server", ""]
)
def test_a_bad_program_is_400_and_saves_nothing(rig: Any, bad: str) -> None:
    with rig() as r:
        response = r.put({"binary": bad})
        assert response.status_code == 400
        message = response.json()["message"]
        assert "llama-server" in message
        assert bad == "" or bad not in message
        assert "llamacpp_server_binary" not in r.file_text()


@pytest.mark.parametrize("extra", ["args", "extra_args", "port", "host", "env"])
def test_no_other_field_is_accepted(rig: Any, extra: str) -> None:
    with rig() as r:
        response = r.put({"models_max": 2, extra: ["--api-key", "x"]})
        assert response.status_code == 400
        assert r.file_text() == ""


def test_an_empty_body_is_400(rig: Any) -> None:
    with rig() as r:
        assert r.put({}).status_code == 400


def test_a_model_key_is_400_and_says_models_are_set_in_the_table(rig: Any) -> None:
    with rig() as r:
        response = r.put({"models_max": 2, "model": "org/name:Q8_0"})
        assert response.status_code == 400
        assert "model table" in response.json()["message"]
        assert r.file_text() == ""


@pytest.mark.parametrize("bad", [0, 120, "soon", None])
def test_an_idle_sleep_key_is_400_and_names_the_fixed_idle_stop(rig: Any, bad: object) -> None:
    with rig() as r:
        response = r.put({"models_max": 2, "idle_sleep": bad})
        assert response.status_code == 400
        assert "10 minutes" in response.json()["message"]
        assert r.file_text() == ""


def test_an_idle_sleep_key_without_a_session_is_401_not_400(rig: Any) -> None:
    with rig() as r:
        r.client.cookies.clear()
        assert r.client.put(URL, json={"idle_sleep": 1}, headers=ORIGIN).status_code == 401


# ── Locks and revisions ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("field", "variable", "body"),
    [
        ("llamacpp_server_binary", "LLAMACPP_SERVER_BINARY", {"binary": "{binary}"}),
        ("llamacpp_router_server", "LLAMACPP_ROUTER_SERVER", {"router_server": "external"}),
        ("llamacpp_router_url", "LLAMACPP_ROUTER_URL", {"router_url": "http://127.0.0.1:9/v1"}),
        ("llamacpp_router_models_max", "LLAMACPP_ROUTER_MODELS_MAX", {"models_max": 2}),
        (
            "llamacpp_router_memory_margin_mib",
            "LLAMACPP_ROUTER_MEMORY_MARGIN_MIB",
            {"memory_margin_mib": 1},
        ),
    ],
)
def test_an_environment_value_locks_the_field_and_names_the_variable(
    rig: Any, field: str, variable: str, body: dict[str, Any]
) -> None:
    with rig(explicit=frozenset({field})) as r:
        sent = {k: v.format(binary=r.binary) if isinstance(v, str) else v for k, v in body.items()}
        response = r.put(sent)
        assert response.status_code == 409
        assert variable in response.json()["message"]
        key = next(iter(body))
        entry = r.get()["saved"][key]
        assert (entry["locked"], entry["source"]) == (True, "env")
        assert variable in entry["lock_reason"]
        assert r.file_text() == ""


def test_a_config_file_value_does_not_lock_the_field(rig: Any) -> None:
    from omrs.config.settings_file_write import write_settings

    with rig() as r:
        write_settings({"llamacpp_router_models_max": 3}, revision=None)  # a hand edit
        entry = r.get()["saved"]["models_max"]
        assert (entry["value"], entry["source"], entry["locked"]) == (3, "config-file", False)
        assert r.put({"models_max": 2}).status_code == 200
        assert r.get()["saved"]["models_max"]["value"] == 2


def test_a_stale_revision_is_409_and_every_answer_carries_the_revision(rig: Any) -> None:
    from omrs.config.settings_file_write import write_settings

    with rig() as r:
        first = r.get()["revision"]
        assert first == "absent"
        assert r.put({"models_max": 2}).json()["revision"] == r.h.store.read().revision
        write_settings({"web_port": 9100}, revision=None)  # a hand edit after the page read
        stale = r.put({"models_max": 3, "revision": first})
        assert stale.status_code == 409
        assert "changed on disk" in stale.json()["message"]
        assert '"llamacpp_router_models_max": 2' in r.file_text()


# ── Scopes ───────────────────────────────────────────────────────────────

WRITES_AND_CONTROLS = [
    ("put", "", {"models_max": 2}),
    ("post", "/start", None),
    ("post", "/stop", None),
    ("post", "/restart", None),
    ("put", "/models/qwen3-4b", {"preset": {"ctx-size": 4096}}),
    ("delete", "/models/qwen3-4b", None),
    ("post", "/install", {}),
]


@pytest.mark.parametrize(("method", "path", "body"), WRITES_AND_CONTROLS)
def test_a_bearer_token_never_writes_or_controls(
    rig: Any, method: str, path: str, body: Any
) -> None:
    with rig() as r:
        r.client.cookies.clear()
        header = edit.bearer(r.h.policy, "read", "graph", "run")
        kwargs: dict[str, Any] = {"headers": header}
        if body is not None:
            kwargs["json"] = body
        response = getattr(r.client, method)(URL + path, **kwargs)
        assert response.status_code == 403, response.text
        assert r.file_text() == ""


def test_the_program_and_the_mode_need_the_credentials_scope(
    rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with rig() as r:
        monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"credentials"})
        assert r.put({"router_server": "external"}).status_code == 403
        assert r.put({"binary": str(r.binary)}).status_code == 403
        mixed = {"models_max": 2, "router_server": "external"}
        assert r.put(mixed).status_code == 403
        assert r.file_text() == ""  # a refused body saves none of its keys


def test_preset_limits_and_the_address_need_manage_only(
    rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with rig() as r:
        monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"credentials"})
        assert r.put({"models_max": 2, "memory_margin_mib": 100}).status_code == 200
        assert r.put({"router_url": "http://127.0.0.1:8099/v1"}).status_code == 200
        assert r.put_model("qwen3-4b", {"preset": {"ctx-size": 4096}}).status_code == 200
        assert r.post("stop").status_code == 200


def test_the_settings_and_the_controls_need_manage(
    rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with rig() as r:
        monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"manage"})
        assert r.put({"models_max": 2}).status_code == 403
        for action in ("start", "stop", "restart"):
            assert r.post(action).status_code == 403
        assert r.get()["state"] == "stopped"  # a session with read still reads


# ── Lifecycle through the routes ─────────────────────────────────────────


def test_start_pending_restart_restart_and_stop(rig: Any) -> None:
    with rig() as r:
        r.save_files()
        started = r.post("start")
        assert started.status_code == 200, started.text
        body = r.wait_state("running")
        assert body["running_with"] == {"models_max": 4, "memory_margin_mib": 8192}
        assert body["pending_restart"] is False
        argv = r.starts()[-1]["argv"]
        assert argv[argv.index("--models-max") + 1] == "4"
        assert argv[argv.index("--models-memory-margin") + 1] == "8192"
        assert argv[argv.index("--host") + 1] == "127.0.0.1"
        first = r.pids()[-1]
        states = {m["id"]: m["state"] for m in body["models"]}
        assert states == {"qwen3-embedding-4b": "unloaded", "qwen3-4b": "unloaded"}

        assert r.put({"models_max": 2}).status_code == 200  # a save keeps the router running
        body = r.get()
        assert (body["state"], body["pending_restart"]) == ("running", True)
        assert r.pids()[-1] == first

        assert r.post("restart").status_code == 200
        body = r.wait_state("running")
        assert body["pending_restart"] is False
        assert body["running_with"]["models_max"] == 2
        argv = r.starts()[-1]["argv"]
        assert argv[argv.index("--models-max") + 1] == "2"
        assert r.pids()[-1] != first

        stopped = r.post("stop").json()
        assert (stopped["state"], stopped["running_with"]) == ("stopped", None)


def test_start_leaves_a_router_running_with_other_values_alone(rig: Any) -> None:
    with rig() as r:
        r.save_files()
        r.post("start")
        r.wait_state("running")
        first = r.pids()
        assert r.put({"memory_margin_mib": 1024}).status_code == 200
        body = r.post("start").json()
        assert (body["state"], body["pending_restart"]) == ("running", True)
        assert r.pids() == first


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({}, "not-configured"),  # the shipped list has no file
        ({"llamacpp_server_binary": "/no/such/llama-server"}, "binary-invalid"),
        ({"llamacpp_router_url": "http://192.168.1.20:8080/v1"}, "not-loopback"),
    ],
)
def test_a_refused_start_is_failed_with_a_fixed_reason(
    rig: Any, overrides: dict[str, Any], reason: str
) -> None:
    with rig(**overrides) as r:
        if reason != "not-configured":
            r.save_files()
        response = r.post("start")
        assert response.status_code == 200
        body = response.json()
        assert (body["state"], body["reason"]) == ("failed", reason)
        assert body["reason_text"]
        assert r.pids() == []


def test_no_program_set_and_none_provisioned_is_not_provisioned(
    rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs.integrations.llamacpp_runtime import provision

    monkeypatch.setattr(provision, "resolve_server_binary", lambda configured: configured)
    with rig(llamacpp_server_binary="") as r:
        r.save_files()
        body = r.post("start").json()
        assert (body["state"], body["reason"]) == ("failed", "not-provisioned")
        assert body["program"] == {"path": "", "source": "none"}


def test_an_external_router_is_never_started_stopped_or_restarted(rig: Any) -> None:
    with rig(llamacpp_router_server="external") as r:
        for action in ("start", "restart"):
            response = r.post(action)
            assert response.status_code == 409
            assert response.json()["reason"] == "external-server"
        assert r.post("stop").status_code == 409
        assert r.pids() == []
        assert r.get()["mode"] == "external"


def test_stop_with_nothing_recorded_signals_nothing(rig: Any) -> None:
    with rig() as r:
        body = r.post("stop").json()
        assert (body["state"], body["reason"]) == ("stopped", None)
        assert r.pids() == []


def test_a_crashed_router_reads_failed_exited(rig: Any) -> None:
    import os
    import signal

    with rig() as r:
        r.save_files()
        r.post("start")
        r.wait_state("running")
        pid = r.pids()[-1]
        os.killpg(pid, signal.SIGKILL)
        wait_until(lambda: not alive(pid))
        body = r.get()
        assert (body["state"], body["reason"]) == ("failed", "exited")


def test_leaving_the_app_stops_the_owned_router(rig: Any) -> None:
    pid = 0
    with rig() as r:
        r.save_files()
        r.post("start")
        r.wait_state("running")
        pid = r.pids()[-1]
    assert wait_until(lambda: not alive(pid), 10)


def test_the_status_never_holds_the_log_or_the_process_text(rig: Any) -> None:
    from omrs.integrations.llamacpp_runtime.router_spec import router_dir
    from omrs.integrations.llamacpp_runtime.state import state_root

    with rig() as r:
        r.save_files()
        r.post("start")
        r.wait_state("running")
        log = router_dir(state_root()) / "server.log"
        with log.open("a", encoding="utf-8") as handle:
            handle.write("SECRET-CHILD-TEXT\n")
        for path in (URL, "/v1/logs"):
            assert "SECRET-CHILD-TEXT" not in r.client.get(path).text, path
        assert "server.log" not in r.client.get(URL).text


def test_the_routes_start_no_process_themselves() -> None:
    for path in sorted(ROUTES_SOURCE.glob("llamacpp_router*.py")):
        source = path.read_text(encoding="utf-8")
        assert "subprocess" not in source, path.name
        assert "os.kill" not in source, path.name


# ── Contract ─────────────────────────────────────────────────────────────


def test_the_responses_conform_to_the_contract(rig: Any) -> None:
    check = ContractChecker()
    with rig() as r:
        check.check(r.client.get(URL), 200)
        check.check(r.put({"models_max": 0}), 400)
        check.check(r.put({"binary": "relative"}), 400)
        check.check(r.put({"idle_sleep": 60}), 400)
        check.check(r.put({"models_max": 2}), 200)
        r.save_files()
        check.check(r.client.get(URL), 200)
        check.check(r.post("start"), 200)
        r.wait_state("running")
        check.check(r.client.get(URL), 200)
        check.check(r.post("restart"), 200)
        r.wait_state("running")
        check.check(r.post("stop"), 200)
        check.check(r.client.put(URL, json={"models_max": 2}, headers={}), 403)
    with rig(llamacpp_router_server="external") as r:
        check.check(r.post("start"), 409)
    assert {"getLlamacppRouter", "saveLlamacppRouter", "startLlamacppRouter"} <= check.operations
    assert check.operations >= FAMILIES["llamacpp_router"] - {
        "saveLlamacppRouterModel",
        "deleteLlamacppRouterModel",
        "installLlamacppBuild",
        "getLlamacppBuild",
    }


def test_reading_the_settings_does_not_touch_a_router_file(rig: Any) -> None:
    with rig() as r:
        r.get()
        assert r.preset_text() == ""
        assert r.starts() == []
