"""``RuntimeSpec`` and the argument builders of the shared runtime manager.

Design D2: Chat and embeddings keep the fixed port of their URL; an OCR
runtime gets a free port at start time. No argument list ever holds
``--sleep-idle-seconds`` (llama.cpp issue #29689).
"""

from __future__ import annotations

import json

import pytest

from omrs.integrations.llamacpp_runtime.spec import (
    DeclaredFile,
    RuntimeSpec,
    chat_spec,
    embeddings_spec,
    ocr_spec,
)

BINARY = "/b/llama-server"


def test_chat_argument_list_is_exact() -> None:
    spec = chat_spec(
        mode="managed", binary=BINARY, model="/m/q.gguf", port=8081, window=16384, kind="file"
    )
    assert list(spec.argv) == [
        BINARY,
        "-m",
        "/m/q.gguf",
        "--host",
        "127.0.0.1",
        "--port",
        "8081",
        "-c",
        "16384",
    ]
    assert spec.id == "chat"
    assert spec.role == "chat"
    assert spec.port_policy == "fixed"
    assert spec.port == 8081


def test_embeddings_argument_list_matches_the_spec_scenario() -> None:
    spec = embeddings_spec(mode="managed", binary=BINARY, model="/m/e.gguf", port=8080, kind="file")
    assert list(spec.argv) == [
        BINARY,
        "-m",
        "/m/e.gguf",
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
        "--embedding",
    ]
    assert spec.id == "embeddings"
    assert spec.role == "embeddings"


def test_no_argument_list_holds_the_idle_sleep_flag() -> None:
    chat = chat_spec(
        mode="managed", binary=BINARY, model="/m/q.gguf", port=8081, window=2048, kind="file"
    )
    embed = embeddings_spec(
        mode="managed", binary=BINARY, model="/m/e.gguf", port=8080, kind="file"
    )
    for spec in (chat, embed):
        assert "--sleep-idle-seconds" not in spec.argv
        assert "--sleep-idle-seconds" not in spec.launch_argv(spec.port or 0)


def test_a_hugging_face_model_uses_hf() -> None:
    spec = chat_spec(mode="managed", binary=BINARY, model="org/model:tag", port=8081, window=16384)
    assert spec.argv[1:3] == ("-hf", "org/model:tag")


def test_external_mode_keeps_the_url_and_no_port_launch() -> None:
    spec = chat_spec(
        mode="external", binary=BINARY, model="/m/q.gguf", port=8081, window=16384, kind="file"
    )
    spec = spec.with_url_base("http://127.0.0.1:8081/v1")
    assert spec.mode == "external"
    assert spec.url_base == "http://127.0.0.1:8081/v1"


def test_slot_count_comes_from_np() -> None:
    chat = chat_spec(
        mode="managed", binary=BINARY, model="/m/q.gguf", port=8081, window=16384, kind="file"
    )
    assert chat.slots == 0
    assert chat.one_slot is False
    ocr = ocr_spec(
        engine_folder="dots-mocr-llamacpp",
        binary=BINARY,
        build=11941,
        flags=("--temp", "0", "-np", "1"),
        files=(DeclaredFile(flag="-m", path="/m/dots.gguf", sha256="0" * 64),),
    )
    assert ocr.slots == 1
    assert ocr.one_slot is True
    assert ocr.id == "ocr-dots-mocr-llamacpp"
    assert ocr.role == "ocr"
    assert ocr.port_policy == "free"


def test_launch_argv_replaces_the_free_port() -> None:
    ocr = ocr_spec(
        engine_folder="dots-mocr-llamacpp",
        binary=BINARY,
        build=11941,
        flags=("-c", "24576", "-np", "1"),
        files=(DeclaredFile(flag="-m", path="/m/dots.gguf", sha256="0" * 64),),
    )
    assert ocr.port == 0
    launched = ocr.launch_argv(41234)
    assert launched[launched.index("--port") + 1] == "41234"
    assert "--host" in launched and "127.0.0.1" in launched
    assert launched.count("--port") == 1


def test_digest_is_stable_for_a_free_port_and_strict_for_a_fixed_port() -> None:
    chat = chat_spec(
        mode="managed", binary=BINARY, model="/m/q.gguf", port=8081, window=16384, kind="file"
    )
    other_port = chat_spec(
        mode="managed", binary=BINARY, model="/m/q.gguf", port=8082, window=16384, kind="file"
    )
    other_model = chat_spec(
        mode="managed", binary=BINARY, model="/m/q2.gguf", port=8081, window=16384, kind="file"
    )
    assert chat.digest == chat.digest
    assert chat.digest != other_port.digest
    assert chat.digest != other_model.digest
    ocr_a = ocr_spec(
        engine_folder="dots-mocr-llamacpp",
        binary=BINARY,
        build=11941,
        flags=("-np", "1"),
        files=(DeclaredFile(flag="-m", path="/m/dots.gguf", sha256="0" * 64),),
    )
    restarted = ocr_a.with_launch_port(41000)
    assert restarted.digest == ocr_a.digest, "a free-port runtime keeps its digest"


def test_json_round_trip() -> None:
    spec = ocr_spec(
        engine_folder="dots-mocr-llamacpp",
        binary=BINARY,
        build=11941,
        flags=("--temp", "0"),
        files=(
            DeclaredFile(flag="-m", path="/m/dots.gguf", sha256="a" * 64),
            DeclaredFile(flag="--mmproj", path="/m/mmproj.gguf", sha256="b" * 64),
        ),
    )
    data = spec.to_dict()
    assert json.loads(json.dumps(data)) == data  # JSON-safe for the client process
    assert RuntimeSpec.from_dict(data) == spec


def test_a_bad_runtime_id_is_refused() -> None:
    with pytest.raises(ValueError):
        RuntimeSpec(
            id="../escape",
            role="chat",
            mode="managed",
            binary=BINARY,
            argv=(BINARY,),
        )


def test_an_argument_list_with_the_idle_sleep_flag_is_refused() -> None:
    with pytest.raises(ValueError):
        RuntimeSpec(
            id="chat",
            role="chat",
            mode="managed",
            binary=BINARY,
            argv=(BINARY, "--sleep-idle-seconds", "300"),
        )
