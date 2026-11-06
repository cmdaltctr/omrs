"""Decision models and routers as named maps in ``omrs.jsonc`` (document-reading-routers, 1.1).

``decision_models`` and ``document_routers`` are file-only maps keyed by entry
name. A broken entry is ignored and listed, and the others load. No environment
variable sets a map. ``document_router`` (the host router name) follows the
normal source order. A key field inside an entry holds a reference only.

Every test points ``OMRS_CONFIG_DIR`` at a temporary folder. Keys and addresses
here are fake constants.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from omrs.config import Settings, provenance
from omrs.config.settings_file import KIND_INVALID, KIND_UNKNOWN, read_settings_file
from omrs.config.user_config import REFERENCE_RULE

#: A literal key that must never be kept, logged or listed.
LITERAL_KEY = "sk-fake-literal-key-0000"

VARIABLES = ("DOCUMENT_ROUTER", "DECISION_MODELS", "DOCUMENT_ROUTERS", "TYPESAFE_API_KEY")

CLEF_LOCAL: dict[str, Any] = {
    "kind": "llamacpp",
    "address": "http://127.0.0.1:8090",
    "model": "clef-flash-q8_0",
    "images": True,
    "server": "external",
}
JEV: dict[str, Any] = {
    "kind": "typesafe",
    "address": "https://api.typesafe.example",
    "model": "jev",
    "images": True,
    "key": "env://TYPESAFE_API_KEY",
}
HANDWRITING: dict[str, Any] = {
    "model": "clef-local",
    "question": "Is the text layer of this page usable?",
    "threshold": 0.172,
    "images": True,
}


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())  # a repo .env must not leak in
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def write_config(root: Path, data: dict[str, Any]) -> None:
    (root / "omrs.jsonc").write_text(json.dumps(data), encoding="utf-8")


def build() -> Settings:
    return Settings(_env_file=None)


def problems_at(prefix: str) -> list[tuple[str, str, str]]:
    return [
        (p.kind, p.key, p.message)
        for p in read_settings_file().problems
        if p.key.startswith(prefix)
    ]


# ── Loading (spec: Hand-written router) ──────────────────────────────────


def test_a_hand_written_router_and_its_model_load_by_name(folder: Path) -> None:
    write_config(
        folder,
        {
            "decision_models": {"clef-local": CLEF_LOCAL},
            "document_routers": {"handwriting": HANDWRITING},
        },
    )

    settings = build()

    model = settings.decision_models["clef-local"]
    router = settings.document_routers["handwriting"]
    assert (model.kind, model.address, model.model, model.images) == (
        "llamacpp",
        "http://127.0.0.1:8090",
        "clef-flash-q8_0",
        True,
    )
    assert (model.server, model.key) == ("external", None)
    assert (router.model, router.threshold, router.images) == ("clef-local", 0.172, True)
    assert (router.max_chars, router.send_off_machine) == (2000, False)
    assert settings.setting_sources["decision_models.clef-local"] == "config-file"
    assert settings.setting_sources["document_routers.handwriting"] == "config-file"
    assert read_settings_file().problems == ()


def test_managed_entry_names_a_model_list_entry_and_holds_no_files(folder: Path) -> None:
    """The files and their checksums moved to ``llamacpp_models`` (one-llamacpp-router D3)."""
    managed = {**CLEF_LOCAL, "server": "managed"}
    write_config(folder, {"decision_models": {"clef-managed": managed}})

    entry = build().decision_models["clef-managed"]

    assert (entry.server, entry.model) == ("managed", "clef-flash-q8_0")
    assert not hasattr(entry, "model_file")


def test_no_map_means_empty_maps_and_no_router(folder: Path) -> None:
    settings = build()
    assert dict(settings.decision_models) == {}
    assert dict(settings.document_routers) == {}
    assert settings.document_router == ""


def test_map_keys_are_not_reported_as_unknown(folder: Path) -> None:
    write_config(
        folder,
        {
            "decision_models": {"clef-local": CLEF_LOCAL},
            "document_routers": {"handwriting": HANDWRITING},
        },
    )
    assert [p for p in read_settings_file().problems if p.kind == KIND_UNKNOWN] == []


# ── Broken entries (spec: Broken entry) ──────────────────────────────────


def test_a_router_with_a_text_threshold_is_ignored_and_listed(folder: Path) -> None:
    write_config(
        folder,
        {
            "decision_models": {"clef-local": CLEF_LOCAL},
            "document_routers": {
                "broken": {**HANDWRITING, "threshold": "high"},
                "handwriting": HANDWRITING,
            },
        },
    )

    settings = build()

    assert sorted(settings.document_routers) == ["handwriting"]
    problems = problems_at("document_routers.broken")
    assert [(kind, key) for kind, key, _ in problems] == [
        (KIND_INVALID, "document_routers.broken.threshold")
    ]
    assert "high" not in problems[0][2]
    assert "number" in problems[0][2]


@pytest.mark.parametrize(
    ("entry", "field", "kind"),
    [
        ({**HANDWRITING, "threshold": 1.5}, "threshold", KIND_INVALID),
        ({**HANDWRITING, "threshold": True}, "threshold", KIND_INVALID),
        ({**HANDWRITING, "images": "yes"}, "images", KIND_INVALID),
        ({**HANDWRITING, "max_chars": 0}, "max_chars", KIND_INVALID),
        ({**HANDWRITING, "question": "   "}, "question", KIND_INVALID),
        ({**HANDWRITING, "model": ""}, "model", KIND_INVALID),
        ({k: v for k, v in HANDWRITING.items() if k != "question"}, "question", KIND_INVALID),
        ({**HANDWRITING, "colour": "red"}, "colour", KIND_UNKNOWN),
    ],
    ids=[
        "above-one",
        "boolean",
        "text-flag",
        "zero-chars",
        "blank",
        "empty-model",
        "missing",
        "unknown",
    ],
)
def test_each_broken_router_field_is_named(
    folder: Path, entry: dict[str, Any], field: str, kind: str
) -> None:
    write_config(folder, {"document_routers": {"r1": entry, "handwriting": HANDWRITING}})

    settings = build()

    assert sorted(settings.document_routers) == ["handwriting"]
    assert [(k, key) for k, key, _ in problems_at("document_routers.r1")] == [
        (kind, f"document_routers.r1.{field}")
    ]


@pytest.mark.parametrize(
    ("entry", "field"),
    [
        ({**CLEF_LOCAL, "kind": "gpt"}, "kind"),
        ({**CLEF_LOCAL, "address": "ftp://127.0.0.1"}, "address"),
        ({**CLEF_LOCAL, "address": "http://user:pw@127.0.0.1"}, "address"),
        ({**CLEF_LOCAL, "server": "cloud"}, "server"),
        ({**CLEF_LOCAL, "images": 1}, "images"),
    ],
    ids=["kind", "scheme", "user", "server", "number-flag"],
)
def test_each_broken_decision_model_field_is_named(
    folder: Path, entry: dict[str, Any], field: str
) -> None:
    write_config(folder, {"decision_models": {"m1": entry, "clef-local": CLEF_LOCAL}})

    settings = build()

    assert sorted(settings.decision_models) == ["clef-local"]
    found = problems_at("decision_models.m1")
    assert [(k, key) for k, key, _ in found] == [(KIND_INVALID, f"decision_models.m1.{field}")]
    assert all("ftp" not in message and "pw" not in message for _, _, message in found)


@pytest.mark.parametrize("name", ["none", "", "has.dot", "-dash", "x" * 65, "a b"])
def test_a_bad_router_name_is_ignored_and_listed(folder: Path, name: str) -> None:
    write_config(folder, {"document_routers": {name: HANDWRITING, "handwriting": HANDWRITING}})

    settings = build()

    assert sorted(settings.document_routers) == ["handwriting"]
    assert [kind for kind, _, _ in problems_at(f"document_routers.{name}")] == [KIND_INVALID]


def test_an_entry_that_is_not_an_object_is_listed(folder: Path) -> None:
    write_config(folder, {"decision_models": {"m1": "clef", "clef-local": CLEF_LOCAL}})
    assert sorted(build().decision_models) == ["clef-local"]
    assert [key for _, key, _ in problems_at("decision_models.m1")] == ["decision_models.m1"]


def test_a_map_that_is_not_an_object_is_listed(folder: Path) -> None:
    write_config(folder, {"document_routers": ["handwriting"], "community_seed": 4})
    settings = build()
    assert dict(settings.document_routers) == {}
    assert settings.community_seed == 4
    assert [(k, key) for k, key, _ in problems_at("document_routers")] == [
        (KIND_INVALID, "document_routers")
    ]


# ── No environment variable sets a map ───────────────────────────────────


def test_no_environment_variable_sets_a_map(folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISION_MODELS", json.dumps({"env-model": CLEF_LOCAL}))
    monkeypatch.setenv("DOCUMENT_ROUTERS", json.dumps({"env-router": HANDWRITING}))
    monkeypatch.setenv("DOCUMENT_ROUTERS__ENV2__MODEL", "clef-local")
    write_config(folder, {"document_routers": {"handwriting": HANDWRITING}})

    settings = build()

    assert dict(settings.decision_models) == {}
    assert sorted(settings.document_routers) == ["handwriting"]
    assert settings.setting_sources["document_routers.handwriting"] == "config-file"


def test_a_broken_map_variable_does_not_stop_start_up(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DECISION_MODELS", "not json")
    assert dict(build().decision_models) == {}


def test_an_explicit_option_cannot_set_a_map(folder: Path) -> None:
    write_config(folder, {"document_routers": {"handwriting": HANDWRITING}})
    settings = Settings(_env_file=None, document_routers={"other": HANDWRITING})  # type: ignore[call-arg]
    assert sorted(settings.document_routers) == ["handwriting"]


# ── document_router: the host router name follows the source order ───────


def test_the_file_names_the_host_router(folder: Path) -> None:
    write_config(folder, {"document_router": "handwriting"})
    settings = build()
    assert settings.document_router == "handwriting"
    assert settings.setting_sources["document_router"] == "config-file"


def test_the_environment_wins_over_the_file_and_locks_the_router(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(folder, {"document_router": "handwriting"})
    monkeypatch.setenv("DOCUMENT_ROUTER", "typed")
    settings = build()
    assert settings.document_router == "typed"
    assert settings.setting_sources["document_router"] == "env"
    assert "document_router" not in settings.config_file_fields


def test_dotenv_names_the_host_router(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(folder, {"document_router": "handwriting"})
    env_file = tmp_path / "test.env"
    env_file.write_text("DOCUMENT_ROUTER=from-dotenv\n", encoding="utf-8")
    settings = Settings(_env_file=env_file)
    assert settings.document_router == "from-dotenv"
    assert settings.setting_sources["document_router"] == "dotenv"


def test_a_padded_router_name_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENT_ROUTER", "  handwriting ")
    assert build().document_router == "handwriting"


# ── Key references inside an entry ───────────────────────────────────────


def test_a_key_reference_is_kept_unresolved(folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", LITERAL_KEY)
    write_config(folder, {"decision_models": {"jev": JEV}})
    entry = build().decision_models["jev"]
    assert entry.key == "env://TYPESAFE_API_KEY"


def test_a_literal_key_is_ignored_and_listed_and_never_kept(
    folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_config(folder, {"decision_models": {"jev": {**JEV, "key": LITERAL_KEY}}})
    caplog.set_level(logging.DEBUG)

    settings = build()

    entry = settings.decision_models["jev"]
    assert entry.key is None
    assert entry.model == "jev"
    assert problems_at("decision_models.jev") == [
        (KIND_INVALID, "decision_models.jev.key", REFERENCE_RULE)
    ]
    assert LITERAL_KEY not in caplog.text
    assert LITERAL_KEY not in repr(settings.decision_models)
    assert LITERAL_KEY not in repr(read_settings_file())


def test_a_key_that_is_not_text_is_ignored_and_listed(folder: Path) -> None:
    write_config(folder, {"decision_models": {"jev": {**JEV, "key": 12345}}})
    assert build().decision_models["jev"].key is None
    assert [key for _, key, _ in problems_at("decision_models.jev")] == ["decision_models.jev.key"]


# ── The maps reach the settings that the reader receives ─────────────────


def test_the_maps_reach_the_effective_settings(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs.compose_settings import settings_to_effective

    write_config(
        folder,
        {
            "decision_models": {"clef-local": CLEF_LOCAL},
            "document_routers": {"handwriting": HANDWRITING},
            "document_router": "handwriting",
        },
    )

    effective = settings_to_effective(build())

    assert effective.document_router == "handwriting"
    assert effective.document_routers["handwriting"].threshold == 0.172
    assert effective.decision_models["clef-local"].kind == "llamacpp"


def test_effective_settings_default_to_no_router() -> None:
    from omrs.core.settings import EffectiveSettings

    effective = EffectiveSettings()
    assert (effective.document_router, dict(effective.document_routers)) == ("", {})
    assert dict(effective.decision_models) == {}


def test_entries_cannot_be_changed_in_place(folder: Path) -> None:
    write_config(folder, {"document_routers": {"handwriting": HANDWRITING}})
    router = build().document_routers["handwriting"]
    with pytest.raises(ValueError):
        router.threshold = 0.9  # type: ignore[misc]
