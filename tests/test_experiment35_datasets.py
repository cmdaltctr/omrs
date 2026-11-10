"""Experiment 35 dataset loading, frozen seeded order, corpus lists and gold scoring.

All data is synthetic, in a tmp folder (``tests/_exp35_fixtures.py``).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from tests._exp35_fixtures import load, make_data_root

datasets35 = load("datasets35")
scoring35 = load("scoring35")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_data_root(tmp_path / "DATA")


# --- the data root -------------------------------------------------------------------


def test_data_root_comes_from_the_environment(tmp_path: Path) -> None:
    assert datasets35.data_root({"EXP35_DATA_DIR": str(tmp_path)}) == tmp_path.resolve()


def test_a_missing_data_root_stops_with_the_variable_named(tmp_path: Path) -> None:
    with pytest.raises(datasets35.DatasetError, match="EXP35_DATA_DIR"):
        datasets35.data_root({"EXP35_DATA_DIR": str(tmp_path / "absent")})


# --- questions and gold --------------------------------------------------------------


def test_financebench_gold_pages_are_converted_to_omrs_labels(root: Path) -> None:
    questions = {q.qid: q for q in datasets35.load_questions("financebench", root)}
    q = questions["financebench_id_00002"]
    # evidence_page_num 2 is zero-indexed, so OMRS stores label "3".
    assert q.gold_pages == {"BETA_2022_10K": ("3",)}
    assert q.relevant == ("BETA_2022_10K#p3",)
    assert q.reference == "answer 2"


def test_freshstack_gold_is_the_parent_ids(root: Path) -> None:
    questions = {q.qid: q for q in datasets35.load_questions("freshstack", root)}
    assert questions["continuity_009"].relevant == ("continuity/zzqj-9097-runbook.md",)
    assert len(questions) == 6


def test_bioasq_gold_passage_ids_are_text(root: Path) -> None:
    questions = {q.qid: q for q in datasets35.load_questions("bioasq", root)}
    assert questions["101"].relevant == ("1001", "1007")
    assert questions["101"].reference == "bio answer 1"


def test_frozen_order_is_seeded_and_does_not_depend_on_file_order(root: Path) -> None:
    questions = datasets35.load_questions("bioasq", root)
    once = [q.qid for q in datasets35.frozen_order(questions, seed=20261101)]
    again = [q.qid for q in datasets35.frozen_order(list(reversed(questions)), seed=20261101)]
    other = [q.qid for q in datasets35.frozen_order(questions, seed=7)]
    assert once == again
    assert sorted(once) == sorted(q.qid for q in questions)
    assert once != other


def test_a_limit_takes_the_head_of_the_frozen_order(root: Path) -> None:
    questions = datasets35.load_questions("freshstack", root)
    full = datasets35.select(questions, None, seed=20261101)
    smoke = datasets35.select(questions, 5, seed=20261101)
    assert [q.qid for q in smoke] == [q.qid for q in full][:5]


# --- corpus lists --------------------------------------------------------------------


def test_full_financebench_corpus_is_every_manifest_pdf(root: Path, tmp_path: Path) -> None:
    files = datasets35.corpus_files("financebench", root, [], None, tmp_path / "work")
    assert [f.name for f in files] == [
        "ACME_2020_10K.pdf",
        "ACME_2021_10K.pdf",
        "BETA_2022_10K.pdf",
        "GAMMA_2023_10K.pdf",
    ]


def test_a_corpus_sample_keeps_every_gold_document_plus_seeded_others(
    root: Path, tmp_path: Path
) -> None:
    questions = datasets35.select(datasets35.load_questions("freshstack", root), 2, seed=1)
    files = datasets35.corpus_files("freshstack", root, questions, 1, tmp_path / "work")
    id_map = datasets35.freshstack_id_map(root)
    parents = {id_map[f.name] for f in files}
    gold = {p for q in questions for p in q.relevant}
    assert gold <= parents
    assert len(parents - gold) == 1


def test_freshstack_full_corpus_adds_the_overlay_runbook(root: Path, tmp_path: Path) -> None:
    files = datasets35.corpus_files("freshstack", root, [], None, tmp_path / "work")
    assert len(files) == 9
    assert datasets35.freshstack_id_map(root)["zzqj-9097-runbook.md"] == (
        "continuity/zzqj-9097-runbook.md"
    )


def test_bioasq_passages_are_written_once_as_files_named_by_id(root: Path, tmp_path: Path) -> None:
    questions = datasets35.select(datasets35.load_questions("bioasq", root), 1, seed=3)
    work = tmp_path / "work"
    files = datasets35.corpus_files("bioasq", root, questions, 2, work)
    assert len(files) == 4  # two gold passages and two others
    assert {f.suffix for f in files} == {".txt"}
    assert set(questions[0].relevant) <= {f.stem for f in files}
    first = {f: f.read_text(encoding="utf-8") for f in files}
    again = datasets35.corpus_files("bioasq", root, questions, 2, work)
    assert {f: f.read_text(encoding="utf-8") for f in again} == first


# --- input hashes --------------------------------------------------------------------


def test_a_changed_input_file_stops_with_both_hashes(root: Path) -> None:
    path = root / "benchmarks" / "financebench" / "financebench_merged.jsonl"
    good = hashlib.sha256(path.read_bytes()).hexdigest()
    datasets35.verify_inputs(root, {"benchmarks/financebench/financebench_merged.jsonl": good})
    with pytest.raises(datasets35.DatasetError, match=good):
        datasets35.verify_inputs(
            root, {"benchmarks/financebench/financebench_merged.jsonl": "f" * 64}
        )


def test_each_financebench_pdf_is_checked_against_its_manifest_hash(
    root: Path, tmp_path: Path
) -> None:
    files = datasets35.corpus_files("financebench", root, [], None, tmp_path / "work")
    expected = datasets35.pdf_hashes(root, files[:1])
    assert expected == {"benchmarks/financebench/pdfs/ACME_2020_10K.pdf": "0" * 64}
    with pytest.raises(datasets35.DatasetError, match="ACME_2020_10K.pdf"):
        datasets35.verify_inputs(root, expected)


def test_every_dataset_names_its_recorded_input_hashes() -> None:
    for name in datasets35.DATASETS:
        assert datasets35.EXPECTED_SHA256[name], name


# --- scoring -------------------------------------------------------------------------


def _row(source: str, pages: list[str] | None = None, name: str = "") -> dict:
    row: dict = {"chunk_id": source + str(pages), "source": source, "score": 1.0}
    if pages is not None:
        row["page_labels"] = pages
    if name:
        row["metadata"] = {"file_name": name}
    return row


def test_financebench_merged_row_spanning_the_gold_page_is_a_hit(root: Path) -> None:
    q = {q.qid: q for q in datasets35.load_questions("financebench", root)}["financebench_id_00002"]
    rows = [_row("/x/ACME_2020_10K.pdf", ["3"]), _row("/x/BETA_2022_10K.pdf", ["2", "3"])]
    metrics = scoring35.question_metrics("financebench", q, rows, {})
    assert metrics["hit_at_page"] is True
    assert metrics["mrr_at_10"] == 0.5
    assert metrics["recall_at_10"] == 1.0


def test_financebench_right_page_in_the_wrong_document_is_no_hit(root: Path) -> None:
    q = {q.qid: q for q in datasets35.load_questions("financebench", root)}["financebench_id_00002"]
    metrics = scoring35.question_metrics(
        "financebench", q, [_row("/x/ACME_2020_10K.pdf", ["3"])], {}
    )
    assert metrics["hit_at_page"] is False
    assert metrics["ndcg_at_10"] == 0.0


def test_freshstack_three_chunks_of_one_parent_count_once_at_its_first_rank(root: Path) -> None:
    q = {q.qid: q for q in datasets35.load_questions("freshstack", root)}["76500001"]
    id_map = datasets35.freshstack_id_map(root)
    rows = [
        _row("a", name="00000_000000000000.md"),
        _row("b", name="00001_000000000001.md"),
        _row("c", name="00001_000000000001.md"),
        _row("d", name="00001_000000000001.md"),
    ]
    metrics = scoring35.question_metrics("freshstack", q, rows, id_map)
    assert metrics["mrr_at_10"] == 0.5
    assert metrics["recall_at_10"] == 1.0
    assert metrics["ndcg_at_10"] == pytest.approx(1 / 1.584962500721156)
    assert "hit_at_page" not in metrics


def test_bioasq_gold_passage_in_the_top_ten_is_a_hit(root: Path) -> None:
    q = {q.qid: q for q in datasets35.load_questions("bioasq", root)}["101"]
    rows = [_row(f"/c/{900 + i}.txt") for i in range(9)] + [_row("/c/1007.txt")]
    metrics = scoring35.question_metrics("bioasq", q, rows, {})
    assert metrics["recall_at_10"] == 0.5
    assert metrics["mrr_at_10"] == 0.1


def test_a_failed_question_scores_zero_and_stays_in_the_denominator() -> None:
    rows = [
        {"qid": "a", "failed": False, "metrics": {"recall_at_10": 1.0, "hit_at_page": True}},
        {"qid": "b", "failed": True, "metrics": scoring35.failed_metrics("financebench")},
    ]
    summary = scoring35.summarise(rows)
    assert summary["n"] == 2
    assert summary["failed"] == 1
    assert summary["recall_at_10"] == 0.5
    assert summary["hit_at_page"] == 0.5
