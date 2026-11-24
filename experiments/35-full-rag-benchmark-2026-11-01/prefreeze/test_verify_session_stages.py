"""Checks on verify_session_stages.txt, the fix check pod session (2026-11-24 notes).

pod_test_session.sh runs the file unchanged; launch35.sh reads it from STAGES_FILE.
test_session_stages.py runs the general checks on it (parsing, scripts and their
options, no key, a timeout on every stage). These tests check what the fix check
needs: sections 1, 3, 4 and 2 in that order, the test session setup, and no checkout
of another commit.
"""

from __future__ import annotations

from test_session_stages import (
    OUT,
    VERIFY_FILE,
    _calls,
    _folder,
    _opts,
    _read,
    _runs,
    _script,
)

# Sections 1, 3, 4 and 2 in that order.
VERIFY_ORDER = [
    "setup",
    "ocr-walmart-20x",
    "fs-rate-1200",
    "fb-unpack",
    "ragas-closedbook-fb",
    "kinds-fb-c512",
    "fs-c2048-ingest",
    "fs-c2048-seal",
    "fs-c2048-r0.6b",
    "fs-c2048-r4b",
    "fs-c2048-r8b",
]
FB_COPY = '[ -d "$OUT_DIR/fb/financebench" ] || exit 77; '


def test_verify_runs_the_sections_cheapest_first_after_the_test_session_setup() -> None:
    stages = _read(VERIFY_FILE)[0]
    assert [s.name for s in stages] == VERIFY_ORDER
    assert [s.name for s in stages if s.fatal] == ["setup"]
    assert stages[0].command == _read()[0][0].command
    for stage in stages:  # the pod runs the commit the watcher gives, nothing else
        for word in ("git ", "checkout", "fetch", "verify-fixes", "omrs-fix"):
            assert word not in stage.command, (stage.name, word)


def test_verify_values_are_the_test_session_questions_with_both_overflow_queries() -> None:
    values = _read(VERIFY_FILE)[1]
    assert values == {"FS_QIDS": _read()[1]["FS_QIDS"]}
    assert {"76293427", "77759618"} <= set(values["FS_QIDS"].split(","))


def test_verify_ocr_reads_walmart_twenty_times_with_a_five_minute_limit_each() -> None:
    (call,) = [c for c in _calls(VERIFY_FILE) if c.stage.name == "ocr-walmart-20x"]
    assert _script(call)[:2] == ("prefreeze/verify35.py", "ocr")
    opts = _opts(call.words)
    pdf = "/root/Development/DATA/omrs/benchmarks/financebench/pdfs/WALMART_2019_10K.pdf"
    assert (opts["--pdf"], opts["--passes"], opts["--timeout"]) == (pdf, "20", "300")
    assert call.stage.timeout == "105m"  # 20 passes x 5 min, plus 5 min


def test_verify_rate_times_1200_fresh_freshstack_files_in_200_file_blocks() -> None:
    (call,) = [c for c in _calls(VERIFY_FILE) if c.stage.name == "fs-rate-1200"]
    assert _script(call)[:2] == ("prefreeze/verify35.py", "rate")
    assert _opts(call.words)["--block"] == "200" and call.words[call.start - 1] == "--"
    (args,) = [a for c, a in _runs(VERIFY_FILE) if c is call]
    found = (args.dataset, args.index, args.stage, args.corpus_sample, args.limit, args.qids)
    assert found == ("freshstack", "e4b-c1024", "ingest", 1200, None, None)
    assert (_folder(args.out_dir), args.index_from) == ("fsrate", None)
    assert call.stage.command.count("run_arms.py ") == 1  # the chain may add --resume


def test_verify_reranker_stages_search_the_fresh_c2048_index_with_each_reranker() -> None:
    runs = {c.stage.name: a for c, a in _runs(VERIFY_FILE)}
    qids = _read(VERIFY_FILE)[1]["FS_QIDS"].split(",")
    for name, stage in (("fs-c2048-ingest", "ingest"), ("fs-c2048-seal", "seal")):
        a = runs[name]
        assert (a.dataset, a.index, a.stage, _folder(a.out_dir)) == (
            "freshstack",
            "e4b-c2048",
            stage,
            "s",
        )
    for size in ("0.6b", "4b", "8b"):
        a = runs[f"fs-c2048-r{size}"]
        assert (a.setup, a.stage, a.qids) == (f"e4b-c2048-r{size}-hon", "search", qids)
        assert (_folder(a.index_from), _folder(a.out_dir), a.corpus_sample) == ("s", "search", 300)


def test_verify_answer_checks_run_on_a_copy_unpacked_from_the_inputs() -> None:
    (unpack,) = [c for c in _calls(VERIFY_FILE) if c.stage.name == "fb-unpack"]
    assert _script(unpack)[1] == "unpack"
    assert _opts(_script(unpack)[2]) == {
        "--tarball": "/workspace/inputs/fb-answers.tgz",
        "--dataset": "financebench",
        "--out": f"{OUT}/fb",
    }
    runs = {c.stage.name: (c, a) for c, a in _runs(VERIFY_FILE)}
    call, a = runs["ragas-closedbook-fb"]
    assert (a.setup, a.stage, a.answers) == ("e4b-c1024-r0.6b-hon", "ragas", "closedbook-rag")
    call2, b = runs["kinds-fb-c512"]
    assert (b.setup, b.stage) == ("e4b-c512-r0.6b-hon", "claimkinds")
    for c, x in ((call, a), (call2, b)):
        assert c.stage.command.startswith(FB_COPY), c.stage.name
        assert (x.dataset, _folder(x.out_dir), x.limit, x.corpus_sample) == (
            "financebench",
            "fb",
            20,
            3,
        )
