"""Experiment 35 dataset loaders, frozen order, named questions and prepared passage files.

All data is synthetic, in a tmp folder (``tests/_exp35_fixtures.py``). Rules
under test: tasks 13.4 (Legal RAG Bench), 13.5 (FreshStack 203 queries on the
full corpus, export format), 13.5a (BioASQ passages as ``.md``), 5.4c
(passage files prepared once, outside the output folder, with a tree hash)
and 5.3 (``--qids``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tests._exp35_fixtures import FS_ROWS, FS_ROWS_DATA, fake_plan, load, make_data_root, unpin

from omrs.core.chunking.model_token import _heading_positions

datasets35 = load("datasets35")
prepare35 = load("prepare35")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_data_root(tmp_path / "DATA")


def _pin() -> dict:
    return fake_plan()["pins"]["datasets"]["freshstack"]


# --- root and hashes ---------------------------------------------------------------------


def test_data_root_comes_from_the_environment(tmp_path: Path) -> None:
    assert datasets35.data_root({"EXP35_DATA_DIR": str(tmp_path)}) == tmp_path.resolve()


def test_a_missing_data_root_stops_with_the_variable_named(tmp_path: Path) -> None:
    with pytest.raises(datasets35.DatasetError, match="EXP35_DATA_DIR"):
        datasets35.data_root({"EXP35_DATA_DIR": str(tmp_path / "absent")})


def test_a_changed_input_file_stops_and_names_it(root: Path) -> None:
    path = root / "benchmarks" / "financebench" / "financebench_merged.jsonl"
    good = hashlib.sha256(path.read_bytes()).hexdigest()
    datasets35.verify_inputs(root, {"benchmarks/financebench/financebench_merged.jsonl": good})
    with pytest.raises(datasets35.DatasetError, match="financebench_merged.jsonl"):
        datasets35.verify_inputs(
            root, {"benchmarks/financebench/financebench_merged.jsonl": "0" * 64}
        )


def test_a_null_dataset_pin_is_refused_and_names_its_key_and_task(
    root: Path, tmp_path: Path
) -> None:
    def unpinned(dataset: str, key: str, task: str) -> dict:
        plan = fake_plan()
        plan["pins"]["datasets"].setdefault(dataset, {})[key] = "x"
        return unpin(plan, f"pins.datasets.{dataset}.{key}", task)

    legal = unpinned("legal", "sha256", "RDY 13.4")
    with pytest.raises(datasets35.DatasetError, match=r"pins\.datasets\.legal\.sha256.*RDY 13.4"):
        datasets35.input_hashes("legal", legal)
    fresh = unpinned("freshstack", "revision", "P1")
    with pytest.raises(datasets35.DatasetError, match=r"pins\.datasets\.freshstack\.revision.*P1"):
        datasets35.freshstack_pin(fresh)
    folder = prepare35.prepare("bioasq", root, tmp_path / "passages", plan=fake_plan())
    assert folder.is_dir()
    tree = unpinned("bioasq", "passages_tree_sha256", "RDY 5.4c")
    with pytest.raises(datasets35.DatasetError, match=r"bioasq\.passages_tree_sha256.*RDY 5.4c"):
        datasets35.check_passages(tmp_path / "passages", "bioasq", tree)


def test_legal_input_hashes_come_from_the_plan_and_a_missing_pin_is_named(root: Path) -> None:
    plan = fake_plan()
    with pytest.raises(datasets35.DatasetError, match=r"pins\.datasets\.legal\.sha256"):
        datasets35.input_hashes("legal", plan)
    plan["pins"]["datasets"]["legal"] = {"sha256": {"benchmarks/legal-rag-bench/qa/x": "1" * 64}}
    assert datasets35.input_hashes("legal", plan) == {"benchmarks/legal-rag-bench/qa/x": "1" * 64}
    assert datasets35.input_hashes("bioasq", plan) == datasets35.EXPECTED_SHA256["bioasq"]


def test_no_overlay_or_continuity_reference_is_left() -> None:
    source = datasets35.__file__ and Path(datasets35.__file__).read_text("utf-8")
    assert "_FS_OVERLAY" not in source
    assert "continuity/*.md" not in source
    assert not any("overlay" in rel for rel in datasets35.EXPECTED_SHA256["freshstack"])


# --- questions and gold --------------------------------------------------------------------


def test_financebench_gold_pages_are_converted_to_omrs_labels(root: Path) -> None:
    questions = {q.qid: q for q in datasets35.load_questions("financebench", root)}
    q = questions["financebench_id_00002"]
    assert q.gold_pages == {"BETA_2022_10K": ("3",)}
    assert q.relevant == ("BETA_2022_10K#p3",)


def test_freshstack_drops_continuity_queries_and_sends_title_then_body(root: Path) -> None:
    questions = {q.qid: q for q in datasets35.load_questions("freshstack", root)}
    assert len(questions) == 5
    assert not any(qid.startswith("continuity") for qid in questions)
    q = questions["76500001"]
    assert q.text == "FreshStack title 1\n\nFreshStack body 1?"
    assert q.relevant == (FS_ROWS_DATA[1][0],)


def test_bioasq_gold_is_the_passage_ids(root: Path) -> None:
    q = {q.qid: q for q in datasets35.load_questions("bioasq", root)}["101"]
    assert q.relevant == ("1001", "1007")


def test_legal_has_100_questions_with_one_gold_passage(root: Path) -> None:
    questions = datasets35.load_questions("legal", root)
    assert len(questions) == 100
    first = {q.qid: q for q in questions}["lq007"]
    assert first.relevant == ("lp007",)
    assert first.reference == "legal answer 7"


def test_legal_refuses_a_question_whose_gold_passage_is_missing(root: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    corpus = root / "benchmarks" / "legal-rag-bench" / "corpus" / "test-00000-of-00001.parquet"
    table = pq.read_table(corpus)
    pq.write_table(table.filter(pa.compute.not_equal(table["id"], "lp042")), corpus)
    with pytest.raises(datasets35.DatasetError, match="lp042"):
        datasets35.load_questions("legal", root)


def test_legal_refuses_a_qa_file_of_another_size(root: Path) -> None:
    import pyarrow.parquet as pq

    qa = root / "benchmarks" / "legal-rag-bench" / "qa" / "test-00000-of-00001.parquet"
    pq.write_table(pq.read_table(qa).slice(0, 99), qa)
    with pytest.raises(datasets35.DatasetError, match="99"):
        datasets35.load_questions("legal", root)


def test_a_question_with_no_gold_is_refused_and_named(root: Path) -> None:
    path = root / "experiments" / "22-raw-query-qwen4b-baseline-2026-09-07" / "ground-truth.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["queries"][2]["relevant_parent_ids"] = []
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(datasets35.DatasetError, match="76500002"):
        datasets35.load_questions("freshstack", root)


# --- frozen order and named questions (task 5.3) -----------------------------------------


def test_frozen_order_is_seeded_and_independent_of_file_order(root: Path) -> None:
    questions = datasets35.load_questions("bioasq", root)
    first = [q.qid for q in datasets35.frozen_order(questions, seed=20261101)]
    again = [q.qid for q in datasets35.frozen_order(list(reversed(questions)), seed=20261101)]
    assert first == again
    assert first != [q.qid for q in datasets35.frozen_order(questions, seed=7)]


def test_named_questions_keep_the_frozen_order(root: Path) -> None:
    questions = datasets35.load_questions("freshstack", root)
    order = [q.qid for q in datasets35.frozen_order(questions, seed=20261101)]
    wanted = [order[3], order[1]]
    picked = datasets35.select(questions, None, seed=20261101, qids=wanted)
    assert [q.qid for q in picked] == [order[1], order[3]]


def test_an_unknown_question_id_is_refused_and_named(root: Path) -> None:
    questions = datasets35.load_questions("freshstack", root)
    with pytest.raises(datasets35.DatasetError, match="99999999"):
        datasets35.select(questions, None, seed=1, qids=["76500001", "99999999"])


def test_limit_takes_the_head_of_the_frozen_order(root: Path) -> None:
    questions = datasets35.load_questions("bioasq", root)
    full = datasets35.select(questions, None, seed=20261101)
    assert [q.qid for q in datasets35.select(questions, 2, seed=20261101)] == [
        q.qid for q in full[:2]
    ]


# --- FreshStack corpus pin and export (task 13.5) -----------------------------------------


def test_freshstack_corpus_matches_its_pin(root: Path) -> None:
    rows = datasets35.freshstack_corpus(root, _pin())
    assert [r[0] for r in rows] == [r[0] for r in FS_ROWS_DATA]


@pytest.mark.parametrize(("field", "value"), [("revision", "other"), ("rows", FS_ROWS + 1)])
def test_freshstack_corpus_refuses_another_revision_or_row_count(
    root: Path, field: str, value: object
) -> None:
    with pytest.raises(datasets35.DatasetError, match=field):
        datasets35.freshstack_corpus(root, {**_pin(), field: value})


def test_markdown_rows_are_written_unchanged_and_others_are_fenced() -> None:
    assert prepare35.export_row("repo/README.md_0_40", "# Title\n") == ("# Title\n", ".md", False)
    assert prepare35.export_row("repo/guide.mdx_0_9", "x\n")[1:] == (".mdx", False)
    text, ext, fenced = prepare35.export_row("repo/LICENSE_0_10", "MIT\n")
    assert (ext, fenced) == ("", True)
    assert text == "```\nMIT\n```\n"
    assert prepare35.export_row("nb/demo.ipynb_0_3", "{}")[0] == "```\n{}\n```\n"


def test_a_fence_is_one_backtick_longer_than_the_longest_run_in_the_row() -> None:
    text, _, _ = prepare35.export_row("a/x.py_0_9", "s = '````'\n```\n# h\n")
    assert text.startswith("`````\n") and text.endswith("\n`````\n")


def test_a_fenced_python_row_gives_no_heading_on_the_markdown_path() -> None:
    row = "# a comment\nprint('x')\n```\n# inside a fence line\n```\n# last\n"
    text, _, fenced = prepare35.export_row("repo/src/app.py_0_60", row)
    assert fenced
    assert _heading_positions(text) == []


def test_an_exported_row_holds_no_front_matter_or_url_of_the_exporter() -> None:
    text, _, _ = prepare35.export_row("repo/src/util.py_60_90", "def f():\n    return 1\n")
    assert not text.startswith("---")
    assert "repo/src/util.py" not in text
    assert "http" not in text


# --- prepared passage files (tasks 5.4c, 13.4, 13.5a) -----------------------------------


def test_bioasq_passages_are_md_files_with_escaped_headings(root: Path, tmp_path: Path) -> None:
    folder = prepare35.prepare("bioasq", root, tmp_path / "passages", plan=fake_plan())
    path = folder / "1003.md"
    assert path.read_text(encoding="utf-8") == "abstract 3\n\\# not a heading\n"
    assert not list(folder.glob("*.txt"))
    assert _heading_positions(path.read_text(encoding="utf-8")) == []
    gold = {q.qid: q for q in datasets35.load_questions("bioasq", root)}["103"].relevant
    assert all((folder / f"{passage}.md").is_file() for passage in gold)


def test_legal_passages_hold_title_text_and_footnotes(root: Path, tmp_path: Path) -> None:
    folder = prepare35.prepare("legal", root, tmp_path / "passages", plan=fake_plan())
    assert (folder / "lp001.md").read_text(encoding="utf-8") == (
        "Section 1\n\nText of passage 1.\n\\#5 is a number\n\nFootnote 1.\n"
    )
    assert (folder / "lp002.md").read_text(encoding="utf-8") == (
        "Section 2\n\nText of passage 2.\n\\#5 is a number\n"
    )
    assert len(list(folder.glob("*.md"))) == 101


def test_freshstack_export_writes_a_manifest_with_extension_and_fence(
    root: Path, tmp_path: Path
) -> None:
    folder = prepare35.prepare("freshstack", root, tmp_path / "passages", plan=fake_plan())
    manifest = [json.loads(line) for line in (folder / "manifest.jsonl").read_text().splitlines()]
    by_id = {row["freshstack_id"]: row for row in manifest}
    assert by_id["repo/README.md_0_40"]["extension"] == ".md"
    assert by_id["repo/README.md_0_40"]["fenced"] is False
    assert by_id["repo/LICENSE_0_10"]["fenced"] is True
    stem = by_id["repo/src/app.py_0_60"]["file"].removesuffix(".md")
    assert datasets35.freshstack_unit_map(folder)[stem] == "repo/src/app.py_0_60"


def test_preparation_writes_a_tree_hash_and_verify_accepts_it(root: Path, tmp_path: Path) -> None:
    folder = prepare35.prepare("bioasq", root, tmp_path / "passages", plan=fake_plan())
    tree = json.loads((folder / "passages-tree.json").read_text(encoding="utf-8"))
    assert set(tree["files"]) == {f"{1000 + i}.md" for i in range(12)}
    assert datasets35.verify_tree(folder) == tree["tree_sha256"]


def test_verify_tree_refuses_a_changed_file_and_names_it(root: Path, tmp_path: Path) -> None:
    folder = prepare35.prepare("bioasq", root, tmp_path / "passages", plan=fake_plan())
    (folder / "1004.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(datasets35.DatasetError, match="1004.md"):
        datasets35.verify_tree(folder)


def test_a_second_preparation_reuses_equal_files_and_refuses_a_changed_one(
    root: Path, tmp_path: Path
) -> None:
    first = prepare35.prepare("bioasq", root, tmp_path / "passages", plan=fake_plan())
    tree = (first / "passages-tree.json").read_text(encoding="utf-8")
    assert prepare35.prepare("bioasq", root, tmp_path / "passages", plan=fake_plan()) == first
    assert (first / "passages-tree.json").read_text(encoding="utf-8") == tree
    (first / "1002.md").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(datasets35.DatasetError, match="1002.md"):
        prepare35.prepare("bioasq", root, tmp_path / "passages", plan=fake_plan())


def test_an_interrupted_preparation_refuses_a_changed_file_before_any_record(
    root: Path, tmp_path: Path
) -> None:
    folder = prepare35.prepare("bioasq", root, tmp_path / "passages", plan=fake_plan())
    (folder / "passages-tree.json").unlink()
    (folder / "1002.md").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(datasets35.DatasetError, match="1002.md"):
        prepare35.prepare("bioasq", root, tmp_path / "passages", plan=fake_plan())
    assert not (folder / "passages-tree.json").exists()


def test_preparation_leaves_no_temporary_file(root: Path, tmp_path: Path) -> None:
    folder = prepare35.prepare("legal", root, tmp_path / "passages", plan=fake_plan())
    assert not [p.name for p in folder.iterdir() if p.name.endswith(".tmp")]


# --- corpus files for an ingest ---------------------------------------------------------


def test_financebench_corpus_is_every_pdf_in_name_order(root: Path, tmp_path: Path) -> None:
    files = datasets35.corpus_files("financebench", root, [], None, tmp_path / "p", seed=1)
    assert [f.name for f in files] == [
        "ACME_2020_10K.pdf",
        "ACME_2021_10K.pdf",
        "BETA_2022_10K.pdf",
        "GAMMA_2023_10K.pdf",
    ]


def test_passage_corpus_files_come_only_from_the_prepared_folder(
    root: Path, tmp_path: Path
) -> None:
    passages = tmp_path / "passages"
    prepare35.prepare("bioasq", root, passages, plan=fake_plan())
    files = datasets35.corpus_files("bioasq", root, [], None, passages, seed=1)
    assert len(files) == 12
    assert {f.parent for f in files} == {passages / "bioasq"}


def test_a_corpus_sample_keeps_every_gold_passage_plus_seeded_others(
    root: Path, tmp_path: Path
) -> None:
    passages = tmp_path / "passages"
    prepare35.prepare("bioasq", root, passages, plan=fake_plan())
    questions = datasets35.select(datasets35.load_questions("bioasq", root), 1, seed=3)
    files = datasets35.corpus_files("bioasq", root, questions, 2, passages, seed=3)
    gold = set(questions[0].relevant)
    assert gold <= {f.stem for f in files}
    assert len(files) == len(gold) + 2


def test_a_missing_prepared_folder_is_refused_and_named(root: Path, tmp_path: Path) -> None:
    with pytest.raises(datasets35.DatasetError, match="prepare35.py"):
        datasets35.corpus_files("legal", root, [], None, tmp_path / "absent", seed=1)
