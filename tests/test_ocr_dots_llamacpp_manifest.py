"""The dots-mocr engine folder (the llama.cpp engine): lockfile and manifest.

Change dots-mocr-llamacpp-backend, tasks 2.1, 2b.3 and 4.2. The engine runs
dots.mocr through a llama.cpp server, so its environment must hold no
PyTorch. The ``[tool.omrs-ocr.runtime]`` block tells the host which server to
run (design D2); a test pins it to ``pins.py`` and the host's rules. The
PyTorch engine is gone, so the D6 copy test went with it.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.ocr_worker.dots_llamacpp import engine_modules

from omrs.integrations.ocr_worker.manifest import RuntimeDeclarationError, declared_runtime

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKERS = REPO_ROOT / "ocr-workers"
ENGINE_DIR = WORKERS / "engines" / "dots-mocr"
PACKAGE = "omrs_ocr_dots_mocr"

FORBIDDEN = frozenset({"torch", "torchvision", "transformers", "accelerate"})


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _lock_names() -> set[str]:
    lock = tomllib.loads((ENGINE_DIR / "uv.lock").read_text(encoding="utf-8"))
    return {_normalise(pkg["name"]) for pkg in lock["package"]}


def test_lockfile_holds_no_pytorch_package() -> None:
    """The lock resolves no torch, torchvision, transformers or accelerate."""
    names = _lock_names()
    assert {"omrs-ocr-worker-core", "pypdfium2", "pillow", "huggingface-hub"} <= names
    assert not names & FORBIDDEN, sorted(names & FORBIDDEN)


def test_manifest_declares_entry_point_gate_and_no_fetch_of_pytorch() -> None:
    """The manifest names the entry point, the licence gate and the fetch script."""
    manifest = tomllib.loads((ENGINE_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    project = manifest["project"]
    assert project["name"] == "omrs-ocr-dots-mocr"
    assert project["entry-points"]["omrs.ocr_engine"] == {"dots-mocr": f"{PACKAGE}.engine:ENGINE"}
    assert project["scripts"]["omrs-ocr-fetch"] == f"{PACKAGE}.fetch:main"
    gate = {k: v for k, v in manifest["tool"]["omrs-ocr"].items() if k != "runtime"}
    assert gate == {"licence-file": "LICENCE-NOTES.md", "requires-acceptance": True}
    declared = {
        _normalise(re.split(r"[\[\s><=!~]", r, maxsplit=1)[0]) for r in project["dependencies"]
    }
    assert declared == {
        "omrs-ocr-worker-core",
        "pypdfium2",
        "pillow",
        "huggingface-hub",
    }
    assert manifest["tool"]["uv"]["sources"]["omrs-ocr-worker-core"] == {"path": "../../core"}


def test_licence_notes_keep_the_clauses_and_add_provenance() -> None:
    """Licence notes copy the PyTorch engine's clauses and record the GGUF files."""
    notes = (ENGINE_DIR / "LICENCE-NOTES.md").read_text(encoding="utf-8")
    for clause in ("3.3(c)", "5.2", "Clause 8", "Clause 9"):
        assert clause in notes
    for needle in (
        "6017b1844a77837010649939fe2e934af17728fc89243f88b10bde4afa04d6be",
        "63f415f961da981d0ee101cfdbf7a7bcc81ace4c4aa780a6e2823c0cd780761f",
        "e539fbb52280393adc081b289ec597430a0f9031",
        "11941",
    ):
        assert needle in notes
    assert "/Users/" not in notes


def test_gitignore_keeps_environment_and_model_cache_out_of_git() -> None:
    """The engine's virtual environment and model cache are ignored."""
    lines = (ENGINE_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".venv/" in lines and ".model-cache/" in lines


def test_no_module_of_the_package_imports_pytorch() -> None:
    """No source file in the package names a PyTorch-family import."""
    pattern = re.compile(
        r"^\s*(?:import|from)\s+(?:torch|torchvision|transformers|accelerate|qwen_vl_utils)\b",
        re.MULTILINE,
    )
    sources = sorted((ENGINE_DIR / "src" / PACKAGE).glob("*.py"))
    assert sources, "the package has no source files"
    assert not [p.name for p in sources if pattern.search(p.read_text(encoding="utf-8"))]


# ── Task 2b.3: the runtime block the host reads (design D2) ────────────────


@pytest.fixture
def pins(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Import the engine's ``pins`` module from source."""
    with engine_modules(monkeypatch) as load:
        yield load("pins")


def _engine_copy(tmp_path: Path, old: str = "", new: str = "") -> Path:
    """Copy the engine manifest into a new folder, replacing *old* with *new* once."""
    source = (ENGINE_DIR / "pyproject.toml").read_text(encoding="utf-8")
    changed = source.replace(old, new, 1) if old else source
    assert old == "" or changed != source, f"{old!r} is not in the manifest"
    folder = tmp_path / "engine"
    folder.mkdir()
    (folder / "pyproject.toml").write_text(changed, encoding="utf-8")
    return folder


def test_the_host_reads_the_runtime_block_and_every_value_equals_pins(
    pins: Any, tmp_path: Path
) -> None:
    """The host accepts the block; its program, build, flags and hashes match ``pins.py``."""
    cache = tmp_path / "cache"
    cache.mkdir()
    runtime = declared_runtime(ENGINE_DIR, cache)
    assert runtime is not None
    assert runtime.program == cache / "llama.cpp" / "llama-server"
    assert runtime.build == pins.LLAMA_BUILD
    assert runtime.flags == pins.SERVER_FLAGS
    assert [(f.flag, f.path, f.sha256) for f in runtime.files] == [
        ("-m", cache / "models" / pins.MODEL_FILE.name, pins.MODEL_FILE.sha256),
        ("--mmproj", cache / "models" / pins.PROJECTOR_FILE.name, pins.PROJECTOR_FILE.sha256),
    ]


@pytest.mark.parametrize(
    ("old", "new", "rule"),
    [
        ('program = "llama.cpp/', 'program = "/opt/llama.cpp/', "path"),
        ('program = "llama.cpp/', 'program = "../llama.cpp/', "path"),
        (
            'program = "llama.cpp/llama-server"',
            'program = "llama.cpp/server"',
            "program",
        ),
        ("build = 11941", "build = 0", "build"),
        ("build = 11941", 'build = "11941"', "build"),
        ("flags = [", 'flags = ["--port", "9", ', "flag"),
        ("flags = [", 'flags = ["--model", "x.gguf", ', "flag"),
        ('flag = "-m"', 'flag = "-hf"', "file"),
        ('flag = "--mmproj"', 'flag = "-m"', "file"),
        ('path = "models/dots-mocr-Q8_0.gguf"', 'path = "../dots-mocr-Q8_0.gguf"', "path"),
        ('sha256 = "6017b184', 'sha256 = "6017', "file"),
    ],
)
def test_the_host_refuses_each_breach_of_a_declaration_rule(
    tmp_path: Path, old: str, new: str, rule: str
) -> None:
    """A copy of the block that breaks one rule is refused, and the error names that rule."""
    folder = _engine_copy(tmp_path, old, new)
    with pytest.raises(RuntimeDeclarationError) as excinfo:
        declared_runtime(folder, tmp_path)
    assert excinfo.value.rule == rule


def test_one_changed_hash_character_no_longer_equals_pins(pins: Any, tmp_path: Path) -> None:
    """One changed hash character passes the host but no longer equals ``pins.py``."""
    first = pins.MODEL_FILE.sha256
    flipped = ("0" if first[10] != "0" else "1").join([first[:10], first[11:]])
    folder = _engine_copy(tmp_path, first, flipped)
    runtime = declared_runtime(folder, tmp_path)
    assert runtime is not None
    assert runtime.files[0].sha256 != pins.MODEL_FILE.sha256
