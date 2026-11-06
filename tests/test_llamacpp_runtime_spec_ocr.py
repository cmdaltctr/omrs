"""More ``RuntimeSpec`` rules: the OCR argument list, slot count and model rule."""

from __future__ import annotations

from omrs.integrations.llamacpp_runtime.spec import (
    DeclaredFile,
    RuntimeSpec,
    ocr_spec,
)

BINARY = "/b/llama-server"


def _spec(argv: tuple[str, ...]) -> RuntimeSpec:
    return RuntimeSpec(id="router", role="router", mode="managed", binary=BINARY, argv=argv)


def test_the_ocr_argument_list_is_exact() -> None:
    spec = ocr_spec(
        engine_folder="dots-mocr-llamacpp",
        binary=BINARY,
        build=11941,
        flags=("--temp", "0", "-np", "1"),
        files=(
            DeclaredFile(flag="-m", path="/c/dots.gguf", sha256="a" * 64),
            DeclaredFile(flag="--mmproj", path="/c/mmproj.gguf", sha256="b" * 64),
        ),
    )
    assert spec.argv == (
        BINARY,
        "--temp",
        "0",
        "-np",
        "1",
        "-m",
        "/c/dots.gguf",
        "--mmproj",
        "/c/mmproj.gguf",
        "--host",
        "127.0.0.1",
        "--port",
        "0",
    )
    assert spec.launch_argv(41000)[-2:] == ("--port", "41000")
    assert spec.id == "ocr-dots-mocr-llamacpp"


def test_only_np_1_makes_a_one_slot_runtime() -> None:
    assert _spec((BINARY, "-np", "1")).one_slot is True
    assert _spec((BINARY, "-np", "2")).one_slot is False
    assert _spec((BINARY, "-np", "4")).one_slot is False
    assert _spec((BINARY,)).one_slot is False
