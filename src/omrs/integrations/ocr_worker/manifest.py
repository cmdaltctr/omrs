"""Read an OCR engine's ``pyproject.toml`` manifest.

``ocr-workers/provision.py`` and the Integrations runtime probe both read
``[tool.omrs-ocr]`` here, so the licence step they report cannot differ
(change integrations-show-runtime-components, design D1).

``provision.py`` runs with the operator's system ``python3`` and loads this
file by its path, without OMRS installed. Keep it standard-library only and
free of package-relative imports.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


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
