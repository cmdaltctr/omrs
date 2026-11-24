"""Checks on p2_session_stages.txt, the P2 pod session (2026-11-24 notes).

pod_test_session.sh runs the file unchanged. test_session_stages.py runs the general
checks on it (parsing, scripts and their options, no key, a timeout on every stage).
These tests check what P2 needs: the test session setup, 1,200-file rate samples of
four indexes, the zero-error recheck in every answer-setup shape (task 10.1), and the
timed full-corpus FreshStack build of e8b-c512, in that order, inside the session cap.
"""

from __future__ import annotations

from test_session_stages import (
    P2_FILE,
    RECHECK,
    _calls,
    _folder,
    _opts,
    _read,
    _runs,
    _script,
)
from tests._exp35_fixtures import load

arms = load("arms")

SAMPLES = ["e0.6b-c1024", "e8b-c1024", "e4b-c512", "e4b-c2048"]
#: The index each chunk size of the recheck reads. This session builds no e4b-c1024,
#: so c1024 reads the smallest index it builds at that size: the e0.6b sample.
RECHECK_INDEX = {512: "e4b-c512", 1024: "e0.6b-c1024", 2048: "e4b-c2048"}
SHAPES = [s.name.removeprefix("e4b-") for s in arms.answer_setups("4b", "0.6b")]
P2_ORDER = [
    "setup",
    *(f"rate-{i}" for i in SAMPLES),
    *(f"seal-{RECHECK_INDEX[c]}" for c in (512, 1024, 2048)),
    *(f"recheck-{shape}" for shape in SHAPES),
    "fsfull-e8b-c512",
    "fsfull-seal",
]
LOCAL, PASSAGES = "/root/exp35-local", "/workspace/passages"
CAP_MIN = 15 * 60  # pod_test_session.sh SESSION_CAP default


def _minutes(timeout: str) -> int:
    return int(timeout[:-1]) * {"m": 1, "h": 60}[timeout[-1]]


def _stages() -> dict[str, object]:
    return {s.name: s for s in _read(P2_FILE)[0]}


def test_p2_runs_the_quick_checks_before_the_full_build_after_the_test_session_setup() -> None:
    stages = _read(P2_FILE)[0]
    assert [s.name for s in stages] == P2_ORDER
    assert len(SHAPES) == 15  # 12 crossed answer setups and 3 token-matched ones
    assert [s.name for s in stages if s.fatal] == ["setup"]
    assert stages[0].command == _read()[0][0].command
    for stage in stages:  # the pod runs the commit the watcher gives, nothing else
        for word in ("git ", "checkout", "fetch", "omrs-fix"):
            assert word not in stage.command, (stage.name, word)


def test_p2_values_are_the_test_session_model_folder_only() -> None:
    # No stage reads FS_QIDS: the recheck names its two questions, the builds take none.
    values = _read(P2_FILE)[1]
    assert values == {"SWEEP_GGUF_DIR": "/root/gguf"}
    assert values["SWEEP_GGUF_DIR"] == _read()[1]["SWEEP_GGUF_DIR"]


def test_every_timeout_fits_the_session_cap_and_the_full_build_gets_eight_hours() -> None:
    minutes = {s.name: _minutes(s.timeout) for s in _read(P2_FILE)[0]}
    assert sum(minutes.values()) <= CAP_MIN  # the cap never cuts the last stage short
    assert minutes["fsfull-e8b-c512"] == 8 * 60  # 2 x the 4.0 h flat projection
    assert minutes["fsfull-seal"] == 20 and minutes["setup"] == 60
    assert {minutes[f"rate-{i}"] for i in SAMPLES} == {40}
    assert {minutes[n] for n in minutes if n.startswith(("seal-", "recheck-"))} == {10}


def _wrapped(name: str) -> tuple[object, object]:
    (call,) = [c for c in _calls(P2_FILE) if c.stage.name == name]
    assert _script(call)[:2] == ("prefreeze/verify35.py", "rate"), name
    assert _opts(call.words)["--block"] == "200" and call.words[call.start - 1] == "--", name
    assert call.stage.command.count("run_arms.py ") == 1, name  # the chain may add --resume
    (args,) = [a for c, a in _runs(P2_FILE) if c is call]
    return call, args


def test_the_full_build_is_the_whole_freshstack_corpus_timed_per_block_then_sealed() -> None:
    _, a = _wrapped("fsfull-e8b-c512")
    found = (a.dataset, a.index, a.stage, a.corpus_sample, a.limit, a.qids)
    assert found == ("freshstack", "e8b-c512", "ingest", None, None, None)
    where = (_folder(a.out_dir), str(a.passages_dir), str(a.local_dir))
    assert where == ("fsfull", PASSAGES, LOCAL)
    (seal,) = [a for c, a in _runs(P2_FILE) if c.stage.name == "fsfull-seal"]
    assert (seal.index, seal.stage, _folder(seal.out_dir)) == ("e8b-c512", "seal", "fsfull")
    assert (seal.corpus_sample, seal.limit, seal.qids, str(seal.passages_dir)) == (
        None,
        None,
        None,
        PASSAGES,
    )


def test_each_rate_sample_ingests_1200_files_into_its_own_fresh_folder() -> None:
    folders = []
    for index in SAMPLES:
        _, a = _wrapped(f"rate-{index}")
        found = (a.dataset, a.index, a.stage, a.corpus_sample, a.limit, a.qids, a.index_from)
        assert found == ("freshstack", index, "ingest", 1200, None, None, None)
        assert str(a.passages_dir) == PASSAGES
        folders.append(_folder(a.out_dir))
    assert folders == [f"rate-{i}" for i in SAMPLES]
    # Only the seal of a recheck index writes into a sample folder after its rate stage.
    later = {(c.stage.name, _folder(a.out_dir)) for c, a in _runs(P2_FILE)}
    later = {pair for pair in later if not pair[0].startswith("rate-") and pair[1] in folders}
    assert later == {(f"seal-{i}", f"rate-{i}") for i in RECHECK_INDEX.values()}


def test_the_recheck_indexes_are_sealed_in_place_before_the_recheck() -> None:
    names = [s.name for s in _read(P2_FILE)[0]]
    for index in RECHECK_INDEX.values():
        (a,) = [a for c, a in _runs(P2_FILE) if c.stage.name == f"seal-{index}"]
        found = (a.index, a.stage, a.corpus_sample, str(a.passages_dir), _folder(a.out_dir))
        assert found == (index, "seal", 1200, PASSAGES, f"rate-{index}")
        assert names.index(f"rate-{index}") < names.index(f"seal-{index}")
        assert names.index(f"seal-{index}") < min(i for i, n in enumerate(names) if "recheck" in n)


def test_the_recheck_answers_and_judges_two_questions_in_every_answer_setup_shape() -> None:
    stages = _stages()
    for shape in SHAPES:
        name = f"recheck-{shape}"
        chunk = int(shape.split("-")[0].removeprefix("c"))
        index = RECHECK_INDEX[chunk]
        runs = [a for c, a in _runs(P2_FILE) if c.stage.name == name]
        assert [a.stage for a in runs] == ["answer", "judge"], name
        for a in runs:
            assert a.setup == f"{index.split('-')[0]}-{shape}", name
            assert (a.dataset, tuple(a.qids), a.limit, a.corpus_sample) == (
                "freshstack",
                RECHECK,
                None,
                None,
            )
            assert (_folder(a.index_from), _folder(a.out_dir)) == (f"rate-{index}", "r"), name
        assert runs[0].answer_host == "deepinfra/fp8" and runs[1].judges == "chat,clef_flash"
        command = stages[name].command
        # Only && joins the two calls, so the judge runs only after a clean answer stage.
        assert command.count(" && ") == 1, name
        assert not any(sep in command for sep in (";", "||", " & ", "|")), name
