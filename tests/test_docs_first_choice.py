"""Docs put the llama.cpp router first and Ollama in its own opt-in section (change 8.4).

A reader who follows the README, the getting-started guide or the provider guide
from the top must not meet an instruction to install or start Ollama. Ollama
stays documented, under a heading that names it. No guide tells the reader to set
a retired llama.cpp address or server variable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from omrs.config.legacy import RETIRED_ROUTER_KEYS

ROOT = Path(__file__).resolve().parent.parent
FIRST_CHOICE_DOCS = (
    "README.md",
    "docs/guides/getting-started.md",
    "docs/guides/providers.md",
    "docs/guides/configuration.md",
    "docs/guides/web-workspace.md",
    "docs/guides/ingestion.md",
)
#: Docs that must carry a section of their own for Ollama.
OLLAMA_SECTION_DOCS = ("README.md", "docs/guides/getting-started.md", "docs/guides/providers.md")

#: Instructions to install, start or pull with Ollama.
OLLAMA_STEP = re.compile(
    r"\bollama\s+(?:pull|serve|run)\b|(?i:install\s+ollama)|brew\s+install\s+ollama|ollama\.com/install"
)
#: A line that sets the embedding model to an Ollama tag. The default is a GGUF name.
OLLAMA_TAG = re.compile(
    r"""(?:EMBED_MODEL\s*=|"embed_model"\s*:)\s*"?(?:qwen3-embedding:\d|nomic-embed-text|mxbai)"""
)
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE = re.compile(r"^\s*```")


def sections(text: str) -> list[tuple[str, list[tuple[int, str]]]]:
    """Split *text* into ``(heading, [(line number, line)])`` sections.

    A heading line inside a fenced block (a shell comment) is not a heading.
    """
    found: list[tuple[str, list[tuple[int, str]]]] = [("", [])]
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            fenced = not fenced
        match = None if fenced else HEADING.match(line)
        if match:
            found.append((match.group(2), []))
        found[-1][1].append((number, line))
    return found


def ollama_free_sections(text: str) -> list[tuple[str, list[tuple[int, str]]]]:
    """Return the sections whose heading does not name Ollama.

    A section that follows an Ollama heading at a deeper level belongs to it.
    """
    kept = []
    inside = None
    for heading, lines in sections(text):
        level = len(re.match(r"#*", lines[0][1]).group(0)) if heading else 0  # type: ignore[union-attr]
        if "ollama" in heading.lower():
            inside = level
            continue
        if inside is not None and level > inside:
            continue
        inside = None
        kept.append((heading, lines))
    return kept


def first_choice_findings(text: str) -> list[str]:
    """Return the lines that tell a reader to use Ollama outside an Ollama section."""
    found = []
    for heading, lines in ollama_free_sections(text):
        for number, line in lines:
            if OLLAMA_STEP.search(line) or OLLAMA_TAG.search(line):
                found.append(f"line {number} (section {heading!r}): {line.strip()[:90]}")
    return found


@pytest.mark.parametrize("name", FIRST_CHOICE_DOCS)
def test_no_instruction_to_use_ollama_outside_its_own_section(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    assert first_choice_findings(text) == []


@pytest.mark.parametrize("name", OLLAMA_SECTION_DOCS)
def test_ollama_has_an_opt_in_section(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    headings = [h for h, _ in sections(text) if "ollama" in h.lower()]
    assert headings, f"{name} has no heading that names Ollama"
    section_text = "\n".join(
        line for h, lines in sections(text) if "ollama" in h.lower() for _, line in lines
    )
    assert "opt-in" in section_text.lower() or "opt in" in section_text.lower()


@pytest.mark.parametrize("name", FIRST_CHOICE_DOCS)
def test_no_guide_assigns_a_retired_router_variable(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    for retired in RETIRED_ROUTER_KEYS:
        assert not re.search(rf"^\s*#?\s*(?:export\s+)?{retired}\s*=", text, re.MULTILINE), retired


@pytest.mark.parametrize("name", ("README.md", "docs/guides/getting-started.md"))
def test_install_steps_name_the_router_command(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    assert "omrs llamacpp install" in text


# The cases below pin the scanner.


@pytest.mark.parametrize(
    "line",
    [
        "ollama serve &",
        "ollama pull qwen3-embedding:0.6b",
        "brew install ollama",
        "Install Ollama from the site first.",
        "EMBED_MODEL=nomic-embed-text",
        '"embed_model": "qwen3-embedding:0.6b"',
    ],
)
def test_the_scanner_finds_an_ollama_first_step(line: str) -> None:
    assert first_choice_findings(f"## Install\n\n{line}\n")


def test_the_scanner_allows_the_same_line_under_an_ollama_heading() -> None:
    text = (
        "## Install\n\nRun the router.\n\n"
        "## Ollama (opt-in)\n\nollama serve &\n\n### Pull\n\nollama pull x\n"
    )
    assert first_choice_findings(text) == []


def test_a_shell_comment_in_a_fence_is_not_a_heading() -> None:
    text = "## Install\n\n```bash\n# Ollama\nollama serve &\n```\n"
    assert first_choice_findings(text)
