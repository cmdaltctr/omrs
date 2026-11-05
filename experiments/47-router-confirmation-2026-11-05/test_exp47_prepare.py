"""Step 1 tests: manifest schema, overlap refusal and clean-checkout reproduction.

uv run --no-sync pytest experiments/47-router-confirmation-2026-11-05 -q
"""

from __future__ import annotations

import copy
import json
import shutil

import pytest
from conftest import prepared

import exp47_io
import prepare_inputs

LICENCES = ["public-domain", "cc0", "cc-by", "cc-by-sa"]


# ---------------------------------------------------------------- manifest schema


def test_fake_manifest_is_valid(ws) -> None:
    assert prepare_inputs.validate_manifest(ws.manifest, LICENCES) == []


def test_committed_manifest_holds_the_approved_shortlist() -> None:
    manifest = exp47_io.read_json(exp47_io.EXP_DIR / "corpus_manifest.json")
    assert prepare_inputs.validate_manifest(manifest, LICENCES) == []
    groups = [d["group"] for d in manifest["documents"]]
    assert (groups.count("JUNK"), groups.count("GOOD")) == (10, 9)
    assert all(d["language"] for d in manifest["documents"])


def test_language_is_an_optional_field(ws) -> None:
    manifest = copy.deepcopy(ws.manifest)
    manifest["documents"][0]["language"] = "English handwriting"
    assert prepare_inputs.validate_manifest(manifest, LICENCES) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"group": "MIXED"}, "group must be JUNK or GOOD"),
        ({"licence": "all rights reserved"}, "licence must be one of"),
        ({"sha256": "ABC"}, "sha256 must be 64"),
        ({"page_range": [3, 2]}, "page_range must be"),
        ({"page_range": [True, 2]}, "page_range must be"),
        ({"file": "../escape.pdf"}, "file must be a plain .pdf file name"),
        ({"source_url": "http://example.org/a.pdf"}, "source_url must be an https address"),
        ({"extra": 1}, "extra is not a field"),
        ({"language": ""}, "language must be a non-empty string"),
    ],
)
def test_each_schema_rule(ws, change, problem) -> None:
    manifest = copy.deepcopy(ws.manifest)
    manifest["documents"][0].update(change)
    assert any(problem in p for p in prepare_inputs.validate_manifest(manifest, LICENCES))


def test_repeated_document_is_refused(ws) -> None:
    manifest = copy.deepcopy(ws.manifest)
    manifest["documents"].append(dict(manifest["documents"][0]))
    problems = prepare_inputs.validate_manifest(manifest, LICENCES)
    assert any("appears more than once" in p for p in problems)


# ---------------------------------------------------------------- overlap with 33, 38, 42, 43, 44


def test_prior_documents_come_from_committed_lists(current) -> None:
    seen = prepare_inputs.prior_documents(current, exp47_io.EXPERIMENTS.parent)
    root = exp47_io.EXPERIMENTS.parent
    for entry in current["overlap_sources"]:
        for doc in exp47_io.read_json(root / entry["path"])["documents"]:
            assert doc["sha256"] in seen["sha256"]


@pytest.mark.parametrize("field", ["sha256", "file", "source_url"])
def test_overlap_with_an_earlier_document_is_refused(ws, current, field) -> None:
    exp42 = exp47_io.read_json(exp47_io.EXPERIMENTS.parent / current["overlap_sources"][1]["path"])
    old = exp42["documents"][3]
    manifest = copy.deepcopy(ws.manifest)
    value = {
        "sha256": old["sha256"],
        "file": old["local_path"].rsplit("/", 1)[-1],
        "source_url": old["pdf_url"],
    }[field]
    manifest["documents"][0][field] = value
    ws.MANIFEST.write_text(json.dumps(manifest))
    with pytest.raises(SystemExit, match="matches an earlier"):
        prepare_inputs.checked_manifest(current, exp47_io.EXPERIMENTS.parent, ws.MANIFEST)


def test_changed_overlap_source_stops(ws, current, tmp_path) -> None:
    root = tmp_path / "clone"
    for entry in current["overlap_sources"]:
        target = root / entry["path"]
        target.parent.mkdir(parents=True)
        target.write_text('{"documents": []}')
    with pytest.raises(SystemExit, match="overlap source differs"):
        prepare_inputs.prior_documents(current, root)


# ---------------------------------------------------------------- step 1 output


def test_committed_inputs_hold_hashes_and_private_files_hold_text(ws) -> None:
    payload = prepared(ws)
    row = payload["documents"]["jone"]["rows"][0]
    assert row["markdown_sha256"] == exp47_io.text_sha256(ws.texts["jone.pdf"][0][0])
    committed = ws.INPUTS.read_text()
    assert "INT , L/" not in committed
    assert (ws.PRIVATE / ".gitignore").read_text() == "*\n"
    assert exp47_io.read_json(ws.PRIVATE / "text" / "jone.json")["1"].startswith("junk INT")


def test_changed_pdf_stops(ws) -> None:
    (ws.CORPUS / "gone.pdf").write_bytes(b"%PDF-other")
    with pytest.raises(SystemExit, match="SHA-256 differs"):
        prepared(ws)


# ---------------------------------------------------------------- point 11: clean checkout


def test_resume_after_a_stop_at_step_1(ws) -> None:
    calls = {"n": 0}

    def stopping_scan(pdf):
        calls["n"] += 1
        if calls["n"] == 2:
            raise SystemExit("stopped by the operator")
        return ws.scan(pdf)

    with pytest.raises(SystemExit, match="stopped"):
        prepare_inputs.prepare(
            ws.manifest,
            resume=False,
            ident={"test": 1},
            scan=stopping_scan,
            render=ws.render,
            corpus=ws.CORPUS,
            target=ws.INPUTS,
        )
    assert list(exp47_io.read_json(ws.INPUTS)["documents"]) == ["jone"]
    payload = prepare_inputs.prepare(
        ws.manifest,
        resume=True,
        ident={"test": 1},
        scan=ws.scan,
        render=ws.render,
        corpus=ws.CORPUS,
        target=ws.INPUTS,
    )
    assert sorted(payload["documents"]) == ["gone", "jone"]


def test_fresh_clone_resume_rebuilds_the_private_files(ws) -> None:
    first = prepared(ws)
    shutil.rmtree(ws.PRIVATE)  # a fresh clone has the committed inputs.json only
    again = prepare_inputs.prepare(
        ws.manifest,
        resume=True,
        ident={"test": 1},
        scan=ws.scan,
        render=ws.render,
        corpus=ws.CORPUS,
        target=ws.INPUTS,
    )
    assert again == first
    for doc_id, doc in again["documents"].items():
        assert prepare_inputs.private_files_match(doc_id, doc["rows"])


def test_fresh_clone_with_a_different_reading_stops(ws) -> None:
    prepared(ws)
    shutil.rmtree(ws.PRIVATE)
    ws.texts["jone.pdf"][0] = ("a different reading", False)
    with pytest.raises(SystemExit, match="differ from the committed"):
        prepare_inputs.prepare(
            ws.manifest,
            resume=True,
            ident={"test": 1},
            scan=ws.scan,
            render=ws.render,
            corpus=ws.CORPUS,
            target=ws.INPUTS,
        )


def test_changed_scanner_refuses_resume(ws) -> None:
    prepared(ws)
    with pytest.raises(SystemExit, match="resume refused"):
        prepare_inputs.prepare(
            ws.manifest,
            resume=True,
            ident={"test": 2},
            scan=ws.scan,
            render=ws.render,
            corpus=ws.CORPUS,
            target=ws.INPUTS,
        )
