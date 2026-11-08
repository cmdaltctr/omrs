"""Tests for ``prepare_financebench.py`` (PR 195 review fix, CodeRabbit 2026-11-08).

Run with: uv run --no-sync pytest test_prepare_financebench.py -q

Tmp folders and one blank PDF only. Nothing reads ``~/Development/DATA``.
"""

from __future__ import annotations

import json

import prepare_financebench as pf
import pytest
from pypdf import PdfWriter
from sweep_lib import file_sha256, stray_files


def test_stray_files_lists_names_outside_the_wanted_set(tmp_path):
    (tmp_path / "keep.pdf").write_text("k", encoding="utf-8")
    (tmp_path / "old.pdf").write_text("o", encoding="utf-8")
    assert stray_files(tmp_path, ["keep.pdf"]) == ["old.pdf"]


def test_stray_files_of_a_missing_folder_is_empty(tmp_path):
    assert stray_files(tmp_path / "none", ["keep.pdf"]) == []


@pytest.fixture
def source(tmp_path, monkeypatch):
    """A one-document FinanceBench source and an empty experiment folder."""
    pdfs = tmp_path / "src" / "pdfs"
    pdfs.mkdir(parents=True)
    writer = PdfWriter()
    writer.add_blank_page(72, 72)
    with (pdfs / "DOC.pdf").open("wb") as handle:
        writer.write(handle)
    question = {"financebench_id": "q1", "doc_name": "DOC", "question": "?", "evidence": []}
    (tmp_path / "src" / "q.jsonl").write_text(json.dumps(question) + "\n", encoding="utf-8")
    manifest = {"files": {"DOC": {"sha256": file_sha256(pdfs / "DOC.pdf"), "bytes": 1}}}
    (tmp_path / "src" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    here = tmp_path / "exp"
    here.mkdir()
    monkeypatch.setattr(pf, "HERE", here)
    monkeypatch.setattr(pf, "PDFS", pdfs)
    monkeypatch.setattr(pf, "QUESTIONS", tmp_path / "src" / "q.jsonl")
    monkeypatch.setattr(pf, "MANIFEST", tmp_path / "src" / "manifest.json")
    return here / "output" / "financebench" / "pdfs"


def test_an_empty_output_folder_is_prepared(source):
    pf.main()
    assert [p.name for p in source.iterdir()] == ["DOC.pdf"]


def test_a_pdf_left_from_an_earlier_run_stops_the_preparation(source):
    source.mkdir(parents=True)
    (source / "STALE.pdf").write_text("old", encoding="utf-8")
    with pytest.raises(SystemExit, match="STALE.pdf"):
        pf.main()
    assert not (source / "DOC.pdf").exists()
