"""A saved document router reaches the running app (one-llamacpp-router D3, D-c).

``document_routers`` (a file map) and ``document_router`` (the host choice) apply
in a running ``omrs web`` the way ``llamacpp_models`` and ``decision_models`` do:
the saved file feeds the same live path, the next request resolves the new value
once at its boundary, and a value that ``env`` or ``.env`` sets stays locked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_connection_summary import make_settings  # noqa: E402
from tests.unit.test_web_connections_edit import ORIGIN, harness  # noqa: E402, F401

from omrs import compose_decision  # noqa: E402
from omrs.compose_providers import (  # noqa: E402
    ProviderValues,
    apply_provider_values,
    provider_values_from_file,
)
from omrs.config.settings_file import SettingsFile  # noqa: E402
from omrs.config.settings_maps import DocumentRouterEntry  # noqa: E402
from omrs.core.settings import ROUTER_LIVE_FIELDS, ROUTER_LIVE_MAPS  # noqa: E402

DECISIONS = "/v1/settings/decision-models"
ROUTERS = "/v1/settings/document-routers"
READING = "/v1/settings/document-reading"
MODEL = {"kind": "llamacpp", "address": "http://127.0.0.1:9200", "model": "clef-q8_0"}


def _router(question: str = "Does the text match?") -> dict[str, Any]:
    return {"model": "clef", "question": question, "threshold": 0.2}


def _revision(h: Any) -> str:
    return h.store.read().revision


def _save_model(h: Any) -> None:
    body = {"entry": MODEL, "revision": _revision(h)}
    response = h.client.put(f"{DECISIONS}/clef", json=body, headers=ORIGIN)
    assert response.status_code == 200, response.text


def _save_router(h: Any, name: str, question: str) -> None:
    body = {"entry": _router(question), "revision": _revision(h)}
    response = h.client.put(f"{ROUTERS}/{name}", json=body, headers=ORIGIN)
    assert response.status_code == 200, response.text


def _save_host(h: Any, name: str | None) -> None:
    body = {"values": {"document_router": name}, "revision": _revision(h)}
    response = h.client.put(READING, json=body, headers=ORIGIN)
    assert response.status_code == 200, response.text
    # This route does not reload by itself; the next request does, before it runs.
    assert h.client.get(ROUTERS).status_code == 200


def _hand_edit(h: Any, **content: Any) -> None:
    """Write ``omrs.jsonc`` as an editor would, behind the server's back."""
    content.setdefault("decision_models", {"clef": MODEL})
    h.store.path.parent.mkdir(parents=True, exist_ok=True)
    h.store.path.write_text(json.dumps(content), encoding="utf-8")


def _file(maps: dict[str, Any] | None = None, **values: Any) -> SettingsFile:
    """Return a file that holds *values* and *maps*, as the store reads it."""
    return SettingsFile(
        directory=Path("/unused"), path=Path("/unused/omrs.jsonc"), values=values, maps=maps or {}
    )


def _base(**extra: Any) -> Any:
    """Return launch settings, with the source word of each setting in *sources*."""
    sources = extra.pop("sources", {})
    settings = make_settings(**extra)
    object.__setattr__(settings, "setting_sources", dict(sources))
    return settings


ENTRY = DocumentRouterEntry(model="clef", question="q", threshold=0.3)


# ── The tuples: one source of truth ──────────────────────────────────────


def test_the_live_tuples_name_the_router_map_and_the_host_choice() -> None:
    assert "document_routers" in ROUTER_LIVE_MAPS
    assert {"document_router", "document_routers"} <= set(ROUTER_LIVE_FIELDS)


# ── Compose: file values reach the settings ──────────────────────────────


def test_compose_applies_the_saved_routers_and_host_choice() -> None:
    values = ProviderValues(
        values={"document_router": "mine"},
        sources={"document_router": "config-file"},
        maps={"document_routers": {"mine": ENTRY}},
    )
    applied = apply_provider_values(_base(), values)
    assert applied.document_router == "mine"
    assert set(applied.document_routers) == {"mine"}
    assert applied.setting_sources["document_router"] == "config-file"


def test_a_host_choice_that_env_sets_stays_locked() -> None:
    base = _base(document_router="from-env", sources={"document_router": "env"})
    values = ProviderValues(values={"document_router": "from-file"})
    assert apply_provider_values(base, values).document_router == "from-env"
    read = provider_values_from_file(base, _file(document_router="from-file"), None)
    assert "document_router" not in read.values
    assert "document_router" not in read.unset


def test_the_file_values_carry_the_routers_and_the_host_choice() -> None:
    file = _file({"document_routers": {"mine": ENTRY}}, document_router="mine")
    read = provider_values_from_file(_base(), file, None)
    assert read.values["document_router"] == "mine"
    assert read.sources["document_router"] == "config-file"
    assert set(read.maps["document_routers"]) == {"mine"}


def test_a_removed_host_choice_goes_back_to_the_default() -> None:
    base = _base(document_router="old", sources={"document_router": "config-file"})
    read = provider_values_from_file(base, _file(), None)
    assert "document_router" in read.unset
    assert apply_provider_values(base, read).document_router == ""


# ── The running app ──────────────────────────────────────────────────────


def test_a_saved_router_and_host_choice_reach_the_next_request(harness: Any) -> None:  # noqa: F811
    with harness() as h:
        engine = h.engines[0]
        assert engine.resolve_settings().document_routers == {}
        _save_model(h)
        _save_router(h, "handwriting", "Does the text match?")
        _save_host(h, "handwriting")

        settings = engine.resolve_settings()
        assert settings.document_router == "handwriting"
        assert settings.document_routers["handwriting"].question == "Does the text match?"
        judge = compose_decision.page_judge_for(settings)
        assert judge is not None
        assert judge.name == "handwriting"

        _save_router(h, "handwriting", "Is this a form?")
        again = compose_decision.page_judge_for(engine.resolve_settings())
        assert again is not None
        assert again.question == "Is this a form?"


def test_the_option_set_follows_the_saved_router(harness: Any) -> None:  # noqa: F811
    with harness() as h:
        engine = h.engines[0]
        before = engine._graph_host(None).host.options["document_router"]
        assert before.inherited is None
        assert before.unavailable["handwriting"]  # no router of this name yet
        _save_model(h)
        _save_router(h, "handwriting", "Does the text match?")
        _save_host(h, "handwriting")

        after = engine._graph_host(None).host.options["document_router"]
        assert after.inherited == "handwriting"
        with pytest.raises(KeyError):
            after.unavailable["handwriting"]  # a defined router is available


def test_removing_the_host_choice_applies_without_a_restart(harness: Any) -> None:  # noqa: F811
    with harness() as h:
        engine = h.engines[0]
        _save_model(h)
        _save_router(h, "handwriting", "Does the text match?")
        _save_host(h, "handwriting")
        assert engine.resolve_settings().document_router == "handwriting"
        _save_host(h, None)
        assert engine.resolve_settings().document_router == ""


def test_a_hand_edit_of_the_file_applies_at_the_next_request(harness: Any) -> None:  # noqa: F811
    """The stamp check reloads a file edited behind the server's back."""
    with harness() as h:
        engine = h.engines[0]
        _hand_edit(h, document_router="hand", document_routers={"hand": _router()})
        h.client.get("/v1/settings/document-routers")  # any request reloads a changed file
        assert engine.resolve_settings().document_router == "hand"


def test_a_host_choice_locked_by_the_environment_is_not_replaced(harness: Any) -> None:  # noqa: F811
    with harness(document_router="from-env", sources={"document_router": "env"}) as h:
        engine = h.engines[0]
        _hand_edit(h, document_router="handwriting", document_routers={"handwriting": _router()})
        h.client.get(ROUTERS)
        settings = engine.resolve_settings()
        assert settings.document_router == "from-env"
        assert "handwriting" in settings.document_routers  # the map is not locked


def test_a_collection_resolves_the_saved_router(harness: Any) -> None:  # noqa: F811
    """The settings of a collection run (ingest page routing) hold the new router."""
    with harness() as h:
        engine = h.engines[0]
        _save_model(h)
        _save_router(h, "handwriting", "Does the text match?")
        _save_host(h, "handwriting")
        effective, _ = engine._resolve_bound("documents")
        assert effective.document_router == "handwriting"
        assert "handwriting" in effective.document_routers


def _row(h: Any, key: str) -> dict[str, Any]:
    response = h.client.get(READING)
    assert response.status_code == 200, response.text
    return next(r for r in response.json()["settings"] if r["key"] == key)


def test_the_reading_row_shows_the_saved_router_as_in_force(harness: Any) -> None:  # noqa: F811
    with harness() as h:
        _save_model(h)
        _save_router(h, "handwriting", "Does the text match?")
        _save_host(h, "handwriting")
        row = _row(h, "document_router")
        assert (row["value"], row["saved"], row["source"]) == (
            "handwriting", "handwriting", "config-file",
        )  # fmt: skip
        assert row["restart_pending"] is False
        _save_host(h, None)
        row = _row(h, "document_router")
        assert (row["value"], row["source"], row["restart_pending"]) == ("", "default", False)
