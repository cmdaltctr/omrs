"""Checks and notebook preparation for opening a Library experiment in marimo.

open-experiment-in-marimo design D1 to D4. The functions here only read files
and write one file, ``analysis.marimo.py``, in the experiment folder. They start
no process: the transport injects the conversion step as a :data:`Converter`
and the empty-notebook text as ``template``.

- :func:`check_project_environment` checks the project ``.venv`` and compares
  its Python version with the editor's tool environment (D2).
- :func:`check_runs_on_open` refuses a project ``pyproject.toml`` that makes
  marimo run cells when a notebook opens (D3, guard 6).
- :func:`prepare_notebook` opens, converts or creates the notebook with an
  exclusive create, so no existing file in the folder changes (D1, D4).

Every refusal is an :class:`EditorRefusal` with a reason from design D5 and a
plain message that names no file system path.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import tempfile
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The derived notebook, directly inside the experiment folder (design D1).
NOTEBOOK_NAME = "analysis.marimo.py"
#: The tracked analysis script that the notebook is converted from.
SOURCE_NAME = "analysis.py"
#: The command that adds jupytext to marimo's tool environment (design D4).
JUPYTEXT_HINT = 'uv tool install "marimo>=0.25.1,<0.26" --with jupytext'
#: Most shadowed distribution names that a check returns.
MAX_SHADOWED = 20

#: ``(source, output) -> (returncode, output_tail)``. Runs the editor's conversion.
Converter = Callable[[Path, Path], tuple[int, str]]

_VENV_DIR = ".venv"
_PYPROJECT = "pyproject.toml"
_MAX_SHEBANG = 4096
_VERSION = re.compile(r"^\s*(\d+)\.(\d+)")
_NAME_SEPARATORS = re.compile(r"[-_.]+")

_NO_VENV_MESSAGE = (
    "This project has no .venv folder. Run `uv sync` (or `python -m venv .venv`) "
    "in the project folder, then open again."
)
_RUNS_ON_OPEN_MESSAGE = (
    "The project's pyproject.toml sets `auto_instantiate = true` under "
    "`[tool.marimo.runtime]`, so marimo would run every cell when the notebook opens. "
    "Set it to false, then open again."
)
_INVALID_PYPROJECT_MESSAGE = (
    "The project's pyproject.toml is not valid TOML, so OMRS cannot check that no cell "
    "runs when the notebook opens. Fix the file, then open again."
)
_NOT_REGULAR_MESSAGE = (
    f"{NOTEBOOK_NAME} is a link or not a regular file. "
    "Remove it or replace it with a regular file, then open again."
)
_CONVERTER_MISSING_MESSAGE = (
    f"marimo needs jupytext to convert {SOURCE_NAME}. Run `{JUPYTEXT_HINT}`, then open again."
)
_CONVERSION_FAILED_MESSAGE = f"marimo could not convert {SOURCE_NAME}."


class EditorRefusal(Exception):
    """The notebook cannot open. Nothing was written to the experiment folder.

    Attributes:
        reason: One of the 409 reasons of design D5.
        message: A plain line for the user. It names no file system path.
        output_tail: The converter's last output lines when a conversion
            failed, for the server log only. Empty otherwise.
    """

    def __init__(self, reason: str, message: str, *, output_tail: str = "") -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.output_tail = output_tail


@dataclass(frozen=True)
class ProjectEnvironment:
    """The project environment that the notebook kernel runs in (design D2).

    Attributes:
        venv: The resolved ``<root>/.venv`` folder.
        python: Python ``major.minor`` from the project ``pyvenv.cfg``, or
            None when it cannot be read.
        marimo_in_project: True when the project environment has marimo.
        shadowed: Distributions that the editor's environment holds with a
            different version, sorted, at most :data:`MAX_SHADOWED`. Empty
            when marimo is in the project.
    """

    venv: Path
    python: str | None
    marimo_in_project: bool
    shadowed: tuple[str, ...]


@dataclass(frozen=True)
class PreparedNotebook:
    """The notebook that the editor opens.

    Attributes:
        path: ``<folder>/analysis.marimo.py``.
        state: ``"converted"``, ``"created"`` or ``"existing"``.
        source_newer: True when ``analysis.py`` is newer than the notebook.
    """

    path: Path
    state: str
    source_newer: bool


def check_project_environment(root: Path, editor_executable: Path) -> ProjectEnvironment:
    """Check the project ``.venv`` before a launch (design D2).

    Args:
        root: The resolved project folder.
        editor_executable: The registered editor executable.

    Returns:
        The resolved environment, its Python version and the shadowed names.

    Raises:
        EditorRefusal: ``no_project_environment`` when the resolved ``.venv``
            has no ``pyvenv.cfg`` or ``bin/python``; ``python_mismatch`` when
            the project has no marimo and its Python version differs from the
            editor's. The version check is skipped when a file cannot be read.
    """
    venv = Path(os.path.realpath(root / _VENV_DIR))
    if not (
        venv.is_dir() and (venv / "pyvenv.cfg").is_file() and (venv / "bin" / "python").exists()
    ):
        raise EditorRefusal("no_project_environment", _NO_VENV_MESSAGE)
    python = _python_version(venv)
    project_packages = _distributions(venv)
    marimo_in_project = "marimo" in project_packages
    if marimo_in_project:
        return ProjectEnvironment(venv, python, True, ())
    tool = _tool_environment(editor_executable)
    if tool is None:
        return ProjectEnvironment(venv, python, False, ())
    tool_python = _python_version(tool)
    if python is not None and tool_python is not None and python != tool_python:
        raise EditorRefusal(
            "python_mismatch",
            f"The project .venv uses Python {python}, but marimo runs on Python "
            f"{tool_python}. Use a project .venv with Python {tool_python}, or add marimo "
            "to the project's dev dependencies, then open again.",
        )
    tool_packages = _distributions(tool)
    shadowed = sorted(
        name
        for name, version in tool_packages.items()
        if name in project_packages and project_packages[name] != version
    )
    return ProjectEnvironment(venv, python, False, tuple(shadowed[:MAX_SHADOWED]))


def check_runs_on_open(folder: Path) -> None:
    """Refuse a project setting that runs cells when the notebook opens (D3).

    The nearest ``pyproject.toml`` is found the way marimo finds it: from
    *folder* upwards to the file system root. No file is accepted.

    Args:
        folder: The experiment folder that holds the notebook.

    Raises:
        EditorRefusal: ``project_config_runs_on_open`` when the file sets
            ``[tool.marimo.runtime] auto_instantiate`` to true, or cannot be
            read as TOML.
    """
    pyproject = _nearest_pyproject(folder)
    if pyproject is None:
        return
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise EditorRefusal("project_config_runs_on_open", _INVALID_PYPROJECT_MESSAGE) from None
    runtime = _table(_table(_table(data, "tool"), "marimo"), "runtime")
    if runtime.get("auto_instantiate"):
        raise EditorRefusal("project_config_runs_on_open", _RUNS_ON_OPEN_MESSAGE)


def notebook_exists(folder: Path) -> bool:
    """Tell whether the experiment folder holds the notebook.

    Args:
        folder: The experiment folder.

    Returns:
        True for a regular file, False when there is no entry.

    Raises:
        EditorRefusal: ``notebook_not_regular`` when the entry is a link or
            not a regular file.
    """
    try:
        mode = os.lstat(folder / NOTEBOOK_NAME).st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(mode):
        raise EditorRefusal("notebook_not_regular", _NOT_REGULAR_MESSAGE)
    return True


def needs_conversion(folder: Path) -> bool:
    """Tell whether opening the folder runs the editor's conversion.

    Args:
        folder: The experiment folder.

    Returns:
        True when the notebook is absent and ``analysis.py`` is a regular file.

    Raises:
        EditorRefusal: ``notebook_not_regular``, as :func:`notebook_exists`.
    """
    return not notebook_exists(folder) and _regular_mtime(folder / SOURCE_NAME) is not None


def prepare_notebook(
    folder: Path, *, convert: Converter, scratch_parent: Path, template: str
) -> PreparedNotebook:
    """Open, convert or create ``analysis.marimo.py`` (design D1, D4).

    An existing notebook is returned unchanged. Else ``analysis.py`` is
    converted into a new private (0700) folder below *scratch_parent*, and the
    result is copied into the experiment folder with an exclusive create. A
    folder without ``analysis.py`` gets *template*. A notebook that appears
    meanwhile is kept. The private folder is always removed.

    Args:
        folder: The resolved experiment folder.
        convert: Runs the editor's conversion recipe.
        scratch_parent: The parent of the private conversion folders.
        template: The text of the packaged empty notebook.

    Returns:
        The notebook path, how it was made and whether its source is newer.

    Raises:
        EditorRefusal: ``notebook_not_regular``; ``converter_missing`` when
            the conversion failed and its output names jupytext;
            ``conversion_failed`` for any other failure.
    """
    notebook = folder / NOTEBOOK_NAME
    if notebook_exists(folder):
        return _existing(folder)
    if _regular_mtime(folder / SOURCE_NAME) is None:
        content = template.encode("utf-8")
        state = "created"
    else:
        content = _convert(folder / SOURCE_NAME, convert, scratch_parent)
        state = "converted"
    if not _create_exclusive(notebook, content):
        return _existing(folder)
    return PreparedNotebook(notebook, state, _source_newer(folder))


def _convert(source: Path, convert: Converter, scratch_parent: Path) -> bytes:
    """Run the converter in a private folder and return the notebook bytes."""
    scratch_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    private = Path(tempfile.mkdtemp(dir=scratch_parent))
    try:
        output = private / NOTEBOOK_NAME
        returncode, tail = convert(source, output)
        if returncode == 0 and output.is_file() and not output.is_symlink():
            return output.read_bytes()
    finally:
        shutil.rmtree(private, ignore_errors=True)
    if returncode != 0 and "jupytext" in tail.lower():
        raise EditorRefusal("converter_missing", _CONVERTER_MISSING_MESSAGE, output_tail=tail)
    raise EditorRefusal("conversion_failed", _CONVERSION_FAILED_MESSAGE, output_tail=tail)


def _create_exclusive(path: Path, content: bytes) -> bool:
    """Write a new file. Return False when an entry with this name exists."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    try:
        view = memoryview(content)
        while view:
            view = view[os.write(fd, view) :]
    except BaseException:
        os.close(fd)
        path.unlink(missing_ok=True)
        raise
    os.close(fd)
    return True


def _existing(folder: Path) -> PreparedNotebook:
    """Return the notebook that is already in the folder, after a new check."""
    notebook_exists(folder)
    return PreparedNotebook(folder / NOTEBOOK_NAME, "existing", _source_newer(folder))


def _source_newer(folder: Path) -> bool:
    source = _regular_mtime(folder / SOURCE_NAME)
    notebook = _regular_mtime(folder / NOTEBOOK_NAME)
    return source is not None and notebook is not None and source > notebook


def _regular_mtime(path: Path) -> float | None:
    """Return the change time of a regular file that is not a link, else None."""
    try:
        info = os.lstat(path)
    except OSError:
        return None
    return info.st_mtime if stat.S_ISREG(info.st_mode) else None


def _nearest_pyproject(folder: Path) -> Path | None:
    for directory in (folder, *folder.parents):
        candidate = directory / _PYPROJECT
        if candidate.exists():
            return candidate
    return None


def _table(data: Any, key: str) -> dict[str, Any]:
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, dict) else {}


def _tool_environment(executable: Path) -> Path | None:
    """Find the editor's environment from the ``#!`` line of its executable."""
    try:
        with open(os.path.realpath(executable), "rb") as handle:
            first = handle.readline(_MAX_SHEBANG).decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not first.startswith("#!"):
        return None
    interpreter = Path(first[2:].strip())
    if not interpreter.is_absolute():
        return None
    return interpreter.parent.parent


def _python_version(venv: Path) -> str | None:
    """Read Python ``major.minor`` from ``pyvenv.cfg``; None when unreadable."""
    try:
        text = (venv / "pyvenv.cfg").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip().lower()] = value.strip()
    for key in ("version_info", "version"):
        match = _VERSION.match(values.get(key, ""))
        if match:
            return f"{match.group(1)}.{match.group(2)}"
    return None


def _distributions(env: Path) -> dict[str, str]:
    """Return ``{normalised name: version}`` from the ``*.dist-info`` folders."""
    found: dict[str, str] = {}
    for site in sorted((env / "lib").glob("python*/site-packages")):
        for name in _entries(site):
            if not name.endswith(".dist-info"):
                continue
            project, separator, version = name.removesuffix(".dist-info").partition("-")
            if separator and project and version:
                found[_NAME_SEPARATORS.sub("-", project).lower()] = version
    return found


def _entries(folder: Path) -> Iterable[str]:
    try:
        return [entry.name for entry in os.scandir(folder)]
    except OSError:
        return []
