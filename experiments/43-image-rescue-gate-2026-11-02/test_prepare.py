"""Input-check tests (task 2.2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prepare_inputs  # noqa: E402


def source(tmp_path: Path, freeze_output: str) -> Path:
    (tmp_path / "freeze.py").write_text(f"print({freeze_output!r})\n")
    docs = [{"doc_id": "bd01", "stratum": "born_digital", "local_path": "corpus/natural/bd01.pdf",
             "page_count": 1}]  # fmt: skip
    (tmp_path / "sources.json").write_text(json.dumps({"documents": docs}))
    return tmp_path


def test_missing_pdf_stops_with_its_path(tmp_path) -> None:
    src = source(tmp_path, "freeze verified")
    with pytest.raises(SystemExit) as stop:
        prepare_inputs.check_source(src, {"frozen": [], "source_data": {"pages": 1}})
    assert "missing PDF" in str(stop.value)
    assert str(src / "corpus/natural/bd01.pdf") in str(stop.value)


def test_failed_freeze_check_stops(tmp_path) -> None:
    src = source(tmp_path, "FREEZE VIOLATION")
    with pytest.raises(SystemExit, match="freeze check failed"):
        prepare_inputs.check_source(src, {"frozen": [], "source_data": {"pages": 1}})


def test_page_texts_keeps_empty_liteparse_pages() -> None:
    class Doc:
        def __init__(self, page: int, text: str) -> None:
            self.metadata, self.text = {"page": page}, text

    texts = prepare_inputs.page_texts([Doc(2, " b ")], "liteparse", 3, str.strip)
    assert texts == ["", "b", ""]
    with pytest.raises(ValueError):
        prepare_inputs.page_texts([Doc(2, "a"), Doc(2, "b")], "liteparse", 3, str.strip)
