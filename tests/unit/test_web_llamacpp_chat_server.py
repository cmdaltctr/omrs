"""Who runs the llama.cpp Chat server, and the model OMRS's server loads (ADR-108 D4, D5).

The choice ``external`` leaves the Chat server to its owner: Start and Restart
start nothing. The choice ``managed`` makes OMRS's own server load the Chat
model in force. A fake ``llama-server`` stands in for the real one.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit import test_web_llamacpp_server as server  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

from omrs.core.answer.settings import AnswerSettings  # noqa: E402
from omrs.transports.api import security  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

HF_ID = "Qwen/Qwen3-4B-GGUF:Q4_K_M"
harness = server.harness
rig = server.rig
ORIGIN = server.ORIGIN


def chat_put(r: Any, body: dict[str, Any]) -> Any:
    headers = {**ORIGIN, "Content-Type": "application/json"}
    return r.client.put("/v1/settings/chat", content=json.dumps(body), headers=headers)


# ── PUT /v1/llamacpp/server ──────────────────────────────────────────────


def test_a_body_with_a_model_is_refused_and_names_settings_chat(rig: Any) -> None:
    with rig() as r:
        response = r.put({"model": str(r.model)})
        assert response.status_code == 400
        assert response.json()["message"] == "Set the Chat model in Settings > Chat."
        assert r.h.file_text() == ""


def test_an_unknown_chat_server_choice_is_400(rig: Any) -> None:
    with rig() as r:
        response = r.put({"chat_server": "router"})
        assert response.status_code == 400
        assert "router" not in response.json()["message"]
        assert r.get()["saved"]["chat_server"]["source"] == "default"


def test_the_chat_server_choice_is_saved_and_read_back(rig: Any) -> None:
    with rig(llamacpp_chat_server="external") as r:
        assert r.get()["saved"]["chat_server"]["value"] == "external"
        response = r.put({"chat_server": "managed"})
        assert response.status_code == 200, response.text
        saved = response.json()["saved"]["chat_server"]
        assert (saved["value"], saved["source"], saved["kind"]) == (
            "managed",
            "config-file",
            "choice",
        )
        assert '"llamacpp_chat_server": "managed"' in r.h.file_text()


def test_the_chat_server_choice_needs_the_credentials_scope(
    rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with rig() as r:
        monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"credentials"})
        assert r.put({"chat_server": "external"}).status_code == 403
        assert r.h.file_text() == ""


def test_a_switch_to_external_while_running_is_409_and_keeps_the_server(rig: Any) -> None:
    check = ContractChecker()
    with rig() as r:
        r.save_all()
        r.post("start")
        r.wait_state("running")
        before, pid = r.h.file_text(), r.program.pids()[-1]
        response = r.put({"chat_server": "external"})
        check.check(response, 409)
        assert response.status_code == 409
        assert response.json()["reason"] == "server-running"
        assert r.h.file_text() == before
        body = r.get()
        assert (body["state"], r.program.pids()[-1]) == ("running", pid)


# ── Start and Restart ───────────────────────────────────────────────────


@pytest.mark.parametrize("action", ["start", "restart"])
def test_start_and_restart_with_external_are_409_and_start_nothing(rig: Any, action: str) -> None:
    check = ContractChecker()
    with rig(llamacpp_chat_server="external") as r:
        r.save_all()
        response = r.post(action)
        check.check(response, 409)
        assert response.json()["reason"] == "external-server"
        assert r.program.pids() == []


def test_start_with_a_chat_provider_other_than_llamacpp_is_not_configured(rig: Any) -> None:
    other = AnswerSettings(enabled=True, provider="openrouter", model="deepseek/deepseek-v4")
    with rig(answer=other) as r:
        r.save_all()
        body = r.post("start").json()
        assert (body["state"], body["reason"]) == ("failed", "not-configured")
        assert body["chat_model"] == {
            "provider": "openrouter",
            "model": "deepseek/deepseek-v4",
            "usable": False,
        }
        assert r.program.pids() == []


def test_start_loads_the_chat_model_by_hugging_face_id(rig: Any) -> None:
    with rig(answer=AnswerSettings(enabled=True, provider="llamacpp", model=HF_ID)) as r:
        r.save_all()
        assert r.post("start").status_code == 200
        body = r.wait_state("running")
        argv = r.program.argv()
        assert argv[argv.index("-hf") + 1] == HF_ID
        assert body["running_with"]["model_kind"] == "hf"
        assert body["chat_model"] == {"provider": "llamacpp", "model": HF_ID, "usable": True}


def test_a_chat_save_while_running_asks_for_a_restart(rig: Any) -> None:
    with rig() as r:
        r.save_all()
        r.post("start")
        assert r.wait_state("running")["pending_restart"] is False
        assert chat_put(r, {"provider": "llamacpp", "model": HF_ID}).status_code == 200
        body = r.get()
        assert (body["state"], body["pending_restart"]) == ("running", True)
