"""Experiment 35 ``plan.json`` pre-freeze pins recorded on 2026-11-23.

Rules under test: the FreshStack full-corpus pin, its tree hash and its file-type
table (tasks 16.1 and 16.33; pre-registration sections 4 and 16, P1); the FreshStack
file count, one file per distinct pair of ID and text (owner decision, 2026-11-23); the
Legal RAG Bench input hashes and source (C35 task 4A.4, RDY task 13.4); the seeds the
owner confirmed and the two local uses of 20261101 (task 16.9, P9); the pod image
pinned by digest (task 9.1). Added 2026-11-23: the passage tree hashes (RDY task 5.4c),
the prompt template hashes (task 16.13, P13) and the P11 values that the pre-registration
or the design states (task 16.11). The tests read the committed files only, never the data.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from tests._exp35_fixtures import FOLDER, ROOT, load

arms = load("arms")
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

#: Seeds the harness code used before ``plan.json`` named them (added 2026-11-24), with
#: the BM25 calibration seed that replaced the retired 20261124.
REGISTERED = {
    "classifier_gate_sample": 20261112,
    "correctness_sample": 20261113,
    "halves": 20261115,
    "faithfulness_sample": 20261116,
    "bm25_calibration": 20261139,
}


def _plan() -> dict[str, Any]:
    return json.loads((FOLDER / "plan.json").read_text(encoding="utf-8"))


def _freshstack() -> dict[str, Any]:
    return _plan()["pins"]["datasets"]["freshstack"]


# --- FreshStack full corpus (tasks 16.1 and 16.33) ----------------------------------------


def test_the_loader_reads_the_recorded_freshstack_pin_and_it_is_no_longer_pending() -> None:
    plan = _plan()
    pin = datasets35.freshstack_pin(plan)
    assert pin == {
        "revision": "069f66dc323e163b48b10d08408d282733d4393b",
        "rows": 49514,
        "files": 49506,
        "corpus_files": {
            "train-00000-of-00001.parquet": (
                "f1e63bf897f30062704cd77b22a4c4961ea74824c0511c17e20098f4f203fa52"
            )
        },
        "corpus_tree_sha256": "9c0ef05856cbd51cf7ea61a55ba175f30ad492763425b197a5ed9775c8894ab6",
    }
    pending = {item["key"] for item in plan["pins"]["pending"]}
    names = ("revision", "rows", "files", "corpus_files", "corpus_tree_sha256")
    keys = {f"pins.datasets.freshstack.{key}" for key in names}
    assert not pending & keys


def test_the_freshstack_export_writes_one_file_per_distinct_pair_of_id_and_text() -> None:
    pin = _freshstack()
    # Owner decision 2026-11-23: one ID has two texts, so 49,505 IDs give 49,506 files.
    assert (pin["rows"], pin["unique_ids"], pin["files"]) == (49514, 49505, 49506)
    prereg = (FOLDER / "preregistration.md").read_text(encoding="utf-8")
    section_4 = prereg.split("\n## 4. Datasets\n", 1)[1].split("\n## 5. ", 1)[0]
    protocol = (FOLDER / "protocol.md").read_text(encoding="utf-8")
    section_41 = protocol.split("\n### 4.1 ", 1)[1].split("\n### 4.2 ", 1)[0]
    for text in (section_4, section_41):
        assert "49,506 files" in text
        assert "owner decision" in text.lower()


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


# --- Legal RAG Bench input hashes (C35 task 4A.4, RDY task 13.4) -------------------------

#: ``isaacus/legal-rag-bench``: the parquet conversion commit and the data it converts.
LEGAL_SOURCE = (
    "refs/convert/parquet",
    "1676450bd957c7ee57ecc3e086291638afa69bda",
    "f161e321987310bf85cfb1eac07401eed5d36154",
    "ed079010242cc3e3279c291bde98e622da5deb2c",
    "CC BY-NC-SA 4.0",
)


def test_the_legal_input_hashes_name_the_two_loader_files_and_are_no_longer_pending() -> None:
    plan = _plan()
    hashes = datasets35.input_hashes("legal", plan)
    assert set(hashes) == {datasets35._LEGAL_Q, datasets35._LEGAL_C}
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values())
    assert "pins.datasets.legal.sha256" not in {item["key"] for item in plan["pins"]["pending"]}


def test_the_pins_table_and_protocol_name_the_legal_source_and_both_hashes() -> None:
    hashes = datasets35.input_hashes("legal", _plan())
    prereg = (FOLDER / "preregistration.md").read_text(encoding="utf-8")
    row = next(line for line in prereg.splitlines() if line.startswith("| Legal RAG Bench rev"))
    protocol = (FOLDER / "protocol.md").read_text(encoding="utf-8")
    section_41 = protocol.split("\n### 4.1 ", 1)[1].split("\n### 4.2 ", 1)[0]
    for text in (row, section_41):
        assert all(value in text for value in LEGAL_SOURCE), text[:80]
        assert all(value in text for value in hashes.values()), text[:80]


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
    assert load("rerank_check35").SEED == seeds["rerank_check"]


def test_every_confirmed_plan_seed_is_a_row_of_the_preregistration_seeds_table() -> None:
    text = (FOLDER / "preregistration.md").read_text(encoding="utf-8")
    table = {int(seed) for seed in re.findall(r"^\| (2026\d{4}) \|", text, re.MULTILINE)}
    seeds = _plan()["seeds"]
    confirmed = {seeds.get(key) for key in (*CONFIRMED, "question_order", "smoke_sample")}
    assert confirmed - table == set()


def test_the_seeds_the_code_uses_are_plan_seeds_and_preregistration_rows() -> None:
    seeds = _plan()["seeds"]
    assert {key: seeds.get(key) for key in REGISTERED} == REGISTERED
    text = (FOLDER / "preregistration.md").read_text(encoding="utf-8")
    table = {int(seed) for seed in re.findall(r"^\| (2026\d{4}) \|", text, re.MULTILINE)}
    assert set(seeds.values()) - table == set()


def test_each_plan_seed_has_one_use_except_20261101() -> None:
    values = [v for v in _plan()["seeds"].values() if v != 20261101]
    assert len(values) == len(set(values))


def test_the_harness_constants_and_the_stage_file_use_the_registered_plan_seeds() -> None:
    seeds = _plan()["seeds"]
    assert load("split35").SEED == seeds["halves"]
    assert load("correct35").SEED == seeds["correctness_sample"]
    assert load("faithpool35").SEED_FAITH == seeds["faithfulness_sample"]
    script = (FOLDER / "prefreeze" / "bm25_calibration35.py").read_text(encoding="utf-8")
    assert re.findall(r"^SEED = (\d+)$", script, re.MULTILINE) == [str(seeds["bm25_calibration"])]
    stages = (FOLDER / "prefreeze" / "test_session_stages.txt").read_text(encoding="utf-8")
    sample = re.findall(r"refusals35\.py sample --seed (\d+)", stages)
    assert sample == [str(seeds["classifier_gate_sample"])]


# --- reranker pins (C35 task 4B.3, RDY task 15.10) ------------------------------------------


def test_each_reranker_is_pinned_with_a_passed_rank_check() -> None:
    plan = _plan()
    checks = plan["pins"]["rerank_checks"]
    models = {m["role"]: m for m in plan["runtime"]["models"]}
    assert checks["pairs"] == 200 and checks["seed"] == plan["seeds"]["rerank_check"]
    assert re.fullmatch(r"[0-9a-f]{64}", checks["pairs_sha256"])
    for size in ("0.6b", "4b", "8b"):
        role = f"reranker-{size}"
        model, check = models[role], checks[role]
        assert model["build"] == checks["build"] == 11941, role
        assert model["server_args"]["pooling"] == "rank", role
        assert check["spearman"] >= 0.95, role
        assert re.fullmatch(r"[0-9a-f]{40}", check["gguf_revision"]), role
        assert re.fullmatch(r"[0-9a-f]{40}", check["hf_revision"]), role


def test_each_reranker_runs_one_slot_so_a_pair_gets_the_whole_context() -> None:
    # Four slots share one 8,192-token cache; long FreshStack queries overflow it (protocol 7).
    models = {m["role"]: m for m in _plan()["runtime"]["models"]}
    for size in ("0.6b", "4b", "8b"):
        args = models[f"reranker-{size}"]["server_args"]
        assert args.get("parallel") == 1, size
        assert args["ctx-size"] == args["ubatch-size"] == 8192, size


# --- P10: tokenizer and GLM-5.3 settings ---------------------------------------------------


def test_the_tokenizer_and_glm_pins_equal_the_values_the_harness_sends() -> None:
    pins = _plan()["pins"]
    embedding = pins["settings"]["embedding"]
    assert embedding["tokenizer_model"] == arms.TOKENIZER_MODEL
    assert embedding["tokenizer_revision"] == arms.TOKENIZER_REVISION
    assert arms.TOKENIZER_REVISION.startswith("5cf2132a")
    glm = pins["glm_judge"]
    assert (glm["reasoning"], glm["temperature"]) == (arms.GLM_REASONING, arms.TEMPERATURE)
    assert (glm["judge"], glm["base_url"]) == ("chat", arms.GLM_BASE_URL)


# --- pod image (task 9.1) -----------------------------------------------------------------


def test_the_pod_image_is_pinned_by_digest_and_protocol_section_7_names_the_same_value() -> None:
    image = _plan()["pins"]["environment"]["image"]
    assert re.fullmatch(r"runpod/base@sha256:[0-9a-f]{64}", image)
    protocol = (FOLDER / "protocol.md").read_text(encoding="utf-8")
    assert image in protocol.split("\n## 7. Runtime\n", 1)[1]


# --- the pending list (protocol 0.14 item 45) ---------------------------------------------


def _null_keys(value: Any, key: str) -> list[str]:
    if value is None:
        return [key]
    if isinstance(value, dict):
        return [k for name, item in value.items() for k in _null_keys(item, f"{key}.{name}")]
    return []


def test_pins_pending_lists_exactly_the_pins_that_are_still_null() -> None:
    pins = _plan()["pins"]
    nulls = _null_keys({k: v for k, v in pins.items() if k != "pending"}, "pins")
    assert sorted(item["key"] for item in pins["pending"]) == sorted(nulls)


# --- passage tree hashes (RDY task 5.4c) ---------------------------------------------------


def test_each_passage_tree_hash_is_recorded_and_no_longer_pending() -> None:
    plan = _plan()
    pending = {item["key"] for item in plan["pins"]["pending"]}
    trees = {}
    for dataset in datasets35.PASSAGE_DATASETS:
        trees[dataset] = arms.pinned(plan, "pins", "datasets", dataset, "passages_tree_sha256")
        assert re.fullmatch(r"[0-9a-f]{64}", trees[dataset]), dataset
        assert f"pins.datasets.{dataset}.passages_tree_sha256" not in pending
    assert len(set(trees.values())) == len(trees)


# --- prompt template hashes (task 16.13, P13) ----------------------------------------------
#
# Each hash is the SHA-256 of the UTF-8 bytes of the template text with its
# placeholders unfilled, the rule of the refusal pattern in the pins table.

#: Stands in for a stock Ragas prompt; the adapter template names it ``{prompt}``.
_RAGAS_PROMPT = "<a stock Ragas prompt>"


class _Reply(BaseModel):
    """A Ragas response model; its JSON schema stands in for ``{schema}``."""

    value: int


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _adapter_template() -> str:
    """Return the text ``prefreeze/ragas_stage.py`` puts around a stock Ragas prompt.

    ``structured`` adds a JSON schema request to the prompt and, after a reply that
    does not parse, sends that ask again with a retry line. A fake seam answers the
    first ask with no JSON, so both asks are seen. The retry ask starts with the
    first ask, so one template, with ``{prompt}`` and ``{schema}`` in place of the
    prompt and the schema, holds every adapter character in send order.
    """
    ragas_stage = load("ragas35").ragas_stage_lib
    sent: list[str] = []

    async def seam(prompt: str) -> str:
        sent.append(prompt)
        return "no JSON here" if len(sent) == 1 else '{"value": 1}'

    assert await ragas_stage.structured(seam, _RAGAS_PROMPT, _Reply) == _Reply(value=1)
    first, retry = sent
    schema = json.dumps(_Reply.model_json_schema())
    assert first.startswith(_RAGAS_PROMPT) and first.endswith(schema)
    assert retry.startswith(first) and retry.count(schema) == 1
    return "{prompt}" + retry.removeprefix(_RAGAS_PROMPT).replace(schema, "{schema}")


async def _templates() -> dict[str, str]:
    """Return each P13 template text by ``pins.prompts`` key (not the classifier, G18).

    The answer, oracle and closed-book RAG stages all fill the OMRS answer
    template: the oracle through ``Engine.answer`` with the gold rows, the
    closed-book RAG prompt with an empty evidence block (``closedbook35.py``).
    """
    from omrs.core.answer.prompt import GROUND_TEXT_QA_TEMPLATE

    answer = GROUND_TEXT_QA_TEMPLATE.template
    return {
        "answer": answer,
        "closedbook_own": load("closedbook35").OWN_PROMPT,
        "closedbook_rag": answer,
        "oracle": answer,
        "ragas_adapter": await _adapter_template(),
    }


async def test_each_recorded_prompt_hash_is_the_sha256_of_its_template_text() -> None:
    plan = _plan()
    expected = {name: _sha(text) for name, text in (await _templates()).items()}
    assert {name: plan["pins"]["prompts"][name] for name in expected} == expected
    pending = {item["key"] for item in plan["pins"]["pending"]}
    assert not pending & {f"pins.prompts.{name}" for name in expected}


def test_the_classifier_prompt_and_examples_pins_match_the_committed_files() -> None:
    # Re-pinned 2026-11-24 after the second gate fail: three prompt rules, four examples added.
    plan, path = _plan(), FOLDER / "classify-examples.json"
    examples = json.loads(path.read_text(encoding="utf-8"))
    pin = plan["pins"]["recorded"]["classifier_examples"]
    assert (pin["file"], pin["count"]) == (path.name, len(examples)) == (path.name, 14)
    assert pin["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    claimkinds35 = load("claimkinds35")
    assert {e["kind"] for e in examples} <= set(claimkinds35.KINDS)
    built = claimkinds35.build_prompt(examples)
    assert plan["pins"]["prompts"]["classifier"] == _sha(built)


def test_the_regate_sample_has_its_own_seed() -> None:
    # Owner decision 2026-11-24: a new sample with a new seed after the first gate failed.
    seeds = _plan()["seeds"]
    assert seeds["classifier_gate_sample_2"] == 20261142 != seeds["classifier_gate_sample"]


def test_the_gate2_errors_are_worked_examples_with_the_owner_labels() -> None:
    # Owner labels 2026-11-24 for the four gate2 disagreements. Each qid is the one in the gate2
    # sample; the AES restructuring claim is left out because its label is ambiguous.
    examples = json.loads((FOLDER / "classify-examples.json").read_text(encoding="utf-8"))
    by_claim = {e["claim"]: (e["qid"], e["kind"]) for e in examples}
    expected = {
        '- **Preventing extra information / "not found" behavior:** The provided sources do not '
        'describe a mechanism for constraining the model to return `"not found"` for missing '
        "fields; see,,,,.": ("77536364", "refusal"),
        "The sources do not contain a definitive fix for a `None` query response in this exact "
        "stack; see,,,,.": ("77762811", "refusal"),
        "The provided sources do not show the FY2018 net PP&E balance for 3M; the retrieved "
        "excerpts include cash flow, debt, and cash balances but not the balance sheet line item "
        "for property, plant and equipment, net.": ("financebench_id_04672", "mixed"),
        "You may want to consult the `langchain_google_vertexai` documentation referenced in for "
        "the current, non-deprecated API.": ("77057028", "factual"),
    }
    assert {c: by_claim.get(c) for c in expected} == expected
    assert not any("AES" in e["claim"] for e in examples)


def test_the_third_gate_sample_has_its_own_seed_and_a_preregistration_row() -> None:
    # Owner decision 2026-11-24: gate 3 draws a new sample from main-run answers, new seed.
    seeds = _plan()["seeds"]
    assert seeds["classifier_gate_sample_3"] == 20261143
    gates = ("classifier_gate_sample", "classifier_gate_sample_2", "classifier_gate_sample_3")
    assert len({seeds[k] for k in gates}) == 3
    text = (FOLDER / "preregistration.md").read_text(encoding="utf-8")
    assert "| 20261143 |" in text


def test_the_closed_book_prompts_fill_the_hashed_templates() -> None:
    from omrs.core.answer.prompt import GROUND_TEXT_QA_TEMPLATE

    closedbook35, query = load("closedbook35"), "Which year?"
    rag = GROUND_TEXT_QA_TEMPLATE.template.replace("{context_str}", "")
    assert closedbook35.prompt_text("rag", query) == rag.replace("{query_str}", query)
    own = closedbook35.OWN_PROMPT.replace("{query}", query)
    assert closedbook35.prompt_text("own", query) == own


# --- P11 values the pre-registration or the design states (task 16.11) --------------------

#: C35 design D0.10 names the default instruction that llama-server applies.
_D0_10 = (
    "the server fills in the query and document with the model card's default "
    'instruction ("{text}")'
)


def test_the_query_instruction_is_the_empty_string_of_the_pins_table() -> None:
    plan = _plan()
    assert arms.pinned(plan, "pins", "settings", "embedding", "query_instruction") == ""
    prereg = (FOLDER / "preregistration.md").read_text(encoding="utf-8")
    assert "| Query instruction | Empty string |" in prereg


def test_the_reranker_instruction_is_the_default_text_that_design_d0_10_names() -> None:
    plan = _plan()
    text = arms.pinned(plan, "pins", "recorded", "reranker_instruction")
    design = ROOT / "openspec/changes/experiment-35-full-document-rag-benchmark/design.md"
    assert _D0_10.format(text=text) in design.read_text(encoding="utf-8")
    # The transformers reference of the rank check (task 15.10) sends the same text.
    assert text == load("rerank_scorers35").INSTRUCTION
    assert "pins.recorded.reranker_instruction" not in {i["key"] for i in plan["pins"]["pending"]}


# --- OCR off during corpus prep (protocol 4.3; 2026-11-25 pre-freeze note) ------------------


def test_the_plan_pins_the_ocr_fallback_off_and_the_real_setups_write_it(tmp_path: Path) -> None:
    from omrs.config import Settings

    plan = _plan()
    assert arms.pinned(plan, "pins", "settings", "ocr_fallback_enabled") is False
    assert "ocr_fallback_enabled" in Settings.model_fields  # the app's own setting key
    gguf = tmp_path / "gguf"
    gguf.mkdir()
    for model in plan["runtime"]["models"]:
        (gguf / model["file"]).write_bytes(b"")
    for name in ("e4b-c512-roff-hoff", "e8b-c2048-r8b-hon"):
        values = arms.settings_values(arms.parse_setup(name), plan, gguf, answer_host="", judges=())
        assert values["ocr_fallback_enabled"] is False


# --- file-type routing off for prepared passages (amendment A13, 2026-11-26) ---------------


def test_the_plan_pins_file_type_routing_off_and_the_real_setups_write_it(tmp_path: Path) -> None:
    from omrs.core.ingestion.settings import IngestionSettings

    plan = _plan()
    assert arms.pinned(plan, "pins", "settings", "ingestion", "file_type_routing") is False
    assert "file_type_routing" in IngestionSettings.model_fields  # the app's own setting key
    assert "A13" in {a["id"] for a in plan["amendments"]}
    gguf = tmp_path / "gguf"
    gguf.mkdir()
    for model in plan["runtime"]["models"]:
        (gguf / model["file"]).write_bytes(b"")
    for name in ("e0.6b-c512-roff-hoff", "e8b-c2048-r8b-hon"):
        values = arms.settings_values(arms.parse_setup(name), plan, gguf, answer_host="", judges=())
        assert values["ingestion"]["file_type_routing"] is False


# --- reproduction tolerance of evidence_recall_20k (RDY 16.14, P14; owner, 2026-11-25) -------


def test_evidence_recall_20k_has_the_tolerance_of_the_other_four_metrics() -> None:
    from omrs.core.experiment_records.runtime_block import load_runtime_block

    plan = _plan()
    tolerance = {t.metric: t.max_abs_change for t in load_runtime_block(plan).tolerance}
    assert tolerance == dict.fromkeys(
        ("Recall@10", "MRR@10", "nDCG@10", "hit@page", "evidence_recall_20k"), 0.005
    )
    prereg = (FOLDER / "preregistration.md").read_text(encoding="utf-8")
    named = "0.005 absolute on nDCG@10, Recall@10, MRR@10, hit@page and `evidence_recall_20k`"
    assert named in prereg
