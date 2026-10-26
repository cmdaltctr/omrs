"""Tool version numbers and tested ranges for plugin manifests (design D10)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?")

Version = tuple[int, ...]


def parse_version(text: str) -> Version | None:
    """Return the first dotted version number in ``text``, or ``None``."""
    match = _VERSION_RE.search(text)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups() if part is not None)


def format_version(version: Version) -> str:
    """Return ``version`` as a dotted string."""
    return ".".join(str(part) for part in version)


@dataclass(frozen=True)
class VersionRange:
    """Tested tool versions: ``minimum`` inclusive, ``below`` exclusive."""

    minimum: Version
    below: Version

    def contains(self, version: Version) -> bool:
        """Return whether ``version`` is inside the tested range."""
        return pad_version(self.minimum) <= pad_version(version) < pad_version(self.below)

    def describe(self) -> str:
        """Return the range as text for messages."""
        return f">={format_version(self.minimum)},<{format_version(self.below)}"


def pad_version(version: Version) -> Version:
    """Return ``version`` padded with zeros to four parts, for comparison."""
    return tuple(version) + (0,) * (4 - len(version))
