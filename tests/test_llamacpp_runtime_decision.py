"""A managed decision runtime (change document-reading-routers, task 2.4).

A ``llamacpp`` decision model entry with ``server: "managed"`` runs as runtime
``decision-<entry name>``: role ``decision``, the model file and the projector
file declared with SHA-256, ``127.0.0.1``, one slot and a build floor. A build
below the floor is refused with ``wrong-build``, and the reason names the build
found and the floor.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.fixtures.llamacpp.harness import RuntimeEnv, runtime_env_fixture

from omrs.integrations.llamacpp_runtime import DeclaredFile, RuntimeSpec, decision_spec
from omrs.integrations.llamacpp_runtime.manager import RuntimeUnavailable

BINARY = "/b/llama-server"
MODEL = DeclaredFile(flag="-m", path="/m/clef-q8_0.gguf", sha256="a" * 64)
PROJECTOR = DeclaredFile(flag="--mmproj", path="/m/mmproj.gguf", sha256="b" * 64)


def _spec(*files: DeclaredFile, port: int = 8091, binary: str = BINARY) -> RuntimeSpec:
    return decision_spec(
        name="clef", binary=binary, port=port, files=files or (MODEL,), min_build=11941
    )


def test_the_argument_list_holds_both_files_loopback_and_one_slot() -> None:
    spec = _spec(MODEL, PROJECTOR)

    assert list(spec.argv) == [
        BINARY, "-m", MODEL.path, "--mmproj", PROJECTOR.path,
        "--host", "127.0.0.1", "--port", "8091", "--parallel", "1",
    ]  # fmt: skip
    assert (spec.id, spec.role, spec.mode, spec.port_policy) == (
        "decision-clef", "decision", "managed", "fixed",
    )  # fmt: skip
    assert spec.one_slot is True
    assert spec.files == (MODEL, PROJECTOR)
    assert spec.min_build == 11941
    assert spec.build is None, "a floor, not an exact build"


def test_a_text_entry_has_no_projector_flag() -> None:
    assert "--mmproj" not in _spec(MODEL).argv


def test_the_json_form_keeps_the_floor() -> None:
    spec = _spec(MODEL, PROJECTOR)
    data = spec.to_dict()

    assert json.loads(json.dumps(data)) == data
    assert RuntimeSpec.from_dict(data) == spec


def test_a_blank_entry_name_is_not_a_runtime_id() -> None:
    with pytest.raises(ValueError):
        decision_spec(name="", binary=BINARY, port=8091, files=(MODEL,), min_build=11941)


# ── Start checks with the fake llama-server ─────────────────────────────

posix = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")


@pytest.fixture()
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimeEnv]:
    yield from runtime_env_fixture(tmp_path, monkeypatch)


def _fake_spec(runtime_env: RuntimeEnv, build: str) -> tuple[RuntimeSpec, object]:
    from tests.unit.llamacpp_fake import free_port

    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_BUILD=build)
    digest = hashlib.sha256(fake.model.read_bytes()).hexdigest()
    model = DeclaredFile(flag="-m", path=str(fake.model), sha256=digest)
    return _spec(model, port=free_port(), binary=str(fake.binary)), fake


@posix
def test_a_build_below_the_floor_is_refused_and_named(runtime_env: RuntimeEnv) -> None:
    spec, fake = _fake_spec(runtime_env, "11900")
    manager = runtime_env.manager()

    with pytest.raises(RuntimeUnavailable) as caught:
        manager.lease(spec).join()

    assert caught.value.reason == "wrong-build"
    assert "b11900" in caught.value.reason_text and "b11941" in caught.value.reason_text
    assert fake.starts() == []
    status = manager.status([spec])[0]
    assert (status["role"], status["state"], status["reason"]) == (
        "decision", "failed", "wrong-build",
    )  # fmt: skip


@posix
def test_a_build_above_the_floor_starts(runtime_env: RuntimeEnv) -> None:
    spec, fake = _fake_spec(runtime_env, "11960")

    url = runtime_env.manager().lease(spec).join()

    assert url == f"http://127.0.0.1:{spec.port}"
    assert len(fake.starts()) == 1
