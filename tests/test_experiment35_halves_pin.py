"""Experiment 35 ``halves.json`` pin and the question halves of section 5 (task 16.12, P12).

The tests read the committed files only, never the benchmark data.
"""

from __future__ import annotations

import hashlib
import json
import re

from tests._exp35_fixtures import FOLDER

SMOKE_IDS = {
    "bioasq": {"4043", "1372", "604", "2291", "1122"},
    "financebench": {
        "financebench_id_01476",
        "financebench_id_01964",
        "financebench_id_01484",
        "financebench_id_05718",
        "financebench_id_00476",
    },
    "freshstack": {"76404464", "78048414", "77762811", "77828572", "77536364"},
}


def _halves() -> dict[str, dict[str, str]]:
    return json.loads((FOLDER / "halves.json").read_text(encoding="utf-8"))["halves"]


def test_the_plan_holds_the_sha256_and_seed_of_the_halves_file() -> None:
    plan = json.loads((FOLDER / "plan.json").read_text(encoding="utf-8"))
    pin = plan["pins"]["recorded"]["halves"]
    data = (FOLDER / "halves.json").read_bytes()
    assert pin["sha256"] == hashlib.sha256(data).hexdigest()
    assert pin["seed"] == plan["seeds"]["halves"] == json.loads(data)["seed"]
    assert "pins.recorded.halves" not in {i["key"] for i in plan["pins"]["pending"]}


def test_every_question_has_half_a_or_half_b_and_the_halves_are_balanced() -> None:
    halves = _halves()
    assert set(halves) == {"bioasq", "financebench", "freshstack", "legal"}
    for rows in halves.values():
        sizes = [list(rows.values()).count(half) for half in "AB"]
        assert sum(sizes) == len(rows)
        assert abs(sizes[0] - sizes[1]) <= 4


def test_section_5_lists_the_half_of_every_smoke_question_as_halves_json_has_it() -> None:
    text = (FOLDER / "preregistration.md").read_text(encoding="utf-8")
    section = text.split("## 5. Existing data")[1].split("## 6.")[0]
    listed: dict[str, dict[str, str]] = {}
    for dataset, half, ids in re.findall(r"^\| (\w+) \| ([AB]) \| ([^|]+) \|$", section, re.M):
        for qid in (part.strip("` ") for part in ids.split(",")):
            listed.setdefault(dataset, {})[qid] = half
    halves = _halves()
    for dataset, ids in SMOKE_IDS.items():
        assert ids <= set(listed[dataset]), f"{dataset}: smoke IDs missing from section 5"
    for dataset, rows in listed.items():
        assert rows == {qid: halves[dataset][qid] for qid in rows}
