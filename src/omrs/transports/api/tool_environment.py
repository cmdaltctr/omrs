"""Find the marimo ``uv tool`` environment (install-marimo-from-integrations, D1, D2, D7, D8).

marimo is not an extra. It lives in its own ``uv tool`` environment, outside
the server's Python (ADR-075, ADR-101). This module builds the fixed install
and uninstall commands from the shipped marimo manifest, and reads what uv
wrote: the tool receipt and the package metadata of the tool environment.

It asks uv once per detector where its folders are (``uv tool dir`` and
``uv tool dir --bin``, 10 s limit each), because uv's folder rule has
several steps and may change. Every other step reads files only. The
process runs only through the injected runner. The default runner passes
the server environment without any ``*_API_KEY`` variable, so
``UV_TOOL_DIR`` and ``UV_TOOL_BIN_DIR`` reach uv, as for the install job.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

from ...core.plugins.manifest import parse_manifest
from ...core.plugins.shipped import shipped_manifests
from ...core.plugins.versions import VersionRange, parse_version
from .install_environment import RECEIPT_NAME, find_uv

logger = logging.getLogger(__name__)

#: The one external tool the card installs.
TOOL = "marimo"
#: The package the Library needs to convert ``analysis.py``.
CONVERTER = "jupytext"
#: Seconds one ``uv tool dir`` call may take.
DIR_TIMEOUT_SECONDS = 10.0
UNINSTALL_COMMAND = f"uv tool uninstall {TOOL}"

READY = "ready"
NEEDS_JUPYTEXT = "needs-jupytext"
OUTSIDE_RANGE = "outside-range"
NOT_INSTALLED = "not-installed"
UNKNOWN = "unknown"

#: Runs one argument list with a time limit; returns the exit code and stdout.
Runner = Callable[[Sequence[str], float], tuple[int, str]]


def shipped_range() -> VersionRange:
    """Return the tested marimo range of the shipped manifest.

    Raises:
        RuntimeError: The package ships no readable marimo manifest.
    """
    for path in shipped_manifests():
        manifest = parse_manifest(path.read_bytes())
        if manifest.tool_name == TOOL:
            return manifest.tested_versions
    raise RuntimeError("The shipped marimo manifest is missing.")


def requirement(tested: VersionRange) -> str:
    """Return the marimo requirement for *tested*, for example ``marimo>=0.25.1,<0.26.0``."""
    return f"{TOOL}{tested.describe()}"


def install_argv(uv: str, tested: VersionRange) -> list[str]:
    """Return the fixed install argument list (no shell, no request text)."""
    return [uv, "tool", "install", requirement(tested), "--with", CONVERTER]


def uninstall_argv(uv: str) -> list[str]:
    """Return the fixed uninstall argument list."""
    return [uv, "tool", "uninstall", TOOL]


def install_command(tested: VersionRange) -> str:
    """Return the copy-ready install command for a terminal."""
    return f'uv tool install "{requirement(tested)}" --with {CONVERTER}'


def _clauses(specifier: str) -> frozenset[str]:
    return frozenset(part.replace(" ", "") for part in specifier.split(",") if part.strip())


def _receipt(path: Path) -> dict[str, object]:
    """Return the receipt's ``[tool]`` table, or an empty mapping when unreadable."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {}
    tool = data.get("tool")
    return tool if isinstance(tool, dict) else {}


def _requirements(tool: dict[str, object]) -> list[dict[str, object]]:
    items = tool.get("requirements")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def installed_by_card(receipt: Path, tested: VersionRange) -> bool:
    """Return whether *receipt* holds exactly what the card installs (D7).

    That is a ``marimo`` requirement whose specifier clauses equal the
    *tested* range, a ``jupytext`` requirement without a specifier, and
    nothing else. An unreadable receipt does not match.
    """
    items = _requirements(_receipt(receipt))
    found = {str(item.get("name")): item for item in items}
    if len(items) != 2 or set(found) != {TOOL, CONVERTER}:
        return False
    specifier = found[TOOL].get("specifier")
    if not isinstance(specifier, str) or _clauses(specifier) != _clauses(tested.describe()):
        return False
    return found[CONVERTER].get("specifier") in (None, "")


def _entrypoint(tool: dict[str, object]) -> str | None:
    items = tool.get("entrypoints")
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("name") == TOOL:
            path = item.get("install-path")
            return path if isinstance(path, str) and os.path.isabs(path) else None
    return None


def _versions(environment: Path) -> dict[str, str]:
    """Return the installed package versions of the tool environment, by lower-case name."""
    found: dict[str, str] = {}
    for site in sorted(environment.glob("lib/python*/site-packages")):
        for dist in metadata.distributions(path=[str(site)]):
            name = (dist.metadata["Name"] or "").lower()
            if name and name not in found:
                found[name] = dist.version
    return found


@dataclass(frozen=True)
class ToolStatus:
    """What the server found for the marimo tool environment.

    Attributes:
        availability: ``ready``, ``needs-jupytext``, ``outside-range``,
            ``not-installed`` or ``unknown``.
        problem: ``uv-not-found`` or ``status-unknown`` when ``unknown``, else ``None``.
        uv: Path of the ``uv`` program, or ``None``.
        version: The installed marimo version, or ``None``.
        jupytext: Whether jupytext is in the tool environment.
        executable: The marimo entrypoint path from the receipt, or ``None``.
        installed_by_card: Whether the receipt holds exactly what the card installs.
    """

    availability: str
    problem: str | None = None
    uv: str | None = None
    version: str | None = None
    jupytext: bool = False
    executable: str | None = None
    installed_by_card: bool = False


def install_caution(status: ToolStatus, tested: VersionRange) -> str | None:
    """Return the red caution shown before Install replaces a marimo (D8), or ``None``."""
    if status.availability not in (NEEDS_JUPYTEXT, OUTSIDE_RANGE):
        return None
    return (
        f"Install replaces your marimo {status.version} tool environment with "
        f"marimo {tested.describe()} and {CONVERTER}."
    )


def run_uv(argv: Sequence[str], timeout: float) -> tuple[int, str]:
    """Run one short ``uv`` command with no shell and no stdin.

    Raises:
        OSError: The program cannot start.
        TimeoutError: It runs longer than *timeout*.
    """
    env = {key: value for key, value in os.environ.items() if not key.upper().endswith("_API_KEY")}
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv built by this module, no shell
            list(argv),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"{argv[0]} did not finish within {timeout} s") from exc
    return done.returncode, done.stdout


@dataclass
class ToolDetector:
    """Detects the marimo tool environment. One detector lives per launch.

    Attributes:
        runner: Runs ``uv tool dir``. ``None`` uses :func:`run_uv`.
        find: Returns the ``uv`` path. ``None`` uses :func:`find_uv`.
        tested: Returns the tested marimo range (tests replace it).

    The two ``None`` defaults are looked up when used, so the test suite can
    replace the module functions for every runtime at once.
    """

    runner: Runner | None = None
    find: Callable[[], str | None] | None = None
    tested: Callable[[], VersionRange] = shipped_range
    _folders: tuple[Path, Path] | None = field(default=None, repr=False)

    def _dirs(self, uv: str) -> tuple[Path, Path] | None:
        """Return ``(tools, bin)`` from uv, asking only once per detector."""
        if self._folders is None:
            answers = []
            for argv in ([uv, "tool", "dir"], [uv, "tool", "dir", "--bin"]):
                try:
                    code, out = (self.runner or run_uv)(argv, DIR_TIMEOUT_SECONDS)
                except (OSError, TimeoutError):
                    logger.warning(
                        "`%s` failed; the marimo card shows unknown.", " ".join(argv[1:])
                    )
                    return None
                text = out.strip()
                if code != 0 or not text:
                    return None
                answers.append(Path(text))
            self._folders = (answers[0], answers[1])
        return self._folders

    def detect(self) -> ToolStatus:
        """Return the marimo tool state. Runs ``uv tool dir`` only on the first call."""
        uv = (self.find or find_uv)()
        if uv is None:
            return ToolStatus(UNKNOWN, problem="uv-not-found")
        folders = self._dirs(uv)
        if folders is None:
            return ToolStatus(UNKNOWN, problem="status-unknown", uv=uv)
        environment = folders[0] / TOOL
        receipt = environment / RECEIPT_NAME
        if not receipt.is_file():
            return ToolStatus(NOT_INSTALLED, uv=uv)
        tested = self.tested()
        try:
            versions = _versions(environment)
        except OSError:
            return ToolStatus(UNKNOWN, problem="status-unknown", uv=uv)
        version = versions.get(TOOL)
        parsed = parse_version(version) if version else None
        if parsed is None:
            return ToolStatus(UNKNOWN, problem="status-unknown", uv=uv)
        jupytext = CONVERTER in versions
        if not tested.contains(parsed):
            availability = OUTSIDE_RANGE
        else:
            availability = READY if jupytext else NEEDS_JUPYTEXT
        return ToolStatus(
            availability,
            uv=uv,
            version=version,
            jupytext=jupytext,
            executable=_entrypoint(_receipt(receipt)),
            installed_by_card=installed_by_card(receipt, tested),
        )
