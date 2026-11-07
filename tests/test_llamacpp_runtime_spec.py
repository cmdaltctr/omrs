"""``RuntimeSpec`` and the argument builders of the shared runtime manager.

Design D2: Chat and embeddings keep the fixed port of their URL; an OCR
runtime gets a free port at start time. No argument list ever holds
``--sleep-idle-seconds`` (llama.cpp issue #29689).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omrs.integrations.llamacpp_runtime.router_spec import external_router_spec, router_spec
from omrs.integrations.llamacpp_runtime.spec import (
    DeclaredFile,
    RuntimeSpec,
    ocr_spec,
)

BINARY = "/b/llama-server"


def test_no_argument_list_holds_the_idle_sleep_flag(tmp_path: Path) -> None:
    spec = router_spec(binary=BINARY, root=tmp_path, port=8080, models_max=4, memory_margin_mib=0)
    assert "--sleep-idle-seconds" not in spec.argv
    assert "--sleep-idle-seconds" not in spec.launch_argv(spec.port or 0)


def test_external_mode_keeps_the_url_and_no_port_launch() -> None:
    spec = external_router_spec("http://127.0.0.1:8081/v1")
    assert spec.mode == "external"
    assert spec.url_base == "http://127.0.0.1:8081/v1"


def test_slot_count_comes_from_np(tmp_path: Path) -> None:
    router = router_spec(binary=BINARY, root=tmp_path, port=8080, models_max=4, memory_margin_mib=0)
    assert router.slots == 0
    assert router.one_slot is False
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


def test_digest_is_stable_for_a_free_port_and_strict_for_a_fixed_port(tmp_path: Path) -> None:
    def router(port: int, models_max: int = 4) -> RuntimeSpec:
        return router_spec(
            binary=BINARY, root=tmp_path, port=port, models_max=models_max, memory_margin_mib=0
        )

    chat = router(8081)
    assert chat.digest == router(8081).digest
    assert chat.digest != router(8082).digest
    assert chat.digest != router(8081, models_max=2).digest
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
            id="router",
            role="router",
            mode="managed",
            binary=BINARY,
            argv=(BINARY, "--sleep-idle-seconds", "300"),
        )
