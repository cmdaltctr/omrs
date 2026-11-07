"""The llama.cpp router model list ``llamacpp_models`` (one-llamacpp-router, task 2.2).

The list is a file-only named map in ``omrs.jsonc``, with the shipped list of design
D11 as the code default. These tests cover the entry rules, the preset allow-list
and its types, and the reading of the file. They check values only: the
``models.ini`` writer belongs to task 3.3.

Every test points ``OMRS_CONFIG_DIR`` at a temporary folder. Paths and names here
are fake constants.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from omrs.config import Settings, provenance
from omrs.config.llamacpp_models import (
    CLASSIFY_MODEL,
    EMBED_MODEL,
    MODEL_PATTERN,
    SHIPPED_MODELS,
    check_model_entry,
    file_problem,
)
from omrs.config.settings_file import KIND_INVALID, KIND_UNKNOWN, read_settings_file
from omrs.config.settings_file_write import read_only_reason

#: A value that must never appear in a rule text or a problem list.
SENTINEL = "SENTINEL-VALUE-0000"
QWEN = "Qwen/Qwen3-4B-GGUF:Q8_0"


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv("LLAMACPP_MODELS", raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
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


def entry(**fields: Any) -> dict[str, Any]:
    return {"model": QWEN, **fields}


def broken_fields(data: dict[str, Any]) -> set[str]:
    loaded, problems = check_model_entry(data)
    assert loaded is None
    return {problem.field for problem in problems}


# ── The shipped list (design D11) ────────────────────────────────────────


def test_the_shipped_list_is_the_default() -> None:
    models = build().llamacpp_models
    assert list(models) == ["qwen3-embedding-4b", "qwen3-4b"]
    embeddings, text = models["qwen3-embedding-4b"], models["qwen3-4b"]
    assert embeddings.model == "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0"
    assert embeddings.preset == {
        "embeddings": True,
        "pooling": "last",
        "embd-normalize": 2,
        "ctx-size": 8192,
        "batch-size": 8192,
        "ubatch-size": 8192,
        "parallel": 1,
        "kv-unified": False,
    }
    assert text.model == "Qwen/Qwen3-4B-GGUF:Q8_0"
    assert text.preset == {"ctx-size": 32768, "parallel": 2}
    assert all(item.file is None and item.projector is None for item in models.values())


def test_the_role_settings_default_to_the_shipped_models() -> None:
    settings = build()
    assert settings.llamacpp_embed_model == EMBED_MODEL == "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0"
    assert settings.llamacpp_chat_model == CLASSIFY_MODEL == "Qwen/Qwen3-4B-GGUF:Q8_0"
    assert {item.model for item in SHIPPED_MODELS.values()} == {EMBED_MODEL, CLASSIFY_MODEL}


def test_the_shipped_entries_pass_their_own_rules() -> None:
    for item in SHIPPED_MODELS.values():
        loaded, problems = check_model_entry(item.model_dump(exclude_none=True))
        assert (loaded, problems) == (item, [])


# ── The list lives in omrs.jsonc ─────────────────────────────────────────


def test_the_environment_cannot_set_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMACPP_MODELS", json.dumps({"x": entry()}))
    assert list(build().llamacpp_models) == ["qwen3-embedding-4b", "qwen3-4b"]


def test_a_user_map_replaces_the_shipped_list(folder: Path) -> None:
    write_config(folder, {"llamacpp_models": {"mine": entry(file="/m/Qwen3-4B-Q8_0.gguf")}})
    settings = build()
    assert list(settings.llamacpp_models) == ["mine"]
    assert settings.llamacpp_models["mine"].file == "/m/Qwen3-4B-Q8_0.gguf"
    assert settings.setting_sources["llamacpp_models.mine"] == "config-file"
    assert read_settings_file().problems == ()


def test_an_empty_user_map_still_replaces_the_shipped_list(folder: Path) -> None:
    write_config(folder, {"llamacpp_models": {}})
    assert dict(build().llamacpp_models) == {}


def test_a_map_that_is_not_an_object_keeps_the_shipped_list(folder: Path) -> None:
    write_config(folder, {"llamacpp_models": [entry()]})
    assert [(p.kind, p.key) for p in read_settings_file().problems] == [
        (KIND_INVALID, "llamacpp_models")
    ]
    assert list(build().llamacpp_models) == ["qwen3-embedding-4b", "qwen3-4b"]


def test_reading_the_list_never_writes_the_file(folder: Path) -> None:
    write_config(folder, {"llamacpp_models": {"mine": entry()}})
    path = folder / "omrs.jsonc"
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    build()
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert list(folder.iterdir()) == [path]


def test_the_configuration_save_never_writes_the_list() -> None:
    assert read_only_reason("llamacpp_models") is not None


def test_a_broken_entry_is_ignored_and_the_others_load(folder: Path) -> None:
    write_config(
        folder,
        {"llamacpp_models": {"good": entry(), "bad": {"model": "Qwen/Qwen3-4B-GGUF"}}},
    )
    assert list(build().llamacpp_models) == ["good"]
    assert [(kind, key) for kind, key, _ in problems_at("llamacpp_models")] == [
        (KIND_INVALID, "llamacpp_models.bad.model")
    ]


# ── Entry rules (spec: Entry files follow fixed rules) ───────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Qwen/Qwen3-4B-GGUF",
        "Qwen3-4B:Q8_0",
        "-Qwen/Qwen3-4B-GGUF:Q8_0",
        "--help/x:Q8_0",
        "Qwen/Qwen3-4B-GGUF:",
        "Qwen/Qwen3 4B:Q8_0",
        "",
        "/m/Qwen3-4B-Q8_0.gguf",
    ],
)
def test_a_model_without_the_hugging_face_shape_and_tag_is_refused(name: str) -> None:
    assert broken_fields({"model": name}) == {"model"}


def test_a_model_name_is_required() -> None:
    assert broken_fields({"file": "/m/q.gguf"}) == {"model"}


@pytest.mark.parametrize(
    "path",
    [
        "models/q.gguf",
        "./q.gguf",
        "~/q.gguf",
        "/m/q.bin",
        "/m/q.gguf.part",
        "/m/Qwen3-mmproj-F16.gguf",
        "/m/MMPROJ.gguf",
        "/m/\x00q.gguf",
        "",
    ],
)
def test_a_bad_model_file_is_refused(path: str) -> None:
    assert broken_fields(entry(file=path)) == {"file"}


@pytest.mark.parametrize("path", ["mmproj.gguf", "/m/mmproj.bin", "/m/proj", "rel.gguf"])
def test_a_bad_projector_is_refused(path: str) -> None:
    assert broken_fields(entry(projector=path)) == {"projector"}


def test_a_projector_may_have_mmproj_in_its_name() -> None:
    loaded, problems = check_model_entry(entry(projector="/m/mmproj-F16.gguf"))
    assert problems == []
    assert loaded is not None and loaded.projector == "/m/mmproj-F16.gguf"


def test_a_missing_file_is_not_a_read_problem(folder: Path) -> None:
    """A file that is gone fails its entry at launch, not at read (spec: Missing file at start)."""
    write_config(folder, {"llamacpp_models": {"mine": entry(file="/gone/Qwen3-4B-Q8_0.gguf")}})
    assert list(build().llamacpp_models) == ["mine"]
    assert read_settings_file().problems == ()


def test_the_disk_check_wants_a_regular_file(tmp_path: Path) -> None:
    good = tmp_path / "Qwen3-4B-Q8_0.gguf"
    good.write_bytes(b"GGUF")
    assert file_problem(str(good), exists=True) is None
    assert file_problem(str(tmp_path / "gone.gguf"), exists=True) is not None
    folder = tmp_path / "dir.gguf"
    folder.mkdir()
    assert file_problem(str(folder), exists=True) is not None
    assert file_problem(str(tmp_path / "gone.gguf")) is None  # no disk check asked


@pytest.mark.parametrize("field", ["sha256", "projector_sha256"])
@pytest.mark.parametrize("value", ["abc", "G" * 64, "A" * 64, "a" * 63, "a" * 65])
def test_a_bad_checksum_is_refused(field: str, value: str) -> None:
    assert broken_fields(entry(**{field: value})) == {field}


def test_a_good_checksum_is_kept() -> None:
    loaded, problems = check_model_entry(entry(sha256="a" * 64, projector_sha256="0" * 64))
    assert problems == [] and loaded is not None and loaded.sha256 == "a" * 64


def test_an_unknown_entry_field_is_listed_as_unknown() -> None:
    loaded, problems = check_model_entry(entry(context=4096))
    assert loaded is None
    assert [(p.kind, p.field) for p in problems] == [(KIND_UNKNOWN, "context")]


@pytest.mark.parametrize(
    ("field", "value"),
    [("file", 4), ("projector", ["/m/p.gguf"]), ("sha256", 1), ("model", 7), ("preset", [])],
)
def test_a_field_of_the_wrong_type_is_refused(field: str, value: object) -> None:
    assert field in broken_fields(entry(**{field: value}))


@pytest.mark.parametrize("name", ["", "A", "has space", "x" * 41, "under_score", "é"])
def test_an_entry_id_outside_the_pattern_is_ignored(folder: Path, name: str) -> None:
    write_config(folder, {"llamacpp_models": {name: entry()}})
    assert dict(build().llamacpp_models) == {}
    assert [kind for kind, _, _ in problems_at("llamacpp_models")] == [KIND_INVALID]


def test_an_entry_id_of_forty_characters_is_accepted(folder: Path) -> None:
    write_config(folder, {"llamacpp_models": {"a" * 40: entry(), "0-9": entry(model="a/b:c")}})
    assert list(build().llamacpp_models) == ["a" * 40, "0-9"]


def test_an_entry_that_is_not_an_object_is_ignored(folder: Path) -> None:
    write_config(folder, {"llamacpp_models": {"x": "not an object"}})
    assert dict(build().llamacpp_models) == {}
    assert [kind for kind, _, _ in problems_at("llamacpp_models")] == [KIND_INVALID]


def test_a_model_may_be_listed_once(folder: Path) -> None:
    write_config(folder, {"llamacpp_models": {"first": entry(), "second": entry()}})
    assert list(build().llamacpp_models) == ["first"]
    assert [(kind, key) for kind, key, _ in problems_at("llamacpp_models")] == [
        (KIND_INVALID, "llamacpp_models.second.model")
    ]


def test_the_model_pattern_matches_the_launch_rule() -> None:
    """``config/`` cannot import ``integrations/``, so this pins the copy to the launch rule."""
    from omrs.integrations.llamacpp_runtime.rules import _HF_ID

    tag = "[A-Za-z0-9._-]{1,64}"
    assert _HF_ID.pattern.replace(f"(:{tag})?", f":{tag}") == MODEL_PATTERN.pattern


def test_no_rule_text_holds_a_value() -> None:
    data = entry(file=SENTINEL, projector=SENTINEL, sha256=SENTINEL, preset={"bad-key": SENTINEL})
    data["model"] = SENTINEL
    loaded, problems = check_model_entry(data)
    assert loaded is None and problems
    assert all(
        SENTINEL not in problem.rule and SENTINEL not in problem.field for problem in problems
    )
