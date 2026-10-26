"""The experiments folder guide stands alone (experiment-format-v1, task 8.1).

``experiments/AGENTS.md`` must not link outside the repository: a reader of a
clone, or of the public repository, has no access to anything else.  Every
Markdown link must resolve to an existing path inside the repository.
``experiments/CLAUDE.md`` is a relative symbolic link to the guide.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_GUIDE = _REPO / "experiments" / "AGENTS.md"

_FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
_CODE_SPAN = re.compile(r"`[^`\n]*`")
_INLINE_LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*<?([^)\s>]*)>?(?:\s+\"[^\"]*\")?\s*\)")
_REFERENCE_DEF = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s*<?(\S+?)>?(?:\s|$)", re.MULTILINE)
_AUTOLINK = re.compile(r"<([a-zA-Z][a-zA-Z0-9+.-]*:[^>\s]*)>")
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def link_targets(markdown: str) -> list[str]:
    """Return every link target in ``markdown``, outside code fences and spans.

    Args:
        markdown: The Markdown source.

    Returns:
        The targets of inline links, images, reference definitions and
        autolinks, in the order they appear.
    """
    text = _CODE_SPAN.sub("", _FENCE.sub("", markdown))
    targets = [m.group(1) for m in _INLINE_LINK.finditer(text)]
    targets += [m.group(1) for m in _REFERENCE_DEF.finditer(text)]
    targets += [m.group(1) for m in _AUTOLINK.finditer(text)]
    return targets


def outside_repo_problem(target: str, base: Path, repo: Path) -> str | None:
    """Explain why ``target`` leaves the repository, or return ``None``.

    Args:
        target: One link target from the guide.
        base: The folder that holds the guide.
        repo: The repository root.

    Returns:
        A plain message for a bad link, else ``None``.
    """
    if not target or target.startswith("#"):
        return None
    if _SCHEME.match(target) or target.startswith("//"):
        return f"{target!r} points outside the repository (it has a scheme or host)"
    if target.startswith("/") or target.startswith("~"):
        return f"{target!r} is an absolute path; use a path relative to the guide"
    path_part = target.split("#", 1)[0].split("?", 1)[0]
    resolved = (base / path_part).resolve()
    if not resolved.is_relative_to(repo):
        return f"{target!r} resolves to a path outside the repository"
    if not resolved.exists():
        return f"{target!r} resolves to {resolved.relative_to(repo)}, which does not exist"
    return None


def test_guide_exists_and_claude_md_links_to_it() -> None:
    assert _GUIDE.is_file(), "experiments/AGENTS.md is missing"
    link = _GUIDE.parent / "CLAUDE.md"
    assert link.is_symlink(), "experiments/CLAUDE.md must be a symbolic link"
    assert os.readlink(link) == "AGENTS.md"


def test_every_guide_link_stays_inside_the_repository() -> None:
    targets = link_targets(_GUIDE.read_text(encoding="utf-8"))
    assert targets, "the guide has no links, so this test checks nothing"
    problems = [p for t in targets if (p := outside_repo_problem(t, _GUIDE.parent, _REPO))]
    assert not problems, "experiments/AGENTS.md: " + "; ".join(problems)


@pytest.mark.parametrize(
    "target",
    [
        "https://example.org/guide",
        "mailto:someone@example.org",
        "/etc/hosts",
        "~/notes.md",
        "../../outside.md",
        "missing-file.md",
    ],
)
def test_a_link_that_leaves_the_repository_is_reported(target: str) -> None:
    """Guard against a checker that passes everything."""
    assert outside_repo_problem(target, _GUIDE.parent, _REPO) is not None


def test_links_inside_code_are_not_read() -> None:
    markdown = "See `[x](https://example.org)`.\n\n```\n[y](/abs)\n```\n[ok](EXP_README.md)\n"
    assert link_targets(markdown) == ["EXP_README.md"]


def test_guide_states_the_edit_rule() -> None:
    """The finished-record rule names the editable files and the edit log (ADR-102)."""
    text = _GUIDE.read_text(encoding="utf-8")
    assert (
        "change only `experiment.json`, `protocol.md` and the report file "
        "(`report.md`, or `results.md` in an older folder without `report.md`)" in text
    )
    assert "Never change or remove a line in `edits.jsonl`." in text
    assert "change only `experiment.json`. Never edit" not in text
