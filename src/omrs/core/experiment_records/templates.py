"""Packaged experiment templates, read through ``importlib.resources`` (design D9).

The files live in ``templates/`` inside this package, so they ship in the
wheel. ``experiments-agents.md`` is not named ``AGENTS.md``, because the
wheel leaves out files with that name. The repository skill keeps
byte-identical copies; a drift test compares them.
"""

from __future__ import annotations

from importlib import resources

TEMPLATE_NAMES = (
    "protocol.md",
    "report.md",
    "report-quick.md",
    "plan.json",
    "experiments-agents.md",
    "exp-readme.md",
)
"""Every packaged template file name."""


def read_template(name: str) -> str:
    """Return the text of one packaged template.

    Args:
        name: One of :data:`TEMPLATE_NAMES`.

    Returns:
        The template text.

    Raises:
        KeyError: *name* is not a packaged template.
    """
    if name not in TEMPLATE_NAMES:
        raise KeyError(f"{name} is not an experiment template; known: {', '.join(TEMPLATE_NAMES)}")
    package = resources.files("omrs.core.experiment_records")
    return (package / "templates" / name).read_text(encoding="utf-8")
