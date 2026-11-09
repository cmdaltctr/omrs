"""Temperature, seed and allowed hosts on the Chat and judge settings routes (tasks 1.5, 7.6).

Spec ``answer-sampling``: the Chat read and save carry ``temperature``,
``seed`` and ``allowed_hosts``; the judge read and save carry the same names
for ``answer.verify_temperature``, ``answer.verify_seed`` and
``answer.verify_allowed_hosts``. Each read lists the values the provider
ignores. An out-of-range value is a 400 that changes nothing; a value the
environment sets is locked and a save that sends it is a 409.

Body rules this suite pins (design D1, D11):

- A value left out keeps the saved value.
- ``null`` (or ``""`` for the host list) removes the saved value.
- A body with only these values keeps the provider, the model and the level.
- A clear (an empty body) also removes every unlocked value.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_connection_summary import make_settings  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402
from tests.unit.test_web_reasoning_settings import CHAT, JUDGE, file_bytes, put  # noqa: E402

from omrs import compose  # noqa: E402
from omrs.core.answer.settings import AnswerSettings  # noqa: E402
from omrs.transports.api.routes import chat_settings  # noqa: E402


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch) -> Any:
    def apply(**overrides: Any) -> Any:
        answer = overrides.pop("answer", None)
        settings = make_settings(**overrides)
        if answer is not None:
            object.__setattr__(settings, "answer", answer)
        monkeypatch.setattr(compose, "get_settings", lambda: settings)
        return settings

    return apply


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any, configure: Any, monkeypatch: pytest.MonkeyPatch):
    configure()
    monkeypatch.setattr(chat_settings, "module_installed", lambda name: True)
    engine = make_engine(lance_store(tmp_path), effective_settings())
    applied: list[Any] = []
    engine.use_provider_settings = applied.append  # type: ignore[method-assign]
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        client.applied = applied  # type: ignore[attr-defined]
        client.store = app.state.mcp_http.store  # type: ignore[attr-defined]
        client.saved = lambda key: app.state.mcp_http.store.read().values.get(key)  # type: ignore[attr-defined]
        yield client


_ALL = ("temperature", "seed", "allowed_hosts")
_JUDGE_PATH = {
    "temperature": "verify_temperature",
    "seed": "verify_seed",
    "allowed_hosts": "verify_allowed_hosts",
}


def _path(url: str, name: str) -> str:
    return f"answer.{_JUDGE_PATH[name] if url == JUDGE else name}"


# ── GET ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("url", [CHAT, JUDGE])
def test_get_reports_empty_values(setup: Any, url: str) -> None:
    body = setup.get(url).json()
    assert (body["temperature"], body["seed"], body["allowed_hosts"]) == (None, None, "")
    assert body["sampling_locked"] == []
    assert body["sampling_lock_reason"] is None


def test_chat_get_reports_what_the_provider_ignores(setup: Any, configure: Any) -> None:
    assert setup.get(CHAT).json()["sampling_ignored"] == ["allowed_hosts"]  # Ollama
    configure(answer_provider="anthropic")
    assert setup.get(CHAT).json()["sampling_ignored"] == list(_ALL)


def test_judge_get_reports_what_its_provider_ignores(setup: Any) -> None:
    assert setup.get(JUDGE).json()["sampling_ignored"] == []  # the judge resolves to OpenRouter


def test_chat_get_reports_saved_values(setup: Any, configure: Any) -> None:
    configure(answer=AnswerSettings(provider="ollama", model="m", temperature=0, seed=20261101))
    body = setup.get(CHAT).json()
    assert (body["temperature"], body["seed"]) == (0, 20261101)


@pytest.mark.parametrize(
    ("url", "variable", "explicit"),
    [
        (CHAT, "ANSWER__SEED", "answer.seed"),
        (JUDGE, "ANSWER__VERIFY_SEED", "answer.verify_seed"),
        (CHAT, "ANSWER__ALLOWED_HOSTS", "answer.allowed_hosts"),
        (JUDGE, "ANSWER__VERIFY_ALLOWED_HOSTS", "answer.verify_allowed_hosts"),
    ],
)
def test_get_lock_names_the_variable(
    setup: Any, configure: Any, url: str, variable: str, explicit: str
) -> None:
    configure(explicit=frozenset({explicit}))
    body = setup.get(url).json()
    name = explicit.removeprefix("answer.").removeprefix("verify_")
    assert body["sampling_locked"] == [name]
    assert variable in body["sampling_lock_reason"]
    assert body["locked"] is False and body["reasoning_locked"] is False


# ── PUT: save ────────────────────────────────────────────────────────────


def test_chat_save_writes_temperature_and_seed(setup: Any) -> None:
    response = put(
        setup, CHAT, {"provider": "ollama", "model": "m", "temperature": 0, "seed": 20261101}
    )
    assert response.status_code == 200, response.text
    assert (setup.saved("answer.temperature"), setup.saved("answer.seed")) == (0, 20261101)
    body = response.json()
    assert (body["temperature"], body["seed"]) == (0, 20261101)
    assert setup.applied[-1].answer.temperature == 0
    assert setup.applied[-1].answer.seed == 20261101


def test_judge_save_writes_its_own_values(setup: Any) -> None:
    response = put(setup, JUDGE, {"temperature": 0.2, "seed": 7, "allowed_hosts": "Z.AI"})
    assert response.status_code == 200, response.text
    assert setup.saved("answer.verify_temperature") == 0.2
    assert setup.saved("answer.verify_seed") == 7
    assert setup.saved("answer.verify_allowed_hosts") == "Z.AI"
    assert setup.saved("answer.seed") is None and setup.saved("answer.temperature") is None
    assert setup.applied[-1].answer.verify_seed == 7


def test_chat_save_normalises_the_host_list(setup: Any) -> None:
    response = put(setup, CHAT, {"allowed_hosts": " Fireworks, ,DeepInfra "})
    assert response.status_code == 200, response.text
    assert setup.saved("answer.allowed_hosts") == "Fireworks,DeepInfra"
    assert response.json()["allowed_hosts"] == "Fireworks,DeepInfra"


def test_a_values_only_body_keeps_the_choice_and_level(setup: Any) -> None:
    put(setup, CHAT, {"provider": "llamacpp", "model": "m", "reasoning": "low"})
    response = put(setup, CHAT, {"seed": 3})
    assert response.status_code == 200, response.text
    assert (setup.saved("answer.provider"), setup.saved("answer.model")) == ("llamacpp", "m")
    assert setup.saved("answer.reasoning") == "low"
    assert setup.saved("answer.seed") == 3


def test_a_value_left_out_keeps_the_saved_one(setup: Any) -> None:
    put(setup, CHAT, {"temperature": 0, "seed": 3})
    response = put(setup, CHAT, {"seed": 4})
    assert response.status_code == 200, response.text
    assert (setup.saved("answer.temperature"), setup.saved("answer.seed")) == (0, 4)


@pytest.mark.parametrize("url", [CHAT, JUDGE])
def test_null_removes_a_value(setup: Any, url: str) -> None:
    put(setup, url, {"temperature": 0, "seed": 3, "allowed_hosts": "Fireworks"})
    response = put(setup, url, {"temperature": None, "seed": None, "allowed_hosts": ""})
    assert response.status_code == 200, response.text
    for name in _ALL:
        assert setup.saved(_path(url, name)) is None
    body = response.json()
    assert (body["temperature"], body["seed"], body["allowed_hosts"]) == (None, None, "")


def test_a_clear_also_removes_the_values(setup: Any) -> None:
    put(setup, CHAT, {"provider": "ollama", "model": "m", "temperature": 0, "seed": 1})
    response = put(setup, CHAT, None)
    assert response.status_code == 200, response.text
    assert setup.saved("answer.temperature") is None and setup.saved("answer.seed") is None


# ── PUT: refuse (400) ────────────────────────────────────────────────────


@pytest.mark.parametrize("url", [CHAT, JUDGE])
@pytest.mark.parametrize(
    "body",
    [
        {"temperature": 3},
        {"temperature": -0.5},
        {"seed": -1},
        {"seed": 2**31},
        {"seed": 1.5},
        {"seed": "7"},
        {"allowed_hosts": "Fire;works"},
        {"allowed_hosts": ",".join(["h"] * 17)},
    ],
)
def test_a_bad_value_is_400_and_changes_nothing(setup: Any, url: str, body: dict[str, Any]) -> None:
    before = file_bytes(setup)
    response = put(setup, url, body)
    assert response.status_code == 400, response.text
    assert file_bytes(setup) == before
    assert setup.applied == []


# ── PUT: lock (409) ──────────────────────────────────────────────────────


def test_chat_locked_seed_is_409_naming_the_variable(setup: Any, configure: Any) -> None:
    configure(explicit=frozenset({"answer.seed"}))
    before = file_bytes(setup)
    response = put(setup, CHAT, {"seed": 1})
    assert response.status_code == 409
    assert "ANSWER__SEED" in response.text
    assert file_bytes(setup) == before


def test_judge_locked_host_list_is_409(setup: Any, configure: Any) -> None:
    configure(explicit=frozenset({"answer.verify_allowed_hosts"}))
    response = put(setup, JUDGE, {"allowed_hosts": "Z.AI"})
    assert response.status_code == 409
    assert "ANSWER__VERIFY_ALLOWED_HOSTS" in response.text


def test_a_locked_value_still_lets_the_others_save(setup: Any, configure: Any) -> None:
    configure(explicit=frozenset({"answer.seed"}))
    response = put(setup, CHAT, {"temperature": 0})
    assert response.status_code == 200, response.text
    assert setup.saved("answer.temperature") == 0
    assert put(setup, CHAT, None).status_code == 200  # a clear skips the locked value


# ── contract ─────────────────────────────────────────────────────────────


def test_sampling_responses_conform(setup: Any, configure: Any) -> None:
    check = ContractChecker()
    check.check(setup.get(CHAT), 200)
    check.check(setup.get(JUDGE), 200)
    check.check(put(setup, CHAT, {"temperature": 0, "seed": 1, "allowed_hosts": "Fireworks"}), 200)
    check.check(put(setup, JUDGE, {"temperature": 0.5, "seed": 2}), 200)
    check.check(put(setup, CHAT, {"temperature": 9}), 400)
    configure(explicit=frozenset({"answer.seed", "answer.verify_seed"}))
    check.check(put(setup, CHAT, {"seed": 1}), 409)
    check.check(put(setup, JUDGE, {"seed": 1}), 409)
    check.check(setup.get(CHAT), 200)
