"""The ``models.ini`` writer (task 3.3; spec ``llamacpp-router``, design D4).

Golden-file tests: one section per usable entry named by ``model``, then
``model = <file>`` and ``mmproj = <projector>``, then the allow-listed keys in
the fixed key order. Booleans are written exactly ``true`` or ``false``;
``embeddings`` only when true. No ``[*]`` section. Entries with no file or a
failed check are left out with a reason.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from omrs.integrations.llamacpp_runtime.hashes import HashCache
from omrs.integrations.llamacpp_runtime.preset_writer import (
    format_section,
    join_sections,
    plan_preset,
    replace_section,
    split_sections,
    write_preset,
)
from omrs.integrations.llamacpp_runtime.router_spec import PRESET_FILE

EMBED = "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0"
CHAT = "Qwen/Qwen3-4B-GGUF:Q8_0"
CLEF = "Clef/Flash-GGUF:Q8_0"


@dataclass
class Entry:
    """Plain entry data, the shape of ``config.llamacpp_models.LlamaCppModelEntry``."""

    model: str
    file: str | None = None
    projector: str | None = None
    sha256: str | None = None
    projector_sha256: str | None = None
    preset: dict[str, Any] = field(default_factory=dict)


EMBED_PRESET = {
    "embeddings": True,
    "pooling": "last",
    "embd-normalize": 2,
    "ctx-size": 8192,
    "batch-size": 8192,
    "ubatch-size": 8192,
    "parallel": 1,
    "kv-unified": False,
}

GOLDEN_EMBED = f"""\
[{EMBED}]
model = /m/Qwen3-Embedding-4B-Q8_0.gguf
ctx-size = 8192
batch-size = 8192
ubatch-size = 8192
parallel = 1
embeddings = true
pooling = last
embd-normalize = 2
kv-unified = false
"""

GOLDEN_CLEF = f"""\
[{CLEF}]
model = /m/Clef-Flash-Q8_0.gguf
mmproj = /m/mmproj-Clef-Flash-f16.gguf
parallel = 1
flash-attn = auto
n-gpu-layers = all
cache-type-k = q8_0
cache-prompt = true
image-max-tokens = 1024
"""


def _file(folder: Path, name: str, data: bytes = b"GGUF data") -> str:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(path)


def _cache(tmp_path: Path) -> HashCache:
    return HashCache(tmp_path / "state" / "hashes.json")


def test_golden_embedding_section() -> None:
    entry = Entry(EMBED, file="/m/Qwen3-Embedding-4B-Q8_0.gguf", preset=dict(EMBED_PRESET))
    assert format_section(entry) == GOLDEN_EMBED


def test_golden_section_with_projector_and_fixed_key_order() -> None:
    # Keys given in a scrambled order come out in the allow-list order.
    preset = {
        "image-max-tokens": 1024,
        "cache-prompt": True,
        "cache-type-k": "q8_0",
        "n-gpu-layers": "all",
        "flash-attn": "auto",
        "parallel": 1,
    }
    entry = Entry(
        CLEF,
        file="/m/Clef-Flash-Q8_0.gguf",
        projector="/m/mmproj-Clef-Flash-f16.gguf",
        preset=preset,
    )
    assert format_section(entry) == GOLDEN_CLEF


def test_spec_scenario_section_name_and_model_path() -> None:
    entry = Entry(CHAT, file="/m/Qwen3-4B-Q8_0.gguf", preset={"ctx-size": 32768, "parallel": 2})
    assert format_section(entry) == (
        f"[{CHAT}]\nmodel = /m/Qwen3-4B-Q8_0.gguf\nctx-size = 32768\nparallel = 2\n"
    )


def test_boolean_written_exactly_and_never_negated() -> None:
    entry = Entry(CHAT, file="/m/q.gguf", preset={"kv-unified": False, "cache-prompt": False})
    text = format_section(entry)
    assert "kv-unified = false\n" in text
    assert "cache-prompt = false\n" in text
    assert "no-kv-unified" not in text
    assert "no-cache-prompt" not in text


def test_plan_writes_usable_entries_and_no_star_section(tmp_path: Path) -> None:
    embed = Entry(EMBED, file=_file(tmp_path, "e.gguf"), preset=dict(EMBED_PRESET))
    chat = Entry(CHAT, file=_file(tmp_path, "c.gguf"), preset={"ctx-size": 32768})
    plan = plan_preset([embed, chat], hashes=_cache(tmp_path))
    assert plan.text == format_section(embed) + "\n" + format_section(chat)
    assert "[*]" not in plan.text
    assert [o.state for o in plan.outcomes] == ["listed", "listed"]
    assert plan.outcome(EMBED).note == "File not checked"  # type: ignore[union-attr]


def test_entry_with_no_file_is_left_out_as_not_downloaded(tmp_path: Path) -> None:
    chat = Entry(CHAT, file=_file(tmp_path, "c.gguf"))
    plan = plan_preset([Entry(EMBED, preset=dict(EMBED_PRESET)), chat], hashes=_cache(tmp_path))
    outcome = plan.outcome(EMBED)
    assert outcome is not None
    assert (outcome.state, outcome.reason, outcome.section) == ("not-downloaded", None, "")
    assert f"[{EMBED}]" not in plan.text
    assert f"[{CHAT}]" in plan.text


def test_missing_file_fails_that_entry_only(tmp_path: Path) -> None:
    """Spec scenario "Missing file at start": ``model-invalid``, the other entry usable."""
    gone = Entry(EMBED, file=str(tmp_path / "gone.gguf"), preset=dict(EMBED_PRESET))
    chat = Entry(CHAT, file=_file(tmp_path, "c.gguf"))
    plan = plan_preset([gone, chat], hashes=_cache(tmp_path))
    assert (plan.outcome(EMBED).state, plan.outcome(EMBED).reason) == (  # type: ignore[union-attr]
        "failed",
        "model-invalid",
    )
    assert plan.outcome(CHAT).state == "listed"  # type: ignore[union-attr]
    assert f"[{EMBED}]" not in plan.text


@pytest.mark.parametrize(
    "key", ["sleep-idle-seconds", "api-key", "host", "port", "connect", "connect-code"]
)
def test_reserved_key_never_written(tmp_path: Path, key: str) -> None:
    entry = Entry(CHAT, file=_file(tmp_path, "c.gguf"), preset={"ctx-size": 4096, key: "x"})
    plan = plan_preset([entry], hashes=_cache(tmp_path))
    outcome = plan.outcome(CHAT)
    assert outcome is not None
    assert (outcome.state, outcome.reason) == ("failed", "preset-invalid")
    assert key not in plan.text
    with pytest.raises(ValueError, match="allow-list"):
        format_section(entry)


@pytest.mark.parametrize(
    "preset",
    [
        {"pooling": "last --api-key x"},
        {"cache-prompt": "maybe"},
        {"cache-prompt": 1},
        {"embeddings": False},
        {"ctx-size": 100},
    ],
)
def test_bad_values_never_written(tmp_path: Path, preset: dict[str, Any]) -> None:
    entry = Entry(CHAT, file=_file(tmp_path, "c.gguf"), preset=preset)
    plan = plan_preset([entry], hashes=_cache(tmp_path))
    assert plan.outcome(CHAT).reason == "preset-invalid"  # type: ignore[union-attr]
    assert plan.text == ""


@pytest.mark.parametrize(
    "name", ["bad\nname.gguf", "semi;colon.gguf", "hash#mark.gguf", "mmproj-x.gguf"]
)
def test_file_paths_that_would_break_the_ini_are_refused(tmp_path: Path, name: str) -> None:
    entry = Entry(CHAT, file=_file(tmp_path, name))
    plan = plan_preset([entry], hashes=_cache(tmp_path))
    assert plan.outcome(CHAT).reason == "model-invalid"  # type: ignore[union-attr]
    assert plan.text == ""


def test_path_with_a_space_reaches_the_file_as_one_value(tmp_path: Path) -> None:
    path = _file(tmp_path, "my models/q 8.gguf")
    plan = plan_preset([Entry(CHAT, file=path)], hashes=_cache(tmp_path))
    assert f"model = {path}\n" in plan.text


def test_write_is_atomic_temp_then_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "router"
    plan = plan_preset([Entry(CHAT, file=_file(tmp_path, "c.gguf"))], hashes=_cache(tmp_path))
    moves: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src: Any, dst: Any) -> None:
        moves.append((Path(src).name, Path(dst).name))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    path = write_preset(folder, plan.text)
    assert path == folder / PRESET_FILE
    assert path.read_text(encoding="utf-8") == plan.text
    assert moves == [(f"{PRESET_FILE}.tmp", PRESET_FILE)]
    assert sorted(p.name for p in folder.iterdir()) == [PRESET_FILE]


def test_replace_one_section_keeps_the_others_byte_identical() -> None:
    embed = format_section(Entry(EMBED, file="/m/e.gguf", preset=dict(EMBED_PRESET)))
    chat = format_section(Entry(CHAT, file="/m/c.gguf", preset={"ctx-size": 8192}))
    text = join_sections([embed, chat])
    new_chat = format_section(Entry(CHAT, file="/m/c.gguf", preset={"ctx-size": 4096}))

    changed = replace_section(text, CHAT, new_chat)

    assert split_sections(changed) == {EMBED: embed, CHAT: new_chat}
    assert replace_section(text, CHAT, None) == embed
    added = replace_section(embed, CHAT, chat)
    assert split_sections(added) == {EMBED: embed, CHAT: chat}
