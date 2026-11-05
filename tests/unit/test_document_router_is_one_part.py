"""Adding the router touches only its own part (change document-reading-routers, task 3.3).

The router is one page rule: its module ``page_rules/document_router.py``, one
``PageRuleDescriptor`` entry in ``core/reading_parts.py`` and one ``register()``
line in ``page_rules/registry.py``. Two checks hold that shape, modelled on
``test_indra_is_one_part.py``:

1. No product module under ``src/omrs/`` or ``web/src/`` names the rule module
   (an import path or an import) outside the descriptor entry and the
   ``register()`` call. The page unit therefore has no call to the rule.
2. Under ``integrations/pdf/`` the name ``document_router`` appears only in the
   rule module and its ``register()`` call.

The setting ``document_router`` is a plain settings key, so settings code,
identity builders, the HTTP contract and the front end may name it. They may
not import the rule.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from omrs.core import reading_parts

ROOT = Path(__file__).resolve().parents[2]
SCANNED = (ROOT / "src" / "omrs", ROOT / "web" / "src")
PDF = ROOT / "src/omrs/integrations/pdf"
RULE_MODULE = PDF / "page_rules/document_router.py"
REGISTRY = PDF / "page_rules/registry.py"
READING_PARTS = ROOT / "src/omrs/core/reading_parts.py"
SKIPPED_DIRS = {"__pycache__", "node_modules", "static"}
MODULE_REF = re.compile(r"page_rules(\.| import )document_router")
NAME = re.compile("document_router")


def _call_lines(path: Path, function: str, matches) -> set[int]:
    """Return the line numbers of every ``function(...)`` call that *matches*."""
    lines: set[int] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id == function and matches(node):
            lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return lines


def _first_arg_is_router(node: ast.Call) -> bool:
    first = node.args[0] if node.args else None
    return isinstance(first, ast.Constant) and first.value == "document_router"


def _named_router(node: ast.Call) -> bool:
    return any(
        kw.arg == "name"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value == "document_router"
        for kw in node.keywords
    )


def _files(roots):
    for root in roots:
        for path in sorted(root.rglob("*")):
            parts = set(path.relative_to(root).parts)
            if not path.is_file() or parts & SKIPPED_DIRS or ".test." in path.name:
                continue
            yield path


def _hits(path: Path, pattern: re.Pattern[str]) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:  # a binary asset holds no source text
        return []
    return [(n, line) for n, line in enumerate(text.splitlines(), 1) if pattern.search(line)]


def _allowed() -> dict[Path, set[int]]:
    register_lines = _call_lines(REGISTRY, "register", _first_arg_is_router)
    descriptor_lines = _call_lines(READING_PARTS, "PageRuleDescriptor", _named_router)
    assert register_lines, "no register('document_router', ...) call in page_rules/registry.py"
    assert descriptor_lines, "no PageRuleDescriptor(name='document_router') in reading_parts.py"
    return {REGISTRY: register_lines, READING_PARTS: descriptor_lines}


def _outside(roots, pattern: re.Pattern[str]) -> list[str]:
    allowed = _allowed()
    found = []
    for path in _files(roots):
        if path == RULE_MODULE:
            continue
        for number, line in _hits(path, pattern):
            if number not in allowed.get(path, set()):
                found.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    return found


def test_no_product_module_names_the_rule_module_outside_its_part() -> None:
    outside = _outside(SCANNED, MODULE_REF)
    assert outside == [], "rule module named outside its own part:\n" + "\n".join(outside)


def test_the_pdf_package_names_the_router_only_in_its_part() -> None:
    outside = _outside((PDF,), NAME)
    assert outside == [], "document_router outside its own part:\n" + "\n".join(outside)


def test_the_descriptor_declares_order_40_and_adds_pages() -> None:
    rule = reading_parts.by_name(reading_parts.PAGE_RULES, "document_router")

    assert rule.order == 40
    assert (rule.adds_pages, rule.has_degrade) == (True, True)
    assert rule.import_path == "omrs.integrations.pdf.page_rules.document_router:RULE"


def test_the_rule_module_exists() -> None:
    assert RULE_MODULE.is_file()
