"""Checks on freeze_check_stages.txt, the pre-freeze pod check (readiness review S2).

pod_test_session.sh runs the file unchanged; launch35.sh reads it from STAGES_FILE.
test_session_stages.py runs the general checks on it (parsing, scripts and their
options, no key, a timeout on every stage, one selection per folder). These tests
check what the freeze check must cover: the setup checks, the resolved settings, the
FreshStack rate on the 2,747-file sample, one reranker-on, hybrid-on setup through
every answer stage on each core dataset, G2 and G1, the 8B pair, the smoke join, and
a read-only check after the files it reads.
"""

from __future__ import annotations

import json

from test_session_stages import (
    EXP35,
    FREEZE_FILE,
    HERE,
    OUT,
    _calls,
    _folder,
    _opts,
    _read,
    _runs,
    _script,
)

CORE = ("financebench", "bioasq", "freshstack")
SHORT = {"financebench": "fb", "bioasq": "bio", "freshstack": "fs"}
SETUP = "e4b-c1024-r0.6b-hon"
TOKENIZER_SHA = "83cdf8c3a34f68862319cb1810ee7b1e2c0a44e0864ae930194ddb76bb7feb8d"
EXPECTED = HERE / "fs_chunks_c1024_expected.json"


def _stage_at(name: str) -> int:
    return next(s.index for s in _read(FREEZE_FILE)[0] if s.name == name)


def _checks() -> dict[str, tuple[str, ...]]:
    """Return each check stage's verify35.py arguments, by stage name."""
    found = {}
    for call in _calls(FREEZE_FILE):
        script = _script(call)
        if script and script[0] == "prefreeze/verify35.py" and script[1] != "rate":
            found[call.stage.name] = (script[1], *script[2])
    return found


def test_setup_and_context_run_first_and_only_they_stop_the_chain() -> None:
    stages, values = _read(FREEZE_FILE)
    assert [s.name for s in stages[:3]] == ["setup", "context", "gpulog"]
    assert [s.name for s in stages if s.fatal] == ["setup", "context"]
    assert stages[0].command == _read()[0][0].command  # the test session's setup line
    assert values == {"SWEEP_GGUF_DIR": _read()[1]["SWEEP_GGUF_DIR"]}
    for stage in stages:  # the pod runs the commit the watcher gives, nothing else
        for word in ("git ", "checkout", "fetch"):
            assert word not in stage.command, (stage.name, word)


def test_the_dry_runs_record_routing_ocr_and_the_answer_cap() -> None:
    runs = [(c, a) for c, a in _runs(FREEZE_FILE) if c.stage.name == "dry-resolved"]
    assert [(a.dataset, a.stage, a.dry_run) for _, a in runs] == [
        ("freshstack", "ingest", True),
        ("financebench", "ingest", True),
    ]
    assert {_folder(a.out_dir) for _, a in runs} == {"dry"}
    args = _checks()["check-dry"]
    assert args[1] == f"{OUT}/dry/*-ingest.txt" and _opts(args)["--count"] == "2"
    assert {
        "resolved.file_type_routing=false",
        "resolved.ocr_fallback_enabled=false",
        "resolved.answer_max_output_tokens=2048",
    } <= set(args)


def test_the_rate_build_is_the_2747_file_sample_checked_against_the_mac_counts() -> None:
    runs = {c.stage.name: (c, a) for c, a in _runs(FREEZE_FILE)}
    call, a = runs["fs-rate"]
    assert _script(call)[:2] == ("prefreeze/verify35.py", "rate")
    found = (a.dataset, a.index, a.stage, a.corpus_sample, a.limit, a.qids, _folder(a.out_dir))
    assert found == ("freshstack", "e4b-c1024", "ingest", 1200, None, None, "fsrate")
    seal = runs["fs-rate-seal"][1]
    assert (seal.stage, seal.corpus_sample, _folder(seal.out_dir)) == ("seal", 1200, "fsrate")
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert len(expected["samples"]["fsrate"]["files"]) == 2747
    assert (expected["chunk_size"], expected["tokenizer"]["revision"][:8]) == (1024, "5cf2132a")
    args = _checks()["check-fs-rate"]
    assert args[1] == f"{OUT}/fsrate/freshstack/e4b-c1024/ingest-summary.json"
    assert _opts(args)["--sample"] == "fsrate"
    assert (EXP35 / _opts(args)["--expected"]).resolve() == EXPECTED.resolve()


def test_the_mac_samples_are_the_selections_the_stages_ingest() -> None:
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))["samples"]
    runs = [a for _, a in _runs(FREEZE_FILE) if a.dataset == "freshstack" and a.stage == "ingest"]
    by_folder = {_folder(a.out_dir): (a.limit, a.corpus_sample) for a in runs}
    assert by_folder["fsrate"] == (expected["fsrate"]["limit"], expected["fsrate"]["corpus_sample"])
    for folder in ("s", "rb"):
        assert by_folder[folder] == (expected["s"]["limit"], expected["s"]["corpus_sample"])
    assert len(expected["s"]["files"]) == 386


def test_each_core_dataset_runs_the_setup_through_every_answer_stage_in_order() -> None:
    runs = _runs(FREEZE_FILE)
    order = ["search", "answer", "determinism", "closedbook", "judge", "ragas", "claimkinds"]
    for dataset in CORE:
        mine = [(c, a) for c, a in runs if a.dataset == dataset and _folder(a.out_dir) == "s"]
        built = [a.stage for _, a in mine if a.index == "e4b-c1024"]
        assert built == ["ingest", "seal"], dataset
        steps = [(a.stage, a.answers) for _, a in mine if a.setup == SETUP]
        assert [s for s, _ in steps if s != "ragas"] == [s for s in order if s != "ragas"]
        assert [k for s, k in steps if s == "ragas"] == [
            "answer",
            "closedbook-own",
            "closedbook-rag",
        ]
        first = {s: min(c.stage.index for c, a in mine if a.stage == s) for s in order}
        assert [first[s] for s in order] == sorted(first.values()), dataset
        assert {a.judges for _, a in mine if a.stage == "judge"} == {"chat,clef_flash"}
        assert {a.run for _, a in mine if a.stage == "determinism"} == {1}
        hosts = {a.answer_host for _, a in mine if a.stage in ("answer", "closedbook")}
        assert hosts == {"deepinfra/fp8"}
        assert {a.limit for _, a in mine} == {10}


def test_financebench_ingests_pdfs_without_a_passages_folder() -> None:
    for _, a in _runs(FREEZE_FILE):
        if a.dataset == "financebench":
            assert a.passages_dir is None and a.corpus_sample == 3
        else:
            assert str(a.passages_dir) == "/workspace/passages"


def test_g2_rebuilds_each_index_and_compares_before_the_answer_setup_searches() -> None:
    runs = _runs(FREEZE_FILE)
    for dataset in CORE:
        mine = [(c, a) for c, a in runs if a.dataset == dataset]
        built = {(a.stage, _folder(a.out_dir)) for _, a in mine if a.index == "e4b-c1024"}
        assert {("ingest", "rb"), ("seal", "rb"), ("ingest", "s"), ("seal", "s")} <= built
        sides = sorted(
            (_folder(a.index_from), _folder(a.out_dir))
            for _, a in mine
            if a.stage == "search" and a.setup == "e4b-c1024-roff-hoff"
        )
        assert sides == [("rb", "rbs"), ("s", "chk")], dataset
        (compare,) = [
            c for c in _calls(FREEZE_FILE) if "rebuild35.py" in c.words and dataset in c.words
        ]
        opts = _opts(compare.words)
        path = f"{dataset}/search/e4b-c1024-roff-hoff/run1/search.jsonl"
        assert (opts["--a"], opts["--b"]) == (f"{OUT}/chk/{path}", f"{OUT}/rbs/{path}")
        assert opts["--out-dir"] == f"{OUT}/s" and compare.words[-1] == "--prefreeze"
        assert compare.stage.index < _stage_at(f"search-{SHORT[dataset]}")
    for name in ("g2-fb-check", "g2-bio-check", "g2-fs-check"):
        command = next(s.command for s in _read(FREEZE_FILE)[0] if s.name == name)
        assert command.count(" && ") == 2 and ";" not in command and "||" not in command


def test_the_8b_embedder_and_reranker_search_an_index_built_in_this_session() -> None:
    runs = [(c, a) for c, a in _runs(FREEZE_FILE) if _folder(a.out_dir) == "vram"]
    found = [(a.index or a.setup, a.stage, a.index_from) for _, a in runs]
    assert found == [
        ("e8b-c1024", "ingest", None),
        ("e8b-c1024", "seal", None),
        ("e8b-c1024-r8b-hon", "search", None),
    ]


def test_the_smoke_join_reads_s_and_every_check_runs_after_its_inputs() -> None:
    (join,) = [c for c in _calls(FREEZE_FILE) if "join35.py" in c.words]
    script, _, words = _script(join)
    assert script == "join35.py" and words == ("--out-dir", f"{OUT}/s", "--smoke", "--runs", "1")
    last_runner = max(c.stage.index for c, _ in _runs(FREEZE_FILE))
    checks = _checks()
    for name in checks:
        if name not in ("check-dry", "check-fs-rate", "check-chunks", "check-chunks-other"):
            assert _stage_at(name) > max(last_runner, join.stage.index), name
    assert _stage_at("check-dry") == _stage_at("dry-resolved") + 1
    assert _stage_at("check-fs-rate") == _stage_at("fs-rate-seal") + 1
    assert _stage_at("check-chunks") > _stage_at("g2-fs-build")
    assert not any(n.startswith("analyse") for n in (s.name for s in _read(FREEZE_FILE)[0]))


def test_the_pass_checks_use_the_real_summary_fields() -> None:
    checks = _checks()
    want = {
        "check-answers": ("missing=0", "--count", "9"),
        "check-judges": ("missing=0", "closed_claims=0", "not_judged=0", "--count", "6"),
        "check-ragas": ("errors=0", "not_judged=0", "unjudged_open={}", "--count", "9"),
        "check-kinds": ("closed_missing=[]", "--count", "3"),
        "check-determinism": ("ok=true", "--count", "3"),
        "check-rebuild": ("ok=true", "setup=e4b-c1024-roff-hoff", "--count", "3"),
        "check-fb-seal": ("unpaged_chunks=0", "--count", "2"),
        "check-tokenizer": (f"tokenizer.sha256={TOKENIZER_SHA}", "--count", "8"),
        "check-join": ("ok=true", "smoke=true"),
    }
    for name, words in want.items():
        assert checks[name][0] == "expect", name
        assert set(words) <= set(checks[name]), name
    finish = checks["check-finish"]
    assert finish[0] == "finish" and _opts(finish)["--cap"] == "2048"
    assert _opts(finish)["--out"] == f"{OUT}/s/finish-reasons.json"
