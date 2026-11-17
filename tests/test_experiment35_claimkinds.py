"""Experiment 35 claim alignment and claim classifier with a stub LLM (tasks 8.2 and 8.5).

Rules under test: claims split again from the saved answer match the judge
row's verdict count and order, and a mismatch stops and names the place; the
prompt holds the three kinds and examples from outside the sample only; the
model sees the question and the claim, never evidence or a verdict; the
version is the SHA-256 of prompt, model, host, reasoning, temperature and
seed; the ``claimkinds`` stage writes one row per claim and a done-marker,
skips saved claims on resume, runs the environment check first, stops with
code 5 on a rate-limit stop and saves no kind for it; an unreadable reply is
saved as ``unreadable``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load
from tests._exp35_label_fixtures import answer_row, judge_row, write_run

claimkinds35 = load("claimkinds35")

QUESTIONS = {"q1": "What is the revenue?", "q2": "Which gene?"}
ANSWERS = {
    "q1": ["Revenue rose sharply", "The sources do not cover the margin"],
    "q2": ["The gene is BRCA"],
}
EXAMPLES = [
    {"question": "Who?", "claim": "The sources do not name the author", "kind": "refusal"},
    {"question": "When?", "claim": "It opened in spring", "kind": "factual"},
    {
        "question": "Where?",
        "claim": "It is in Paris, but the sources do not give the street",
        "kind": "mixed",
    },
]


class StubStop(RuntimeError):
    """Stands in for the hosted gate's rate-limit stop."""


def _stub(replies: dict[str, str] | None = None, *, stop_on: str | None = None):
    sent: list[list[dict[str, str]]] = []

    async def call(messages: list[dict[str, str]]) -> str:
        sent.append(messages)
        claim = messages[-1]["content"]
        if stop_on is not None and stop_on in claim:
            raise StubStop("429 on every attempt")
        for needle, reply in (replies or {}).items():
            if needle in claim:
                return reply
        return "factual"

    return call, sent


def _stage(tmp_path: Path, call: Any, **kw: Any) -> int:
    run_dir = tmp_path / "run1"
    if not (run_dir / "answer.jsonl").exists():
        write_run(run_dir, ANSWERS)
    prompt = claimkinds35.build_prompt(EXAMPLES)
    kw.setdefault("env_check", lambda _folder: None)
    kw.setdefault("stop_errors", (StubStop,))
    return asyncio.run(
        claimkinds35.claimkinds_stage(run_dir, QUESTIONS, call, prompt=prompt, version="v1", **kw)
    )


# --- 8.2 claim alignment ---------------------------------------------------------------------


def test_claims_split_again_match_the_judge_verdicts_in_order() -> None:
    answer = answer_row("q1", ANSWERS["q1"])
    judge = judge_row("q1", ["supported", "unsupported"])
    pairs = claimkinds35.align(answer, judge, where="bioasq/setup-a/run1/q1")
    assert [c for c, _ in pairs] == [
        "Revenue rose sharply.",
        "The sources do not cover the margin.",
    ]
    assert [v["verdict"] for _, v in pairs] == ["supported", "unsupported"]


def test_a_count_mismatch_stops_and_names_the_place() -> None:
    answer = answer_row("q1", ANSWERS["q1"])
    judge = judge_row("q1", ["supported"])
    with pytest.raises(claimkinds35.AlignmentError, match="bioasq/setup-a/run1/q1"):
        claimkinds35.align(answer, judge, where="bioasq/setup-a/run1/q1")


def test_verdicts_out_of_order_stop() -> None:
    answer = answer_row("q1", ANSWERS["q1"])
    judge = judge_row("q1", ["supported", "unsupported"])
    judge["verdicts"].reverse()
    with pytest.raises(claimkinds35.AlignmentError, match="order"):
        claimkinds35.align(answer, judge, where="x")


def test_the_stage_stops_on_a_mismatch_and_names_dataset_setup_run_question(tmp_path: Path) -> None:
    run_dir = tmp_path / "bioasq" / "setup-a" / "run2"
    write_run(run_dir, ANSWERS, {"chat": {"q1": ["supported"], "q2": ["supported"]}})
    call, sent = _stub()
    with pytest.raises(claimkinds35.AlignmentError, match="bioasq/setup-a/run2/q1"):
        asyncio.run(
            claimkinds35.claimkinds_stage(
                run_dir, QUESTIONS, call, prompt="p", version="v", env_check=lambda _f: None
            )
        )
    assert sent == []


# --- 8.5 prompt and version ------------------------------------------------------------------


def test_prompt_holds_the_three_kinds_and_the_examples() -> None:
    prompt = claimkinds35.build_prompt(EXAMPLES)
    for kind in ("factual", "refusal", "mixed"):
        assert kind in prompt
    for example in EXAMPLES:
        assert example["claim"] in prompt


def test_no_example_may_be_a_sample_claim() -> None:
    keys = {claimkinds35.claim_key("q9", "It opened in spring")}
    examples = [dict(e, qid="q9") for e in EXAMPLES]
    with pytest.raises(ValueError, match="sample"):
        claimkinds35.check_examples(examples, keys)
    claimkinds35.check_examples([dict(e, qid="other") for e in EXAMPLES], keys)


def test_the_model_sees_the_question_and_the_claim_only(tmp_path: Path) -> None:
    call, sent = _stub()
    assert _stage(tmp_path, call) == 0
    user = [m for m in sent[0] if m["role"] == "user"][0]["content"]
    assert QUESTIONS["q1"] in user
    assert "Revenue rose sharply." in user
    joined = json.dumps(sent)
    assert "passage for" not in joined  # no evidence
    assert "supported" not in joined  # no verdict


def test_version_is_the_sha256_of_the_six_settings() -> None:
    base = {
        "model": "openai/gpt-oss-120b",
        "host": "host-a",
        "reasoning": "low",
        "temperature": 0.0,
        "seed": 20261101,
    }
    first = claimkinds35.classifier_version("prompt", **base)
    assert len(first) == 64
    assert first == claimkinds35.classifier_version("prompt", **base)
    for name, other in [
        ("model", "m2"),
        ("host", "h2"),
        ("reasoning", "high"),
        ("temperature", 0.1),
        ("seed", 1),
    ]:
        assert claimkinds35.classifier_version("prompt", **{**base, name: other}) != first
    assert claimkinds35.classifier_version("prompt 2", **base) != first


# --- 8.5 the claimkinds stage ----------------------------------------------------------------


def _rows(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / "run1" / "claim-kinds.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_stage_writes_one_kind_per_claim_and_a_done_marker(tmp_path: Path) -> None:
    call, _ = _stub({"do not cover": "Refusal."})
    assert _stage(tmp_path, call) == 0
    rows = _rows(tmp_path)
    assert [(r["qid"], r["index"], r["kind"]) for r in rows] == [
        ("q1", 0, "factual"),
        ("q1", 1, "refusal"),
        ("q2", 0, "factual"),
    ]
    assert rows[1]["claim_key"] == claimkinds35.claim_key(
        "q1", "The sources do not cover the margin."
    )
    assert all(r["version"] == "v1" for r in rows)
    assert (tmp_path / "run1" / ".done-claimkinds.json").exists()


def test_resume_skips_saved_claims(tmp_path: Path) -> None:
    call, _ = _stub(stop_on="BRCA")
    assert _stage(tmp_path, call) == claimkinds35.EXIT_RATE_LIMIT
    assert not (tmp_path / "run1" / ".done-claimkinds.json").exists()
    assert [r["qid"] for r in _rows(tmp_path)] == [
        "q1",
        "q1",
    ]  # no kind saved for the stopped claim
    call2, sent2 = _stub()
    assert _stage(tmp_path, call2, resume=True) == 0
    assert len(sent2) == 1  # only the claim not yet saved
    assert [r["qid"] for r in _rows(tmp_path)] == ["q1", "q1", "q2"]


def test_without_resume_an_existing_file_is_refused(tmp_path: Path) -> None:
    call, _ = _stub()
    _stage(tmp_path, call)
    with pytest.raises(RuntimeError, match="resume"):
        _stage(tmp_path, call)


def test_environment_check_runs_before_any_call(tmp_path: Path) -> None:
    call, sent = _stub()

    def refuse(_folder: Path) -> None:
        raise RuntimeError("environment differs: gpu")

    with pytest.raises(RuntimeError, match="gpu"):
        _stage(tmp_path, call, env_check=refuse)
    assert sent == []


def test_unreadable_reply_is_saved_as_unreadable(tmp_path: Path) -> None:
    call, _ = _stub({"BRCA": "I think it might be a fact or not"})
    _stage(tmp_path, call)
    assert _rows(tmp_path)[-1]["kind"] == "unreadable"


def test_concurrency_limit_holds(tmp_path: Path) -> None:
    live = {"now": 0, "max": 0}

    async def call(_messages: list[dict[str, str]]) -> str:
        live["now"] += 1
        live["max"] = max(live["max"], live["now"])
        await asyncio.sleep(0.01)
        live["now"] -= 1
        return "factual"

    write_run(tmp_path / "run1", {f"q{i}": ["Claim one", "Claim two"] for i in range(6)})
    questions = {f"q{i}": "?" for i in range(6)}
    asyncio.run(
        claimkinds35.claimkinds_stage(
            tmp_path / "run1",
            questions,
            call,
            prompt="p",
            version="v",
            env_check=lambda _f: None,
            concurrency=3,
        )
    )
    assert live["max"] == 3


@pytest.mark.parametrize(
    ("reply", "kind"),
    [
        ("factual", "factual"),
        ("Refusal.", "refusal"),
        (" MIXED\n", "mixed"),
        ("fact", "unreadable"),
        ("", "unreadable"),
    ],
)
def test_parse_kind(reply: str, kind: str) -> None:
    assert claimkinds35.parse_kind(reply) == kind
