"""Adding Indra touches only its own part (change local-ocr-backends, task 7.4, D19).

The text ``indra`` (any case) may appear in product code under ``src/omrs/`` and
``web/src/`` only in three places: the backend module ``local_ocr/indra.py``, its
``register()`` call in ``local_ocr/registry.py`` and its descriptor entry in
``core/reading_parts.py``. The catalogue and health rows derive from the
descriptor, so they need no mention.

Front-end test files (``*.test.*``) are not product code; their fixtures name a
backend ``indra`` and stay out of the check. Built web assets
(``transports/api/static/``) are gitignored output and stay out too.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = (ROOT / "src" / "omrs", ROOT / "web" / "src")
BACKEND = ROOT / "src/omrs/integrations/pdf/local_ocr/indra.py"
REGISTRY = ROOT / "src/omrs/integrations/pdf/local_ocr/registry.py"
READING_PARTS = ROOT / "src/omrs/core/reading_parts.py"
SKIPPED_DIRS = {"__pycache__", "node_modules", "static"}
WORD = re.compile("indra", re.IGNORECASE)


def _call_lines(path: Path, function: str, matches) -> set[int]:
    """Return the line numbers of every ``function(...)`` call that *matches*."""
    lines: set[int] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id == function and matches(node):
            lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return lines


def _first_arg_is_indra(node: ast.Call) -> bool:
    first = node.args[0] if node.args else None
    return isinstance(first, ast.Constant) and first.value == "indra"


def _named_indra(node: ast.Call) -> bool:
    return any(
        kw.arg == "name" and isinstance(kw.value, ast.Constant) and kw.value.value == "indra"
        for kw in node.keywords
    )


def _product_files():
    for root in SCANNED:
        for path in sorted(root.rglob("*")):
            parts = set(path.relative_to(root).parts)
            if not path.is_file() or parts & SKIPPED_DIRS or ".test." in path.name:
                continue
            yield path


def _hits(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:  # a binary asset holds no source text
        return []
    return [(n, line) for n, line in enumerate(text.splitlines(), 1) if WORD.search(line)]


def test_indra_appears_only_in_its_own_part() -> None:
    register_lines = _call_lines(REGISTRY, "register", _first_arg_is_indra)
    descriptor_lines = _call_lines(READING_PARTS, "LocalOcrBackendDescriptor", _named_indra)
    assert register_lines, "no register('indra', ...) call in local_ocr/registry.py"
    assert descriptor_lines, "no LocalOcrBackendDescriptor(name='indra') in reading_parts.py"
    allowed = {REGISTRY: register_lines, READING_PARTS: descriptor_lines}

    outside = []
    for path in _product_files():
        if path == BACKEND:
            continue
        for number, line in _hits(path):
            if number not in allowed.get(path, set()):
                outside.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    assert outside == [], "indra outside its own part:\n" + "\n".join(outside)


def test_the_backend_module_exists() -> None:
    assert BACKEND.is_file()
