"""Experiment 35 ``refusals35.py classify`` and the regular-expression pin (tasks 8.6, 8.7).

``classify`` runs the fixed-prompt classifier over the saved gate sample through the hosted
gate and writes ``sample-kinds.jsonl``, which ``gate`` reads. A stub stands in for the model;
nothing here sends a call.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests._exp35_fixtures import FOLDER, load

refusals35 = load("refusals35")
claimkinds35 = load("claimkinds35")

PROMPT = "fixed prompt"
VERSION = "v-classify"


class RateLimited(Exception):
    status_code = 429


def _sample(out: Path) -> list[dict]:
    items = [
        {"item_id": f"k{i}", "claim_key": claimkinds35.claim_key(f"q{i}", f"Claim {i}."),
         "qid": f"q{i}", "question": f"Q{i}?", "claim": f"Claim {i}.",
         "stratum": "d/plain", "flagged": False}
        for i in range(3)
    ]  # fmt: skip
    out.mkdir(parents=True, exist_ok=True)
    (out / "sample.json").write_text(json.dumps({"seed": 1, "n": 3, "strata": [], "items": items}))
    return items


def _examples(tmp_path: Path, claim: str = "Another claim.") -> Path:
    path = tmp_path / "examples.json"
    path.write_text(
        json.dumps([{"qid": "qx", "question": "QX?", "claim": claim, "kind": "factual"}])
    )
    return path


def _argv(out: Path, examples: Path, *extra: str) -> list[str]:
    return ["classify", "--out-dir", str(out), "--examples", str(examples), *extra]


def _builder(call):
    seen: list[list[dict]] = []

    def build(plan, examples):
        seen.append(examples)
        return call, VERSION, PROMPT

    build.seen = seen
    return build


def _reply(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text, model_returned="m", provider_returned="p")


def test_classify_writes_one_saved_kind_per_sample_claim(tmp_path: Path) -> None:
    out = tmp_path / "gate"
    items = _sample(out)
    sent: list[list[dict]] = []

    async def call(messages):
        sent.append(messages)
        return _reply("refusal" if "Claim 1." in messages[-1]["content"] else "factual")

    code = refusals35.main(_argv(out, _examples(tmp_path)), build_classifier=_builder(call))
    assert code == 0
    rows = [json.loads(line) for line in (out / "sample-kinds.jsonl").read_text().splitlines()]
    assert {r["claim_key"]: r["kind"] for r in rows} == {
        i["claim_key"]: "refusal" if i["qid"] == "q1" else "factual" for i in items
    }
    assert {r["version"] for r in rows} == {VERSION}
    assert len(sent) == len(items)
    assert all(m[0]["content"] == PROMPT for m in sent)


def test_classify_goes_through_the_hosted_gate_and_a_429_on_every_attempt_exits_5(
    tmp_path: Path,
) -> None:
    out = tmp_path / "gate"
    _sample(out)
    calls = 0

    async def call(messages):
        nonlocal calls
        calls += 1
        raise RateLimited("slow down")

    code = refusals35.main(
        _argv(
            out, _examples(tmp_path), "--rate-limit-attempts", "1", "--classify-concurrency", "1"
        ),
        build_classifier=_builder(call),
    )
    assert code == 5
    assert calls >= 1
    assert not (out / "sample-kinds.jsonl").exists()


def test_classify_refuses_a_prompt_example_that_is_a_sample_claim(tmp_path: Path) -> None:
    out = tmp_path / "gate"
    _sample(out)

    async def call(messages):
        return _reply("factual")

    path = tmp_path / "ex-sample.json"
    path.write_text(
        json.dumps([{"qid": "q2", "question": "Q2?", "claim": "Claim 2.", "kind": "factual"}])
    )
    with pytest.raises(SystemExit, match="Claim 2"):
        refusals35.main(_argv(out, path), build_classifier=_builder(call))
    assert not (out / "sample-kinds.jsonl").exists()


def test_the_prefreeze_regex_matches_the_sha256_pinned_in_the_pre_registration() -> None:
    text = (FOLDER / "preregistration.md").read_text(encoding="utf-8")
    pinned = re.search(r"SHA-256 of the pattern text[^`]*`([0-9a-f]{64})`", text)
    assert pinned is not None
    actual = hashlib.sha256(refusals35.PREFREEZE_REGEX.pattern.encode("utf-8")).hexdigest()
    assert actual == pinned.group(1)
    assert refusals35.PREFREEZE_REGEX.flags & re.IGNORECASE
