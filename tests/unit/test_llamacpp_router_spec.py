"""The router runtime spec (task 3.2; spec ``llamacpp-runtimes`` and ``llamacpp-server``).

The router is runtime ``router`` (capability ``llamacpp-router``). Its argument
list is fixed: the preset file, the model limit, the memory margin and a
loopback host and port. The ``chat``, ``embeddings`` and ``decision-*`` ids
retire; ``ocr-*`` stays.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from omrs.integrations.llamacpp_runtime import pins
from omrs.integrations.llamacpp_runtime.router_spec import (
    ROUTER_CAPABILITY,
    ROUTER_ID,
    external_router_spec,
    model_id,
    router_spec,
)
from omrs.integrations.llamacpp_runtime.spec import (
    RUNTIME_ID_RE,
    RuntimeSpec,
)
from omrs.integrations.llamacpp_runtime.state import runtime_dir

BINARY = "/b/llama-server"


def _spec(root: Path, **overrides: object) -> RuntimeSpec:
    values: dict[str, object] = {
        "binary": BINARY,
        "root": root,
        "port": 8080,
        "models_max": 4,
        "memory_margin_mib": 8192,
    }
    values.update(overrides)
    return router_spec(**values)  # type: ignore[arg-type]


def test_exact_arguments(tmp_path: Path) -> None:
    """Spec scenario "Exact arguments": port 8080, limit 4, margin 8,192."""
    spec = _spec(tmp_path)
    assert list(spec.argv) == [
        BINARY,
        "--models-preset",
        f"{tmp_path}/runtimes/router/models.ini",
        "--models-max",
        "4",
        "--models-memory-margin",
        "8192",
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
    ]
    assert spec.launch_argv(8080) == spec.argv


def test_router_identity(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    assert (spec.id, spec.role, spec.mode, spec.port_policy) == (
        "router",
        "router",
        "managed",
        "fixed",
    )
    assert ROUTER_ID == "router"
    assert ROUTER_CAPABILITY == "llamacpp-router"
    assert spec.port == 8080
    assert spec.one_slot is False  # the router's own request.lock is never taken


def test_router_needs_the_pinned_build_floor(tmp_path: Path) -> None:
    """The router refuses a build below b11941 (spec "start checks build")."""
    assert _spec(tmp_path).min_build == pins.LLAMA_BUILD == 11941
    assert _spec(tmp_path).build is None  # a newer build is accepted


def test_the_preset_file_sits_in_the_router_folder(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    preset = spec.argv[spec.argv.index("--models-preset") + 1]
    assert Path(preset) == runtime_dir(tmp_path, "router") / "models.ini"


def test_external_router_starts_nothing() -> None:
    spec = external_router_spec("http://127.0.0.1:9931/v1")
    assert (spec.id, spec.role, spec.mode) == ("router", "router", "external")
    assert spec.argv == ()
    assert spec.url_base == "http://127.0.0.1:9931/v1"


def test_idle_sleep_flag_still_refused(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    with pytest.raises(ValueError, match="idle sleep"):
        replace(spec, argv=(*spec.argv, "--sleep-idle-seconds", "60"))


@pytest.mark.parametrize("runtime_id", ["router", "ocr-dots-mocr-llamacpp", "ocr-a.b_c-d"])
def test_runtime_ids_kept(runtime_id: str) -> None:
    assert RUNTIME_ID_RE.fullmatch(runtime_id)


@pytest.mark.parametrize("runtime_id", ["chat", "embeddings", "decision-clef", "routers", "ocr-"])
def test_retired_runtime_ids_refused(runtime_id: str) -> None:
    """Spec scenario "Old runtime ids gone"."""
    assert RUNTIME_ID_RE.fullmatch(runtime_id) is None
    with pytest.raises(ValueError, match="not a runtime id"):
        RuntimeSpec(id=runtime_id, role="router", mode="external", binary="")


def test_router_digest_is_binary_and_arguments_only(tmp_path: Path) -> None:
    """D8: the router digest covers the binary and the router arguments only."""
    base = _spec(tmp_path)
    assert _spec(tmp_path).digest == base.digest
    assert _spec(tmp_path, models_max=5).digest != base.digest
    assert _spec(tmp_path, memory_margin_mib=0).digest != base.digest
    assert _spec(tmp_path, port=8090).digest != base.digest
    assert _spec(tmp_path, binary="/c/llama-server").digest != base.digest


def test_model_id_is_sixteen_hex_of_sha256() -> None:
    """D8: ``<model id>`` is the first 16 hex characters of SHA-256 of the name."""
    import hashlib

    name = "Qwen/Qwen3-4B-GGUF:Q8_0"
    assert model_id(name) == hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    assert len(model_id(name)) == 16
    assert model_id(name) != model_id("Qwen/Qwen3-Embedding-4B-GGUF:Q8_0")
