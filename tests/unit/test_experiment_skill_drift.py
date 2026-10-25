"""The repository experiment skill stays in step with the package (design D9).

The ``omrs`` package ships the experiment templates.  The repository copy of
the ``s-experiment`` skill keeps a byte-for-byte copy of each one under
``references/``.  This test fails, and names the file, when a copy drifts.

The skill is in a public repository, so a second test scans every skill file
for personal identifiers: home-folder paths, email addresses and the
maintainer's login.
"""

from __future__ import annotations

import hashlib
import re
from importlib.resources import files
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SKILL = _REPO / ".agents" / "skills" / "s-experiment"
_SOURCE_TEMPLATES = _REPO / "src" / "omrs" / "core" / "experiment_records" / "templates"

# Package template name -> skill copy, relative to the skill folder.
TEMPLATE_COPIES: dict[str, str] = {
    "protocol.md": "references/template-protocol.md",
    "report.md": "references/template-report.md",
    "report-quick.md": "references/template-report-quick.md",
    "plan.json": "references/template-plan.json",
    "experiments-agents.md": "references/template-experiments-agents.md",
    "exp-readme.md": "references/template-exp-readme.md",
}

_PERSONAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "macOS home folder": re.compile(r"/Users/[A-Za-z0-9._-]+"),
    "Linux home folder": re.compile(r"/home/[A-Za-z0-9._-]+"),
    "Windows home folder": re.compile(r"[A-Za-z]:\\+Users\\+", re.IGNORECASE),
    "email address": re.compile(r"[\w.%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
}

# SHA-256 of each login to refuse, lower case.  A hash keeps the login itself
# out of this public file.
_LOGIN_SHA256: frozenset[str] = frozenset(
    {"3543428d987d626966fc71660baa84c9b6d24dac0a46f0c892ef4196273c22bc"}
)
_WORD = re.compile(r"[a-z0-9]+")


def package_template_bytes(name: str) -> bytes:
    """Return a template's bytes from the installed package, else the source tree.

    Args:
        name: The template file name inside ``templates/``.

    Returns:
        The file content.
    """
    try:
        resource = files("omrs.core.experiment_records") / "templates" / name
        return resource.read_bytes()
    except (ModuleNotFoundError, FileNotFoundError):
        return (_SOURCE_TEMPLATES / name).read_bytes()


def _sha256(word: str) -> str:
    return hashlib.sha256(word.encode("utf-8")).hexdigest()


def personal_identifier_hits(text: str, login_sha256: frozenset[str] = _LOGIN_SHA256) -> list[str]:
    """Name each kind of personal identifier found in ``text``.

    Args:
        text: The file content.
        login_sha256: SHA-256 digests of the logins to refuse.

    Returns:
        One ``"<kind>: <match>"`` entry per kind found.
    """
    hits = []
    for kind, pattern in _PERSONAL_PATTERNS.items():
        match = pattern.search(text)
        if match:
            hits.append(f"{kind}: {match.group(0)!r}")
    words = set(_WORD.findall(text.lower()))
    if any(_sha256(word) in login_sha256 for word in words):
        hits.append("maintainer login")
    return hits


def test_every_package_template_has_a_skill_copy() -> None:
    shipped = {p.name for p in _SOURCE_TEMPLATES.iterdir() if p.is_file()}
    shipped.discard("__init__.py")
    assert shipped == set(TEMPLATE_COPIES), (
        "TEMPLATE_COPIES must name every package template: "
        f"missing {sorted(shipped - set(TEMPLATE_COPIES))}, "
        f"extra {sorted(set(TEMPLATE_COPIES) - shipped)}"
    )


@pytest.mark.parametrize("template", sorted(TEMPLATE_COPIES))
def test_skill_copy_matches_package_template(template: str) -> None:
    copy = _SKILL / TEMPLATE_COPIES[template]
    assert copy.is_file(), f"skill copy {copy.relative_to(_REPO)} is missing"
    assert copy.read_bytes() == package_template_bytes(template), (
        f"{copy.relative_to(_REPO)} differs from the package template {template}. "
        "Copy the package template over it."
    )


def test_skill_has_no_personal_identifiers() -> None:
    problems = []
    # Bytecode caches are gitignored and never published.
    paths = (p for p in _SKILL.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for path in sorted(paths):
        text = path.read_bytes().decode("utf-8", errors="replace")
        problems += [f"{path.relative_to(_REPO)}: {hit}" for hit in personal_identifier_hits(text)]
    assert not problems, "personal identifiers in the skill: " + "; ".join(problems)


@pytest.mark.parametrize(
    "text",
    [
        "see /Users/someone/notes.md",
        "run from /home/someone/repo",
        r"open C:\Users\someone\repo",
        "mail someone@example.org",
    ],
)
def test_scan_reports_each_kind_of_identifier(text: str) -> None:
    """Guard against a scan that passes everything."""
    assert personal_identifier_hits(text)


def test_scan_reports_a_login_by_its_hash() -> None:
    planted = frozenset({_sha256("someone")})
    hits = personal_identifier_hits("owned by Someone", login_sha256=planted)
    assert hits == ["maintainer login"]
    assert _LOGIN_SHA256, "the login list is empty, so the login scan checks nothing"


def test_scan_allows_ordinary_skill_text() -> None:
    text = "Run `uv run --no-sync omrs experiments check` from the repository root."
    assert personal_identifier_hits(text) == []
