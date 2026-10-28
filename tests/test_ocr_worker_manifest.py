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


def test_helper_imports_only_the_standard_library() -> None:
    source = Path(__file__).resolve().parents[1] / "src/omrs/integrations/ocr_worker/manifest.py"
    imports = [
        line.split()[1]
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.startswith(("import ", "from ")) and not line.startswith("from __future__")
    ]
    assert imports
    assert all(name.split(".")[0] in {"re", "pathlib", "typing", "tomllib"} for name in imports)
