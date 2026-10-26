"""Result of one notebook conversion run (design D4, D7).

The supervisor runs the manifest's ``convert_script`` recipe through the
registry's injected runner; this module holds only the result shape.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Lines of conversion output kept for the server log.
CONVERT_TAIL_LINES = 40


@dataclass(frozen=True)
class ConvertResult:
    """Outcome of one conversion run.

    Attributes:
        returncode: Exit status, or ``-1`` when the tool did not start or finish.
        output_tail: Last lines of stdout and stderr, not redacted.
    """

    returncode: int
    output_tail: str


def output_tail(stdout: str, stderr: str) -> str:
    """Return the last :data:`CONVERT_TAIL_LINES` lines of stdout, then stderr."""
    text = "\n".join(part.rstrip("\n") for part in (stdout, stderr) if part)
    return "\n".join(text.splitlines()[-CONVERT_TAIL_LINES:])
