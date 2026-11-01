"""Read an OCR engine's ``pyproject.toml`` manifest.

``ocr-workers/provision.py`` and the Integrations runtime probe both read
``[tool.omrs-ocr]`` here, so the licence step they report cannot differ
(change integrations-show-runtime-components, design D1).

``provision.py`` runs with the operator's system ``python3`` and loads this
file by its path, without OMRS installed. Keep it standard-library only and
free of package-relative imports.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, NamedTuple


def engine_manifest(folder: Path) -> dict[str, Any]:
    """Return the engine's parsed ``pyproject.toml``.

    ``tomllib`` exists from Python 3.11. The operator may run provisioning
    with an older system ``python3``, so a minimal reader covers the few
    flat tables provisioning needs.
    """
    text = (folder / "pyproject.toml").read_text(encoding="utf-8")
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python 3.10 and older
        return minimal_toml(text)
    return tomllib.loads(text)


_TABLE_RE = re.compile(r"^\[([^\[\]]+)\]\s*$")
_PAIR_RE = re.compile(r'^("?)([A-Za-z0-9_.-]+)\1\s*=\s*(.+?)\s*$')


def minimal_toml(text: str) -> dict[str, Any]:
    """Read flat ``key = "string" | true | false`` pairs, grouped by table.

    Only what provisioning reads: ``[tool.omrs-ocr]`` and
    ``[project.scripts]``. Arrays and inline tables are skipped.
    """
    data: dict[str, Any] = {}
    table: dict[str, Any] = data
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        header = _TABLE_RE.match(line)
        if header:
            table = data
            for part in (p.strip().strip('"') for p in header.group(1).split(".")):
                table = table.setdefault(part, {})
            continue
        pair = _PAIR_RE.match(line)
        if not pair:
            continue
        value = pair.group(3)
        if value in ("true", "false"):
            table[pair.group(2)] = value == "true"
        elif len(value) >= 2 and value[0] == value[-1] == '"':
            table[pair.group(2)] = value[1:-1]
    return data


def licence_gate(manifest: dict[str, Any]) -> tuple[bool, str | None]:
    """Return ``(requires acceptance, licence file)`` from ``[tool.omrs-ocr]``."""
    config = manifest.get("tool", {}).get("omrs-ocr", {})
    return bool(config.get("requires-acceptance", False)), config.get("licence-file")


def not_provisioned_reason(folder: Path, name: str) -> str:
    """Return the reason for an engine without an environment, with its licence step."""
    command = f"python3 ocr-workers/provision.py {name}"
    if (folder / "pyproject.toml").is_file():
        needs_licence, licence_file = licence_gate(engine_manifest(folder))
        if needs_licence:
            notes = licence_file or "the licence notes"
            return (
                f"Not provisioned. Read {notes} in the engine folder, then run "
                f"{command} --accept-model-licence."
            )
    return f"Not provisioned. Run {command}."


# -- Declared llama.cpp runtime (change managed-llamacpp-runtimes, D10) -------
#
# ``NamedTuple`` rather than ``dataclass``: ``provision.py`` loads this file
# without registering it in ``sys.modules``, and a ``dataclass`` with string
# annotations fails in that case.


class RuntimeFile(NamedTuple):
    """One model file of a declared runtime."""

    flag: str
    path: Path
    sha256: str


class DeclaredRuntime(NamedTuple):
    """The ``[tool.omrs-ocr.runtime]`` block after every rule held.

    Every path is absolute and lies inside the engine cache. Nothing here
    says the files exist: the manager checks that at start.
    """

    program: Path
    build: int
    flags: tuple[str, ...]
    files: tuple[RuntimeFile, ...]


class RuntimeDeclarationError(ValueError):
    """A runtime block breaks a rule; the message names the rule.

    Attributes:
        rule: One of ``program``, ``build``, ``path``, ``flag`` or ``file``.
    """

    def __init__(self, rule: str, detail: str) -> None:
        super().__init__(f"Runtime declaration breaks the {rule} rule: {detail}")
        self.rule = rule


#: Flags the host sets or forbids. ``-hf`` style aliases are listed too.
RESERVED_FLAGS = frozenset(
    {
        "--host",
        "--port",
        "-m",
        "--model",
        "--mmproj",
        "-hf",
        "-hfr",
        "--hf-repo",
        "-hff",
        "--hf-file",
        "-hft",
        "--hf-token",
        "--api-key",
        "--sleep-idle-seconds",
        "--log-file",
        "-mu",
    }
)
#: A flag that starts with this text is reserved (``--model-url`` and relatives).
RESERVED_FLAG_PREFIX = "--model-url"
#: The only model-file flags a declaration may use.
FILE_FLAGS = ("-m", "--mmproj")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")


def _inside_cache(relative: Any, cache_dir: Path, where: str) -> Path:
    """Return ``cache_dir / relative`` after the path rule held, else raise."""
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise RuntimeDeclarationError("path", f"{where} must be a non-empty relative path")
    if PurePosixPath(relative).is_absolute() or PureWindowsPath(relative).is_absolute():
        raise RuntimeDeclarationError("path", f"{where} must be relative to the engine cache")
    if ".." in PurePosixPath(relative).parts or ".." in PureWindowsPath(relative).parts:
        raise RuntimeDeclarationError("path", f"{where} must not hold '..'")
    root = os.path.realpath(cache_dir)
    target = os.path.realpath(cache_dir / relative)
    if os.path.commonpath([root, target]) != root:
        raise RuntimeDeclarationError("path", f"{where} resolves outside the engine cache")
    return cache_dir / relative


def _flag_name(flag: str) -> str:
    return flag.split("=", 1)[0]


def _check_flags(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeDeclarationError("flag", "flags must be a list of strings")
    for flag in value:
        name = _flag_name(flag)
        if name in RESERVED_FLAGS or name.startswith(RESERVED_FLAG_PREFIX):
            raise RuntimeDeclarationError(
                "flag", f"{name} is set by the host and may not be declared"
            )
    return tuple(value)


def _check_files(value: Any, cache_dir: Path) -> tuple[RuntimeFile, ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeDeclarationError("file", "files must be a list of tables")
    files: list[RuntimeFile] = []
    for index, item in enumerate(value):
        flag = item.get("flag")
        if flag not in FILE_FLAGS:
            raise RuntimeDeclarationError("file", f"files[{index}].flag must be -m or --mmproj")
        if any(done.flag == flag for done in files):
            raise RuntimeDeclarationError("file", f"files[{index}].flag {flag} appears twice")
        digest = item.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise RuntimeDeclarationError("file", f"files[{index}].sha256 must be 64 hex digits")
        path = _inside_cache(item.get("path"), cache_dir, f"files[{index}].path")
        files.append(RuntimeFile(flag, path, digest.lower()))
    return tuple(files)


def declared_runtime(folder: Path, cache_dir: Path) -> DeclaredRuntime | None:
    """Return the engine's declared llama.cpp runtime, or ``None`` when it has none.

    Reads ``[tool.omrs-ocr.runtime]`` of ``<folder>/pyproject.toml`` with
    ``tomllib``. An engine without that block (or without a ``pyproject.toml``)
    declares no runtime. The reader never looks at the environment: the caller
    resolves the engine cache and passes it in.

    Args:
        folder: The engine folder.
        cache_dir: The engine cache folder. Every declared path is relative to
            it and must resolve inside it.

    Returns:
        The checked declaration, with absolute paths.

    Raises:
        RuntimeDeclarationError: A rule is broken. The message names the rule.
    """
    if not (folder / "pyproject.toml").is_file():
        return None
    block = engine_manifest(folder).get("tool", {}).get("omrs-ocr", {}).get("runtime")
    if block is None:
        return None
    if not isinstance(block, dict):
        raise RuntimeDeclarationError("program", "runtime must be a table")
    if not isinstance(block.get("program"), str) or not block["program"]:
        raise RuntimeDeclarationError("program", "program must name the llama-server file")
    program = _inside_cache(block["program"], cache_dir, "program")
    expected = "llama-server.exe" if os.name == "nt" else "llama-server"
    if program.name != expected:
        raise RuntimeDeclarationError("program", f"the file name must be {expected}")
    build = block.get("build")
    if isinstance(build, bool) or not isinstance(build, int) or build < 1:
        raise RuntimeDeclarationError("build", "build must be a positive whole number")
    return DeclaredRuntime(
        program,
        build,
        _check_flags(block.get("flags", [])),
        _check_files(block.get("files", []), cache_dir),
    )
