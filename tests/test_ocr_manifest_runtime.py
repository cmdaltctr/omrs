"""The declared llama.cpp runtime of an OCR engine (change managed-llamacpp-runtimes, D10).

``declared_runtime(folder, cache_dir)`` reads ``[tool.omrs-ocr.runtime]`` with
the standard library only and applies the path, program, flag and file rules.
A block that breaks a rule raises :class:`RuntimeDeclarationError`; the route
turns that into an unavailable route whose reason names the rule.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
from pathlib import Path

import pytest

from omrs.integrations.ocr_worker.manifest import (
    DeclaredRuntime,
    RuntimeDeclarationError,
    declared_runtime,
)

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "src/omrs/integrations/ocr_worker/manifest.py"
SHA_A = "6017b1844a77837010649939fe2e934af17728fc89243f88b10bde4afa04d6be"
SHA_B = "63f415f961da981d0ee101cfdbf7a7bcc81ace4c4aa780a6e2823c0cd780761f"

BLOCK = f"""\
[project]
name = "omrs-ocr-engine-demo"

[tool.omrs-ocr.runtime]
program = "llama.cpp/llama-b11941/llama-server"
build = 11941
flags = ["--temp", "0", "-c", "24576", "-np", "1", "--image-min-tokens", "4"]

[[tool.omrs-ocr.runtime.files]]
flag = "-m"
path = "models/dots-mocr-Q8_0.gguf"
sha256 = "{SHA_A}"

[[tool.omrs-ocr.runtime.files]]
flag = "--mmproj"
path = "models/dots-mocr-mmproj-bf16.gguf"
sha256 = "{SHA_B}"
"""


def _engine(tmp_path: Path, text: str) -> tuple[Path, Path]:
    folder = tmp_path / "engine"
    folder.mkdir()
    (folder / "pyproject.toml").write_text(text, encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    return folder, cache


def _with(**changes: str) -> str:
    """Return BLOCK with one line replaced (key = new full line)."""
    text = BLOCK
    for old, new in changes.items():
        assert old in text, old
        text = text.replace(old, new)
    return text


def test_a_declared_runtime_is_read(tmp_path: Path) -> None:
    folder, cache = _engine(tmp_path, BLOCK)
    runtime = declared_runtime(folder, cache)
    assert isinstance(runtime, DeclaredRuntime)
    assert runtime.program == cache / "llama.cpp/llama-b11941/llama-server"
    assert runtime.build == 11941
    assert runtime.flags == ("--temp", "0", "-c", "24576", "-np", "1", "--image-min-tokens", "4")
    assert [(f.flag, f.path, f.sha256) for f in runtime.files] == [
        ("-m", cache / "models/dots-mocr-Q8_0.gguf", SHA_A),
        ("--mmproj", cache / "models/dots-mocr-mmproj-bf16.gguf", SHA_B),
    ]


def test_an_engine_without_the_block_declares_nothing(tmp_path: Path) -> None:
    folder, cache = _engine(tmp_path, '[project]\nname = "x"\n[tool.omrs-ocr]\nfoo = 1\n')
    assert declared_runtime(folder, cache) is None


def test_a_folder_without_pyproject_declares_nothing(tmp_path: Path) -> None:
    assert declared_runtime(tmp_path, tmp_path / "cache") is None


def test_the_cache_dir_decides_where_paths_land(tmp_path: Path) -> None:
    folder, _ = _engine(tmp_path, BLOCK)
    other = tmp_path / "elsewhere"
    runtime = declared_runtime(folder, other)
    assert runtime is not None
    assert runtime.program == other / "llama.cpp/llama-b11941/llama-server"


# -- path rules ---------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "/abs/models/m.gguf",
        "../escape.gguf",
        "models/../../escape.gguf",
        "models/../models/inside.gguf",
        "C:/win/m.gguf",
        "",
    ],
)
def test_a_file_path_outside_the_cache_is_refused(tmp_path: Path, bad: str) -> None:
    folder, cache = _engine(tmp_path, _with(**{"models/dots-mocr-Q8_0.gguf": bad}))
    with pytest.raises(RuntimeDeclarationError, match="path rule"):
        declared_runtime(folder, cache)


@pytest.mark.parametrize("bad", ["/usr/bin/llama-server", "../llama-server"])
def test_a_program_path_outside_the_cache_is_refused(tmp_path: Path, bad: str) -> None:
    folder, cache = _engine(tmp_path, _with(**{"llama.cpp/llama-b11941/llama-server": bad}))
    with pytest.raises(RuntimeDeclarationError, match="path rule"):
        declared_runtime(folder, cache)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX links")
def test_a_link_that_resolves_outside_the_cache_is_refused(tmp_path: Path) -> None:
    folder, cache = _engine(tmp_path, BLOCK)
    outside = tmp_path / "outside"
    outside.mkdir()
    (cache / "models").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeDeclarationError, match="path rule"):
        declared_runtime(folder, cache)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX links")
def test_a_link_that_stays_inside_the_cache_is_accepted(tmp_path: Path) -> None:
    folder, cache = _engine(tmp_path, BLOCK)
    real = cache / "real-models"
    real.mkdir()
    (cache / "models").symlink_to(real, target_is_directory=True)
    assert declared_runtime(folder, cache) is not None


# -- program rule -------------------------------------------------------------


def test_the_program_must_be_named_llama_server(tmp_path: Path) -> None:
    folder, cache = _engine(tmp_path, _with(**{"llama.cpp/llama-b11941/llama-server": "bin/sh"}))
    with pytest.raises(RuntimeDeclarationError, match="program rule"):
        declared_runtime(folder, cache)


# -- flag rules ---------------------------------------------------------------

RESERVED = [
    "--host",
    "--port",
    "-m",
    "--model",
    "--mmproj",
    "-hf",
    "--hf-repo",
    "--api-key",
    "--sleep-idle-seconds",
    "--log-file",
    "--model-url",
    "--model-url-extra",
]


@pytest.mark.parametrize("flag", RESERVED)
def test_a_reserved_flag_is_refused(tmp_path: Path, flag: str) -> None:
    folder, cache = _engine(tmp_path, _with(**{'"--temp", "0"': f'"{flag}", "x"'}))
    with pytest.raises(RuntimeDeclarationError, match="flag rule") as caught:
        declared_runtime(folder, cache)
    assert flag in str(caught.value)


@pytest.mark.parametrize("flag", ["--port=9999", "--host=0.0.0.0", "--model-url=http://x"])
def test_a_reserved_flag_in_equals_form_is_refused(tmp_path: Path, flag: str) -> None:
    folder, cache = _engine(tmp_path, _with(**{'"--temp", "0"': f'"{flag}", "0"'}))
    with pytest.raises(RuntimeDeclarationError, match="flag rule"):
        declared_runtime(folder, cache)


def test_flags_must_be_a_list_of_strings(tmp_path: Path) -> None:
    folder, cache = _engine(tmp_path, _with(**{'"--temp", "0"': '"--temp", 0'}))
    with pytest.raises(RuntimeDeclarationError, match="flag rule"):
        declared_runtime(folder, cache)


def test_flags_default_to_empty(tmp_path: Path) -> None:
    text = "\n".join(line for line in BLOCK.splitlines() if not line.startswith("flags ="))
    folder, cache = _engine(tmp_path, text)
    runtime = declared_runtime(folder, cache)
    assert runtime is not None
    assert runtime.flags == ()


# -- file and build rules -----------------------------------------------------


def test_a_file_flag_other_than_m_or_mmproj_is_refused(tmp_path: Path) -> None:
    folder, cache = _engine(tmp_path, _with(**{'flag = "--mmproj"': 'flag = "--lora"'}))
    with pytest.raises(RuntimeDeclarationError, match="file rule"):
        declared_runtime(folder, cache)


@pytest.mark.parametrize(
    "bad", ["abc", SHA_A[:-1], SHA_A + "0", "g" * 64, SHA_A.upper()[:-1] + "Z"]
)
def test_a_malformed_sha256_is_refused(tmp_path: Path, bad: str) -> None:
    folder, cache = _engine(tmp_path, _with(**{SHA_A: bad}))
    with pytest.raises(RuntimeDeclarationError, match="file rule"):
        declared_runtime(folder, cache)


def test_an_uppercase_sha256_is_read_as_lowercase(tmp_path: Path) -> None:
    folder, cache = _engine(tmp_path, _with(**{SHA_A: SHA_A.upper()}))
    runtime = declared_runtime(folder, cache)
    assert runtime is not None
    assert runtime.files[0].sha256 == SHA_A


def test_each_file_flag_may_appear_once(tmp_path: Path) -> None:
    folder, cache = _engine(tmp_path, _with(**{'flag = "--mmproj"': 'flag = "-m"'}))
    with pytest.raises(RuntimeDeclarationError, match="file rule"):
        declared_runtime(folder, cache)


@pytest.mark.parametrize("bad", ['"11941"', "0", "-3", "true", "1.5"])
def test_the_build_must_be_a_positive_whole_number(tmp_path: Path, bad: str) -> None:
    folder, cache = _engine(tmp_path, _with(**{"build = 11941": f"build = {bad}"}))
    with pytest.raises(RuntimeDeclarationError, match="build rule"):
        declared_runtime(folder, cache)


def test_the_build_is_required(tmp_path: Path) -> None:
    text = "\n".join(line for line in BLOCK.splitlines() if not line.startswith("build ="))
    folder, cache = _engine(tmp_path, text)
    with pytest.raises(RuntimeDeclarationError, match="build rule"):
        declared_runtime(folder, cache)


def test_the_program_is_required(tmp_path: Path) -> None:
    text = "\n".join(line for line in BLOCK.splitlines() if not line.startswith("program ="))
    folder, cache = _engine(tmp_path, text)
    with pytest.raises(RuntimeDeclarationError, match="program rule"):
        declared_runtime(folder, cache)


# -- standard library only ----------------------------------------------------


def _imported_modules(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "package-relative import in manifest.py"
            names.add((node.module or "").split(".")[0])
    return names


def test_manifest_imports_only_the_standard_library() -> None:
    modules = _imported_modules(MANIFEST.read_text(encoding="utf-8"))
    assert modules
    assert modules <= set(sys.stdlib_module_names) | {"__future__"}, modules


def test_the_import_check_sees_function_local_and_relative_imports() -> None:
    assert _imported_modules("def f():\n    import yaml\n") == {"yaml"}
    assert "omrs" in _imported_modules("from omrs.core import x\n")
    with pytest.raises(AssertionError):
        _imported_modules("from .core import x\n")


def test_provision_still_loads_manifest_by_path(tmp_path: Path) -> None:
    """``provision.py`` loads the helper from its file, without OMRS installed.

    It does not register the module in ``sys.modules``, so the new types must
    survive that load (a ``dataclass`` with string annotations does not).
    """
    provision = (REPO / "ocr-workers/provision.py").read_text(encoding="utf-8")
    assert "spec_from_file_location" in provision
    assert '"ocr_worker" / "manifest.py"' in provision
    spec = importlib.util.spec_from_file_location("omrs_ocr_manifest_by_path", MANIFEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "omrs_ocr_manifest_by_path" not in sys.modules
    assert module.engine_manifest and module.minimal_toml and module.licence_gate
    folder, cache = _engine(tmp_path, BLOCK)
    runtime = module.declared_runtime(folder, cache)
    assert runtime is not None and runtime.build == 11941


def test_cache_paths_are_not_resolved_through_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller passes the cache folder; the reader never reads the environment."""
    monkeypatch.setenv("OMRS_OCR_MODEL_CACHE", str(tmp_path / "ignored"))
    folder, cache = _engine(tmp_path, BLOCK)
    runtime = declared_runtime(folder, cache)
    assert runtime is not None
    assert os.fspath(runtime.program).startswith(os.fspath(cache))
