"""Editor config file for a kernel in a project environment (design D2, D7).

With a :class:`KernelEnvironment`, the launch config file gains a ``[venv]``
table (the absolute environment path, not writable) and ``runtime.dotenv``
set to an empty list, merged with the manifest's own values. This module
only renders text; the injected launcher writes the file.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omrs.core.plugins.manifest import ConfigFile


@dataclass(frozen=True)
class KernelEnvironment:
    """The project virtual environment a notebook kernel runs in.

    Attributes:
        venv_path: Absolute path to the project ``.venv`` folder.
    """

    venv_path: Path


def render_kernel_config(config: ConfigFile, kernel: KernelEnvironment) -> str:
    """Return ``config`` as TOML with the project environment merged in.

    Args:
        config: The manifest's launch config file.
        kernel: The project environment for the kernel.

    Returns:
        TOML text: the manifest tables plus ``[venv] path`` and
        ``writable = false``, and ``runtime.dotenv = []`` so marimo loads
        no ``.env`` file by itself.

    Raises:
        ValueError: If the path is relative or holds a control character.
    """
    path = str(kernel.venv_path)
    if not kernel.venv_path.is_absolute():
        raise ValueError("the project environment path must be absolute")
    values: dict[str, dict[str, Any]] = {name: dict(table) for name, table in config.values.items()}
    values.setdefault("runtime", {})["dotenv"] = []
    values.setdefault("venv", {}).update({"path": path, "writable": False})
    lines: list[str] = []
    for table in sorted(values):
        lines.append(f"[{table}]")
        lines.extend(f"{key} = {_scalar(values[table][key])}" for key in sorted(values[table]))
        lines.append("")
    return "\n".join(lines)


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if value == []:
        return "[]"
    return _basic_string(str(value))


def _basic_string(text: str) -> str:
    # TOML basic strings forbid raw control characters; refuse rather than escape.
    if any(unicodedata.category(char) == "Cc" for char in text):
        raise ValueError("a path in the editor config must not hold a control character")
    # With no control characters left, JSON escapes only '"' and '\', as TOML needs.
    return json.dumps(text, ensure_ascii=False)
