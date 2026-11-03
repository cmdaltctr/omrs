"""The ``pdf_readers`` block of ``GET /v1/integrations`` (ordered-reader-and-ocr-lists, D8).

One item for each registered PDF reader, so a reader registered later shows
with no change here. The probe only checks that the reader's package imports
(``capabilities.pdf_reader_options``). Nothing installs, downloads or starts.

``used_by`` holds the lines the Integrations page shows as given: the reader's
place in the host list, and each saved user profile whose Read document step
lists it.

This module imports no web framework.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from importlib import metadata
from typing import Any

from ... import capabilities
from ...core.reading_lists import expand_pdf_reader, reader_list
from ...integrations.pdf import registry as pdf_registry
from .install_environment import (
    CHECKOUT,
    UV_TOOL,
    InstallEnvironment,
    _requirement_name,
    copy_command,
    extra_requirements,
    is_base_extra,
    tool_install_command,
)
from .uninstall_profiles import graph_readers

logger = logging.getLogger(__name__)

_ORDINALS = ("First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth")
_PAGE = "Settings > Document reading"


def _metadata() -> tuple[list[str], list[str]]:
    """Return the requirement lines and the extra names of the installed ``omrs``."""
    try:
        dist = metadata.distribution("omrs")
    except metadata.PackageNotFoundError:
        return [], []
    return list(dist.requires or []), list(dist.metadata.get_all("Provides-Extra") or [])


def _extra_of(package: str, requires: list[str], extras: Iterable[str]) -> str | None:
    """Return the extra that adds *package*, or ``None`` when every install holds it.

    An extra whose packages are all base requirements only keeps an old command
    working (``pdf-inspector``), so it does not count.
    """
    wanted = _requirement_name(package)
    for extra in extras:
        if is_base_extra(extra, requires):
            continue
        if any(_requirement_name(line) == wanted for line in extra_requirements(extra, requires)):
            return extra
    return None


def _base_command(environment: InstallEnvironment) -> str:
    """Return the command that restores the base install for this install type."""
    if environment.install_type == CHECKOUT:
        return "uv sync"
    if environment.install_type == UV_TOOL:
        return tool_install_command(environment, environment.receipt_extras)
    return 'pip install --force-reinstall "omrs"'


def _host_lines(settings: Any) -> dict[str, str]:
    """Return the position line of each reader in the host list."""
    if settings is None:
        return {}
    lines: dict[str, str] = {}
    for index, name in enumerate(reader_list(settings)):
        ordinal = _ORDINALS[index] if index < len(_ORDINALS) else f"Number {index + 1}"
        lines.setdefault(name, f"{ordinal} in {_PAGE}")
    return lines


def _profile_lines(catalogue: Any) -> dict[str, list[str]]:
    """Return the ``Profile <title>`` lines of each reader that saved profiles list.

    A step that sets the single ``pdf_reader`` lists what it expands to. A
    catalogue that cannot be read gives no lines, and the host lines remain.
    """
    lines: dict[str, list[str]] = {}
    if catalogue is None:
        return lines
    try:
        for record in catalogue.list_profiles():
            line = f"Profile {record.get('title') or record['profile_id']}"
            document = catalogue.slot_document(record["profile_id"], "ingest")
            for option, names in graph_readers(document):
                listed = expand_pdf_reader(names[0]) if option == "pdf_reader" else names
                for name in listed:
                    if line not in lines.setdefault(name, []):
                        lines[name].append(line)
    except Exception:
        # The detail stays out of the response; the stack goes to the redacted log.
        logger.warning("Could not read the saved profiles for the PDF readers list.")
        logger.debug("Profile read failed.", exc_info=True)
    return lines


def pdf_reader_items(
    settings: Any, environment: InstallEnvironment, catalogue: Any
) -> list[dict[str, Any]]:
    """Return one item for each registered PDF reader, in registry order.

    Args:
        settings: The Engine's frozen ``EffectiveSettings``, or ``None``.
        environment: The detected install type.
        catalogue: The saved-profile catalogue, or ``None``.

    Returns:
        Items with ``name``, ``installed``, ``extra`` (``None`` for a base
        reader), ``fix_command`` (``None`` when installed) and ``used_by``.
    """
    requires, extras = _metadata()
    host, profiles = _host_lines(settings), _profile_lines(catalogue)
    items = []
    for name, reason in capabilities.pdf_reader_options().items():
        extra = _extra_of(pdf_registry.describe(name)["probe_module"], requires, extras)
        if reason is None:
            fix = None
        else:
            fix = _base_command(environment) if extra is None else copy_command(environment, extra)
        used_by = ([host[name]] if name in host else []) + profiles.get(name, [])
        items.append(
            {
                "name": name,
                "installed": reason is None,
                "extra": extra,
                "fix_command": fix,
                "used_by": used_by,
            }
        )
    return items
