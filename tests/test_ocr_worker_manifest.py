"""The shared OCR engine manifest reader (change integrations-show-runtime-components, D1).

``provision.py`` and the Integrations runtime probe read ``[tool.omrs-ocr]``
from one helper, so the licence step they report cannot differ.
"""

from __future__ import annotations

from pathlib import Path

from omrs.integrations.ocr_worker.manifest import engine_manifest, licence_gate, minimal_toml

LICENSED = """\
[project]
name = "omrs-ocr-engine-demo"

[tool.omrs-ocr]
requires-acceptance = true
licence-file = "LICENCE-NOTES.md"
"""


def test_licence_engine_gives_its_licence_file(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(LICENSED, encoding="utf-8")

    assert licence_gate(engine_manifest(tmp_path)) == (True, "LICENCE-NOTES.md")


def test_engine_without_the_table_needs_no_acceptance(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")

    assert licence_gate(engine_manifest(tmp_path)) == (False, None)


def test_minimal_reader_matches_tomllib_for_the_gate() -> None:
    assert licence_gate(minimal_toml(LICENSED)) == (True, "LICENCE-NOTES.md")


# The standard-library-only rule is checked by an AST test in
# tests/test_ocr_manifest_runtime.py (function-local imports included).
