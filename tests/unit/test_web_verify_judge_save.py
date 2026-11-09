"""Saving a claim-judge choice from Studio (task 8.3a; spec ``claim-judge-strategies``).

``POST /v1/pipelines/{id}/revisions`` refuses a graph whose Verify claims step
picks a strategy that is unknown or not set up on this host, with a plain
message that names the missing setting. Inherit (``null``) always saves.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_runs_support import (  # noqa: E402
    BASE,
    ORIGIN,
    build_app,
    login,
    make_engine,
    new_pipeline,
)

from omrs.pipeline_templates import answer_template  # noqa: E402


def _document(**verify: Any) -> dict[str, Any]:
    data = answer_template().model_dump(mode="json")["graph"]
    for node in data["nodes"]:
        if node["id"] == "verify":
            node["params"] = {**(node.get("params") or {}), **verify}
    return data


@pytest.fixture
def client(tmp_path: Path, effective_settings: Any) -> Any:
    settings = effective_settings().model_copy(
        update={"llamacpp_models": {"clef": {"model": "clef-flash", "file": "/m/clef.gguf"}}}
    )
    settings = settings.model_copy(
        update={"answer": settings.answer.model_copy(update={"verify_model": "granite-guardian"})}
    )
    app, policy = build_app(tmp_path, make_engine(lambda: settings))
    with TestClient(app, base_url=BASE) as test_client:
        login(test_client, policy)
        yield test_client


def _save(client: Any, document: dict[str, Any]) -> Any:
    pipeline_id = new_pipeline(client.app, "Answer", {"zoom": 1})["pipeline_id"]
    url = f"/v1/pipelines/{pipeline_id}/revisions"
    return client.post(url, json={"document": document}, headers=ORIGIN)


def test_a_not_ready_strategy_is_refused_naming_the_setting(client: Any) -> None:
    response = _save(client, _document(verify_judge="granite_guardian"))
    assert response.status_code == 400, response.text
    body = response.json()
    assert "answer.verify_model" in body["message"] and "granite-guardian" in body["message"]


def test_inherit_and_the_chat_judge_save(client: Any) -> None:
    assert _save(client, _document(verify_judge=None)).status_code == 201
    assert _save(client, _document(verify_judge="chat")).status_code == 201
