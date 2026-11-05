"""Page writes of the router maps (document-reading-routers, task 1.2).

The Settings page writes ``decision_models`` and ``document_routers`` entries
through the safe writer: comments stay, the revision check runs, a literal key
is refused, and an entry that a router or a saved profile names cannot be
deleted. Only ``omrs web`` writes the maps; the CLI reads them.

Every test points ``OMRS_CONFIG_DIR`` at a temporary folder. Keys are fake.
"""

from __future__ import annotations

import ast
import json
import pathlib
from pathlib import Path
from typing import Any

import pytest

from omrs.config import provenance
from omrs.config.settings_file import file_revision, read_settings_file
from omrs.config.settings_file_write import (
    SettingsFileConflict,
    SettingsFileRefused,
    write_settings,
)
from omrs.config.settings_maps_write import write_map_entries
from omrs.config.user_config import parse_jsonc

LITERAL_KEY = "sk-fake-literal-key-0000"
SRC = Path(__file__).resolve().parents[2] / "src" / "omrs"

CLEF_LOCAL: dict[str, Any] = {
    "kind": "llamacpp",
    "address": "http://127.0.0.1:8090",
    "model": "clef-flash-q8_0",
    "images": True,
}
JEV: dict[str, Any] = {
    "kind": "typesafe",
    "address": "https://api.typesafe.example",
    "model": "jev",
    "key": "env://TYPESAFE_API_KEY",
}
HANDWRITING: dict[str, Any] = {
    "model": "clef-local",
    "question": "Is the text layer of this page usable?",
    "threshold": 0.172,
    "images": True,
}
START = (
    "// my settings\n{\n"
    '  "community_seed": 3, // keep me\n'
    '  "decision_models": {\n'
    "    // the local arm\n"
    f'    "clef-local": {json.dumps(CLEF_LOCAL)}\n'
    "  },\n"
    f'  "document_routers": {{ "handwriting": {json.dumps(HANDWRITING)} }}\n'
    "}\n"
)


@pytest.fixture
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "cfg" / "omrs"
    root.mkdir(parents=True, mode=0o700)
    (root / "omrs.jsonc").write_text(START, encoding="utf-8")
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def text(folder: Path) -> str:
    return (folder / "omrs.jsonc").read_text(encoding="utf-8")


def data(folder: Path) -> dict[str, Any]:
    return parse_jsonc(text(folder))


def no_profiles(_router: str) -> list[str]:
    return []


# ── Saves keep comments and use the revision check ───────────────────────


def test_saving_a_router_keeps_comments_and_loads_back(folder: Path) -> None:
    result = write_map_entries(
        {"document_routers.scans": {**HANDWRITING, "threshold": 0.3}},
        revision=file_revision(folder),
    )

    assert result.changed
    assert "// my settings" in text(folder)
    assert "// keep me" in text(folder)
    assert "// the local arm" in text(folder)
    loaded = read_settings_file().maps["document_routers"]
    assert sorted(loaded) == ["handwriting", "scans"]
    assert loaded["scans"].threshold == 0.3
    assert result.revision == file_revision(folder)


def test_saving_a_decision_model_writes_the_reference_and_not_a_key(folder: Path) -> None:
    write_map_entries({"decision_models.jev": JEV}, revision=file_revision(folder))
    assert data(folder)["decision_models"]["jev"]["key"] == "env://TYPESAFE_API_KEY"
    assert "clef-local" in data(folder)["decision_models"]


def test_a_stale_revision_is_refused_and_nothing_is_written(folder: Path) -> None:
    before = text(folder)
    with pytest.raises(SettingsFileConflict):
        write_map_entries({"document_routers.scans": HANDWRITING}, revision="0" * 64)
    assert text(folder) == before


def test_a_new_file_gets_the_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "fresh"
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    write_map_entries({"decision_models.clef-local": CLEF_LOCAL}, revision="absent")
    assert read_settings_file().maps["decision_models"]["clef-local"].model == "clef-flash-q8_0"


# ── Refused entries ──────────────────────────────────────────────────────


def test_a_literal_key_is_refused_and_not_echoed(folder: Path) -> None:
    before = text(folder)
    with pytest.raises(SettingsFileRefused) as caught:
        write_map_entries({"decision_models.jev": {**JEV, "key": LITERAL_KEY}}, revision=None)
    assert "decision_models.jev.key" in str(caught.value)
    assert LITERAL_KEY not in str(caught.value)
    assert text(folder) == before


@pytest.mark.parametrize(
    ("change", "named"),
    [
        ({"document_routers.scans": {**HANDWRITING, "threshold": "high"}}, "threshold"),
        ({"document_routers.scans": {**HANDWRITING, "colour": "red"}}, "colour"),
        ({"document_routers.scans": "clef"}, "document_routers.scans"),
        ({"decision_models.m": {**CLEF_LOCAL, "address": "ftp://x"}}, "address"),
        ({"document_routers.none": HANDWRITING}, "document_routers.none"),
        ({"document_routers.a.b": HANDWRITING}, "document_routers.a.b"),
        ({"document_routers": HANDWRITING}, "document_routers"),
        ({"community_seed.x": HANDWRITING}, "community_seed.x"),
    ],
    ids=["text", "unknown", "not-object", "address", "none", "dotted", "no-name", "not-a-map"],
)
def test_a_broken_change_is_refused_naming_it(
    folder: Path, change: dict[str, Any], named: str
) -> None:
    before = text(folder)
    with pytest.raises(SettingsFileRefused, match=named.replace(".", r"\.")):
        write_map_entries(change, revision=None)
    assert text(folder) == before


def test_the_general_writer_refuses_the_maps(folder: Path) -> None:
    for key in ("decision_models", "document_routers", "document_routers.scans"):
        with pytest.raises(SettingsFileRefused):
            write_settings({key: HANDWRITING}, revision=None)


def test_the_general_writer_saves_the_host_router(folder: Path) -> None:
    write_settings({"document_router": "handwriting"}, revision=None)
    assert data(folder)["document_router"] == "handwriting"
    assert "// keep me" in text(folder)
    write_settings({"document_router": None}, revision=None)
    assert "document_router" not in data(folder)


@pytest.mark.parametrize("value", ["has.dot", "a b", 5, True, "   "])
def test_the_general_writer_refuses_a_bad_host_router_name(folder: Path, value: Any) -> None:
    before = text(folder)
    with pytest.raises(SettingsFileRefused, match="document_router"):
        write_settings({"document_router": value}, revision=None)
    assert text(folder) == before


# ── Entries in use cannot be deleted ─────────────────────────────────────


def test_deleting_a_model_that_a_router_names_is_refused_naming_the_router(folder: Path) -> None:
    before = text(folder)
    with pytest.raises(SettingsFileRefused, match="handwriting"):
        write_map_entries({"decision_models.clef-local": None}, revision=None)
    assert text(folder) == before


def test_moving_the_last_router_away_frees_the_model(folder: Path) -> None:
    write_map_entries(
        {"document_routers.handwriting": None, "decision_models.clef-local": None},
        revision=None,
        profiles_naming=no_profiles,
    )
    assert data(folder).get("decision_models") == {}  # its comment keeps the object
    assert "document_routers" not in data(folder)
    assert data(folder)["community_seed"] == 3


def test_deleting_a_router_that_a_saved_profile_names_is_refused(folder: Path) -> None:
    asked: list[str] = []

    def profiles_naming(router: str) -> list[str]:
        asked.append(router)
        return ["Scanned theses"] if router == "handwriting" else []

    before = text(folder)
    with pytest.raises(SettingsFileRefused, match="Scanned theses"):
        write_map_entries(
            {"document_routers.handwriting": None},
            revision=None,
            profiles_naming=profiles_naming,
        )
    assert asked == ["handwriting"]
    assert text(folder) == before


def test_a_rename_is_refused_while_a_saved_profile_names_the_router(folder: Path) -> None:
    with pytest.raises(SettingsFileRefused, match="Scanned theses"):
        write_map_entries(
            {"document_routers.handwriting": None, "document_routers.scans": HANDWRITING},
            revision=None,
            profiles_naming=lambda name: ["Scanned theses"],
        )


def test_a_router_delete_needs_the_profile_check(folder: Path) -> None:
    with pytest.raises(SettingsFileRefused, match="profile"):
        write_map_entries({"document_routers.handwriting": None}, revision=None)


def test_deleting_the_host_router_is_refused(folder: Path) -> None:
    write_settings({"document_router": "handwriting"}, revision=None)
    before = text(folder)
    with pytest.raises(SettingsFileRefused, match="document_router"):
        write_map_entries(
            {"document_routers.handwriting": None}, revision=None, profiles_naming=no_profiles
        )
    assert text(folder) == before


def test_deleting_a_free_router_removes_it_and_keeps_the_rest(folder: Path) -> None:
    write_map_entries(
        {"document_routers.handwriting": None}, revision=None, profiles_naming=no_profiles
    )
    assert "document_routers" not in data(folder)
    assert "clef-local" in data(folder)["decision_models"]
    assert "// the local arm" in text(folder)


# ── Only omrs web writes the maps (spec: CLI reads a router) ─────────────


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("folder_name", ["transports/cli", "transports/mcp", "daemon"])
def test_no_reading_process_imports_a_settings_writer(folder_name: str) -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in sorted((SRC / folder_name).rglob("*.py"))
        if any(
            name.endswith(("settings_maps_write", "write_settings", "write_map_entries"))
            for name in _imported_modules(path)
        )
    ]
    assert offenders == []


def test_cli_ingest_uses_the_router_and_opens_the_file_read_only(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from omrs.transports.cli import app
    from omrs.transports.cli import ingest as cli_ingest

    monkeypatch.setenv("DOCUMENT_ROUTER", "handwriting")
    monkeypatch.setenv("HOME", str(tmp_path))  # no default workspace
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    monkeypatch.setattr("omrs.config._settings", None)
    monkeypatch.chdir(tmp_path)
    config = folder / "omrs.jsonc"
    before = (text(folder), config.stat().st_mtime_ns)
    modes: list[str] = []
    real_open = pathlib.Path.open

    def recording_open(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if self.name.startswith("omrs.jsonc"):
            modes.append(mode)
        return real_open(self, mode, *args, **kwargs)

    seen: dict[str, Any] = {}

    def fake_run(path: str, kwargs: dict[str, Any], json_output: bool, fn: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"status": "success", "files_indexed": 0, "chunks_created": 0, "warnings": []}

    monkeypatch.setattr(pathlib.Path, "open", recording_open)
    monkeypatch.setattr(cli_ingest, "_run_ingest", fake_run)

    result = CliRunner().invoke(app, ["ingest", str(tmp_path), "--json"])

    monkeypatch.setattr("omrs.config._settings", None)
    assert result.exit_code == 0, result.output
    effective = seen["effective_settings"]
    assert effective.document_router == "handwriting"
    assert effective.document_routers["handwriting"].model == "clef-local"
    assert effective.decision_models["clef-local"].kind == "llamacpp"
    assert modes and all(mode in ("r", "rb") for mode in modes)
    assert (text(folder), config.stat().st_mtime_ns) == before
    assert sorted(p.name for p in folder.iterdir()) == ["omrs.jsonc"]
