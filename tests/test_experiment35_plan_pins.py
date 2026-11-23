"""Experiment 35 ``plan.json`` pre-freeze pins recorded on 2026-11-23.

Rules under test: the FreshStack full-corpus pin, its tree hash and its file-type
table (tasks 16.1 and 16.33; pre-registration sections 4 and 16, P1); the seeds the
owner confirmed and the two local uses of 20261101 (task 16.9, P9); the pod image
pinned by digest (task 9.1). The tests read the committed files only, never the data.
"""

from __future__ import annotations

import json
import re
from typing import Any

from tests._exp35_fixtures import FOLDER, load

datasets35 = load("datasets35")
prepare35 = load("prepare35")

#: Seeds confirmed by the owner on 2026-11-23 (P9), by ``plan.json`` ``seeds`` key.
CONFIRMED = {
    "mde_pilot": 20261118,
    "length_check": 20261119,
    "smoke_setups": 20261121,
    "l2_claim_kinds": 20261122,
    "l2_faithfulness": 20261123,
    "faithfulness_gate_kappa": 20261125,
    "differential_error": 20261126,
    "correctness_gate_kappa": 20261127,
    "correctness_gate_auc": 20261128,
    "l1_l2_kappa": 20261129,
    "ragflow_page_gate": 20261130,
    "ragflow_repeatability": 20261131,
    "part2_label_order": 20261132,
    "part2_correctness_sample": 20261133,
    "part2_correctness_kappa": 20261134,
    "part2_correctness_auc": 20261135,
    "refusal_report": 20261136,
}


def _plan() -> dict[str, Any]:
    return json.loads((FOLDER / "plan.json").read_text(encoding="utf-8"))


def _freshstack() -> dict[str, Any]:
    return _plan()["pins"]["datasets"]["freshstack"]


# --- FreshStack full corpus (tasks 16.1 and 16.33) ----------------------------------------


def test_the_loader_reads_the_recorded_freshstack_pin_and_it_is_no_longer_pending() -> None:
    plan = _plan()
    pin = datasets35.freshstack_pin(plan)
    assert pin == {"revision": "069f66dc323e163b48b10d08408d282733d4393b", "rows": 49514}
    pending = {item["key"] for item in plan["pins"]["pending"]}
    assert not pending & {"pins.datasets.freshstack.revision", "pins.datasets.freshstack.rows"}


def test_the_corpus_tree_hash_is_the_tree_hash_of_the_recorded_file_hashes() -> None:
    pin = _freshstack()
    assert list(pin["corpus_files"]) == ["train-00000-of-00001.parquet"]
    assert datasets35.tree_hash(pin["corpus_files"]) == pin["corpus_tree_sha256"]


def test_the_file_type_table_counts_every_row_once() -> None:
    pin = _freshstack()
    table = pin["file_types"]
    assert sum(entry["rows"] for entry in table.values()) == pin["rows"]
    assert pin["fenced_rows"] + pin["unfenced_rows"] == pin["rows"]
    assert all(0 < entry["files"] <= entry["rows"] for entry in table.values())


def test_the_fenced_count_is_the_rows_whose_extension_is_not_md_or_mdx() -> None:
    pin = _freshstack()
    fenced = 0
    for extension, entry in pin["file_types"].items():
        _, found, is_fenced = prepare35.export_row(f"repo/file{extension}_0_1", "x\n")
        assert found == extension
        fenced += entry["rows"] if is_fenced else 0
    assert fenced == pin["fenced_rows"]
    markdown = pin["file_types"][".md"]["rows"] + pin["file_types"][".mdx"]["rows"]
    assert pin["unfenced_rows"] == markdown


# --- seeds (task 16.9) --------------------------------------------------------------------


def test_the_confirmed_seeds_are_in_the_plan_with_their_values() -> None:
    seeds = _plan()["seeds"]
    assert {key: seeds.get(key) for key in CONFIRMED} == CONFIRMED
    assert 20261124 not in seeds.values()  # retired (O4), never reused


def test_seed_20261101_keeps_its_value_and_both_local_uses() -> None:
    plan = _plan()
    seeds = plan["seeds"]
    assert plan["seed"] == seeds["answer"] == 20261101
    assert seeds["question_order"] == seeds["smoke_sample"] == 20261101


def test_the_harness_seed_constants_equal_the_confirmed_plan_seeds() -> None:
    seeds = _plan()["seeds"]
    lengthcheck35, labels35 = load("lengthcheck35"), load("labels35")
    correct35, refusalreport35 = load("correct35"), load("refusalreport35")
    assert (lengthcheck35.SEED, lengthcheck35.CLAIMS) == (seeds["length_check"], 300)
    assert labels35.SEED_L2 == {
        "claim_kinds": seeds["l2_claim_kinds"],
        "faithfulness": seeds["l2_faithfulness"],
    }
    assert labels35.SEED_GATE_KAPPA == seeds["faithfulness_gate_kappa"]
    assert labels35.SEED_DIFFERENCE == seeds["differential_error"]
    assert labels35.SEED_L1_L2 == seeds["l1_l2_kappa"]
    assert correct35.SEED_KAPPA == seeds["correctness_gate_kappa"]
    assert correct35.SEED_AUC == seeds["correctness_gate_auc"]
    assert refusalreport35.SEED == seeds["refusal_report"]


def test_every_confirmed_plan_seed_is_a_row_of_the_preregistration_seeds_table() -> None:
    text = (FOLDER / "preregistration.md").read_text(encoding="utf-8")
    table = {int(seed) for seed in re.findall(r"^\| (2026\d{4}) \|", text, re.MULTILINE)}
    seeds = _plan()["seeds"]
    confirmed = {seeds.get(key) for key in (*CONFIRMED, "question_order", "smoke_sample")}
    assert confirmed - table == set()


# --- pod image (task 9.1) -----------------------------------------------------------------


def test_the_pod_image_is_pinned_by_digest_and_protocol_section_7_names_the_same_value() -> None:
    image = _plan()["pins"]["environment"]["image"]
    assert re.fullmatch(r"runpod/base@sha256:[0-9a-f]{64}", image)
    protocol = (FOLDER / "protocol.md").read_text(encoding="utf-8")
    assert image in protocol.split("\n## 7. Runtime\n", 1)[1]
