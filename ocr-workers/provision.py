#!/usr/bin/env python3
"""Deterministic provisioning for one isolated OCR engine environment.

Resolves the named engine's virtual environment from that engine's own
``uv.lock`` only. The script never touches the parent OMRS project or
its virtual environment: every command runs with the engine folder as
its working directory, the uv project selectors are pinned to that
folder, and ``uv sync --locked`` refuses drift from the committed
lockfile.

Usage::

    python3 ocr-workers/provision.py paddleocr-vl
    python3 ocr-workers/provision.py paddleocr-vl --python 3.11
    python3 ocr-workers/provision.py dots-mocr --accept-model-licence
    python3 ocr-workers/provision.py dots-mocr --accept-model-licence --dry-run

Licence gate (design D9): an engine whose ``pyproject.toml`` declares
``[tool.omrs-ocr] requires-acceptance = true`` is refused without
``--accept-model-licence``, before anything is installed, and the error
names the engine's licence file.

After ``uv sync --locked``, an engine that ships an ``omrs-ocr-fetch``
console script runs it inside the engine environment, to download its
pinned weights and apply its patches. ``--dry-run`` installs nothing and
fetches nothing.

Supported interpreters: Python 3.11, 3.12, and 3.13 (the range every
engine manifest declares, ``>=3.11,<3.14``). Any other version is
rejected with an error naming the supported range before anything is
installed.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SUPPORTED_MIN = (3, 11)
SUPPORTED_MAX_INCLUSIVE = (3, 13)
SUPPORTED_RANGE_TEXT = ">=3.11,<3.14"

WORKERS_DIR = Path(__file__).resolve().parent
ENGINES_DIR = WORKERS_DIR / "engines"

#: The shared ``[tool.omrs-ocr]`` reader (also used by the Integrations probe).
MANIFEST_HELPER = (
    WORKERS_DIR.parent / "src" / "omrs" / "integrations" / "ocr_worker" / "manifest.py"
)

#: The console script an engine may ship to fetch weights and patch them.
FETCH_SCRIPT = "omrs-ocr-fetch"

#: Exit status when the licence gate refuses an engine.
EXIT_LICENCE_NOT_ACCEPTED = 3

_ENGINE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class UnsupportedPythonError(Exception):
    """The requested interpreter is outside the supported range.

    Attributes:
        version: The rejected ``(major, minor)`` version.
    """

    def __init__(self, version: tuple[int, int]) -> None:
        self.version = version
        super().__init__(
            f"Python {version[0]}.{version[1]} is not supported by the OCR "
            f"engines. Use a Python version in the range {SUPPORTED_RANGE_TEXT} "
            "(3.11, 3.12, or 3.13)."
        )


class UnknownEngineError(Exception):
    """The named engine has no folder with a ``pyproject.toml``."""


def parse_python_version(text: str) -> tuple[int, int]:
    """Extract the ``(major, minor)`` version from a version string.

    Args:
        text: A version such as ``3.12``, ``3.12.7``, or the leading
            part of a ``sys.version`` string.

    Returns:
        The ``(major, minor)`` pair.

    Raises:
        ValueError: If no ``major.minor`` prefix can be read.
    """
    parts = text.strip().split()
    candidate = parts[0] if parts else text.strip()
    segments = candidate.split(".")
    try:
        major = int(segments[0])
        minor = int(segments[1])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"cannot read a major.minor version from {text!r}") from exc
    return (major, minor)


def ensure_supported_python(version: tuple[int, int]) -> None:
    """Accept a supported interpreter version or reject it clearly.

    Raises:
        UnsupportedPythonError: If the version is outside
            ``>=3.11,<3.14``, naming the supported range.
    """
    if not (SUPPORTED_MIN <= version <= SUPPORTED_MAX_INCLUSIVE):
        raise UnsupportedPythonError(version)


def available_engines() -> list[str]:
    """Return the names of every engine folder, sorted."""
    if not ENGINES_DIR.is_dir():
        return []
    return sorted(p.name for p in ENGINES_DIR.iterdir() if (p / "pyproject.toml").is_file())


def engine_dir(name: str) -> Path:
    """Return the folder of engine *name*.

    Raises:
        UnknownEngineError: If the name is not a plain folder name or
            has no ``pyproject.toml``; the message lists known engines.
    """
    folder = ENGINES_DIR / name
    if not _ENGINE_NAME_RE.match(name) or not (folder / "pyproject.toml").is_file():
        known = ", ".join(available_engines()) or "none"
        raise UnknownEngineError(f"unknown OCR engine {name!r}; available engines: {known}")
    return folder


def _load_manifest_helper() -> Any:
    """Load the shared manifest reader from the checkout by its file path.

    The operator runs this script without OMRS installed, so it cannot
    import the package. The helper is standard-library only.
    """
    spec = importlib.util.spec_from_file_location("omrs_ocr_manifest", MANIFEST_HELPER)
    if spec is None or spec.loader is None:  # pragma: no cover - file ships with the checkout
        raise ImportError(f"cannot load {MANIFEST_HELPER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_manifest = _load_manifest_helper()
engine_manifest = _manifest.engine_manifest
_minimal_toml = _manifest.minimal_toml
licence_gate = _manifest.licence_gate


def has_fetch_script(manifest: dict[str, Any]) -> bool:
    """Return True when the engine ships an ``omrs-ocr-fetch`` console script."""
    return FETCH_SCRIPT in manifest.get("project", {}).get("scripts", {})


def engine_environment(folder: Path) -> dict[str, str]:
    """Return the process environment with uv pinned to the engine folder.

    An inherited absolute ``UV_PROJECT_ENVIRONMENT`` overrides the
    working directory, so without this pin ``uv sync --locked`` could
    install an engine into (and prune) another environment.
    """
    environment = dict(os.environ)
    environment["UV_PROJECT"] = str(folder)
    environment["UV_PROJECT_ENVIRONMENT"] = str(folder / ".venv")
    environment.pop("VIRTUAL_ENV", None)
    return environment


def build_commands(
    folder: Path, manifest: dict[str, Any], python: str, *, dry_run: bool
) -> list[list[str]]:
    """Return the commands provisioning runs, in order.

    ``uv sync --locked`` always runs (with ``--dry-run`` when asked). The
    fetch script runs after it, and never in a dry run.
    """
    sync = ["uv", "sync", "--locked", "--python", python]
    if dry_run:
        return [[*sync, "--dry-run"]]
    commands = [sync]
    if has_fetch_script(manifest):
        commands.append([str(folder / ".venv" / "bin" / FETCH_SCRIPT)])
    return commands


def _resolve_requested_python(requested: str) -> str | None:
    """Return the version text for *requested*, asking an interpreter path if given."""
    if not Path(requested).exists():
        return requested
    probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [requested, "-c", "import sys; print(sys.version.split()[0])"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        return None
    return probe.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    """Provision one engine environment from its own lockfile.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        The process exit status.
    """
    parser = argparse.ArgumentParser(
        description="Provision one isolated OCR engine environment from its uv.lock."
    )
    parser.add_argument("engine", help="engine folder name under ocr-workers/engines/")
    parser.add_argument(
        "--python", default="3.12", help="Python version or interpreter path (default: 3.12)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve from the lockfile without installing or fetching anything",
    )
    parser.add_argument(
        "--accept-model-licence",
        action="store_true",
        help="Accept the engine's model licence terms (required by some engines)",
    )
    args = parser.parse_args(argv)

    try:
        folder = engine_dir(args.engine)
    except UnknownEngineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    manifest = engine_manifest(folder)

    requires_acceptance, licence_file = licence_gate(manifest)
    if requires_acceptance and not args.accept_model_licence:
        licence_path = folder / (licence_file or "pyproject.toml")
        print(
            f"error: the {args.engine} model licence adds terms beyond its code licence. "
            f"Read {licence_path}, then re-run with --accept-model-licence to accept them. "
            "Nothing was installed.",
            file=sys.stderr,
        )
        return EXIT_LICENCE_NOT_ACCEPTED

    version_text = _resolve_requested_python(args.python)
    if version_text is None:
        print(f"error: cannot interrogate interpreter {args.python!r}", file=sys.stderr)
        return 1
    try:
        version = parse_python_version(version_text)
        ensure_supported_python(version)
    except (UnsupportedPythonError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if shutil.which("uv") is None:
        print(
            "error: uv is not on PATH; install it from https://docs.astral.sh/uv/",
            file=sys.stderr,
        )
        return 1

    print(f"provisioning OCR engine {args.engine} with Python {version[0]}.{version[1]} ...")
    environment = engine_environment(folder)
    for command in build_commands(folder, manifest, args.python, dry_run=args.dry_run):
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command, cwd=folder, env=environment, check=False
        )
        if completed.returncode != 0:
            print("error: provisioning failed; see the output above", file=sys.stderr)
            return completed.returncode
    if args.dry_run:
        print(f"dry run: {args.engine} resolves from its uv.lock; nothing was installed.")
    else:
        print(f"OCR engine {args.engine} ready (resolved from its uv.lock only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
