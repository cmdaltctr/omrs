"""Checks on verify35.py, the helper of the fix check pod session (verify_session_stages.txt).

No OCR engine, model or network is used: the OCR passes and the timed ingest run
small Python children that print what the real ones print.
"""

from __future__ import annotations

import inspect
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest
import verify35

PY = sys.executable


def _child(code: str) -> list[str]:
    return [PY, "-c", code]


def test_ocr_counts_a_pass_only_when_it_returns_every_page_in_time(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert verify35.ocr_passes(_child("print(29)"), passes=3, expect=29, timeout=30) == 3
    assert verify35.ocr_passes(_child("print(28)"), passes=2, expect=29, timeout=30) == 0
    slow = _child("import time; time.sleep(30)")
    assert verify35.ocr_passes(slow, passes=1, expect=29, timeout=1) == 0
    assert verify35.ocr_passes(_child("raise SystemExit(3)"), passes=1, expect=29, timeout=30) == 0
    out = capsys.readouterr().out
    assert "[ocr] pass 3/3: 29 pages" in out
    assert "[ocr] pass 1/2: FAILED (28 pages, expected 29)" in out
    assert "[ocr] pass 1/1: FAILED (no result after 1 s)" in out
    assert "[ocr] pass 1/1: FAILED (exit 3)" in out


def test_ocr_main_exits_0_only_when_every_pass_is_good(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake(cmd: list[str], *, passes: int, expect: int, timeout: float) -> int:
        calls.append(cmd)
        assert (passes, expect, timeout) == (20, len(verify35.PAGES), 300)
        return passes - (len(calls) - 1)

    monkeypatch.setattr(verify35, "ocr_passes", fake)
    argv = ["ocr", "--pdf", "/data/WALMART_2019_10K.pdf", "--passes", "20", "--timeout", "300"]
    assert verify35.main(argv) == 0
    assert verify35.main(argv) == 1
    assert calls[0][:2] == [sys.executable, "-c"] and calls[0][3] == "/data/WALMART_2019_10K.pdf"


def test_the_ocr_child_reads_the_fixed_pages_with_the_real_reader() -> None:
    assert verify35.PAGES == list(range(90, 147, 2)) and len(verify35.PAGES) == 29
    compile(verify35.OCR_CODE, "<ocr>", "exec")
    from omrs.integrations.pdf.local_ocr.pp_ocrv6_small import PpOcrV6Small

    assert "settings" in inspect.signature(PpOcrV6Small.read_pages).parameters
    for name in ("PpOcrV6Small", "get_settings", "read_pages"):
        assert name in verify35.OCR_CODE


def test_rate_prints_one_line_per_block_and_passes_the_exit_code_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lines = [f"[ingest] f{i}.md: {i % 3 + 1} chunks" for i in range(450)]
    lines[7] = "[ingest] f7.md: ERROR store refused"
    lines.insert(0, "[ingest] freshstack/e4b-c1024: done earlier, skipped")
    lines.insert(3, "2026-11-24 - INFO - Stored 3 verified chunk(s)")
    code = f"import sys; print({chr(10).join(lines)!r}); sys.exit(4)"
    assert verify35.main(["rate", "--block", "200", "--", PY, "-c", code]) == 4
    out = capsys.readouterr().out.splitlines()
    blocks = [line for line in out if line.startswith("[rate] files")]
    chunks = [sum(i % 3 + 1 for i in range(a, b) if i != 7) for a, b in ((0, 200), (200, 400))]
    assert [b.split(":")[0] for b in blocks] == [
        "[rate] files 1-200",
        "[rate] files 201-400",
        "[rate] files 401-450",
    ]
    assert f", {chunks[0]} chunks" in blocks[0] and f", {chunks[1]} chunks" in blocks[1]
    assert all(" s, " in b and " s/file, " in b for b in blocks)
    assert out[-1].startswith("[rate] total: 450 files in ")
    assert "[ingest] f449.md: 3 chunks" in out  # the child's own lines stay in the log


def _tarball(path: Path, names: list[str]) -> None:
    with tarfile.open(path, "w:gz") as tar:
        for name in names:
            data = f"data of {name}\n".encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


KEEP = [
    "answer/e4b-c512-r0.6b-hon/run1/answer.jsonl",
    "answer/e4b-c512-r0.6b-hon/run1/judge-chat.jsonl",
    "answer/e4b-c512-r0.6b-hon/run1/ragas.jsonl",
    "closedbook-rag/e4b-c1024-r0.6b-hon/run1/answer.jsonl",
    "closedbook-rag/e4b-c1024-r0.6b-hon/run1/.done-answer.json",
    "rebuild.json",
]
DROP = [
    "answer/e4b-c512-r0.6b-hon/run1/claimkinds.key.json",
    "answer/e4b-c512-r0.6b-hon/run1/claim-kinds.jsonl",
    "answer/e4b-c512-r0.6b-hon/run1/.done-claimkinds.json",
    "closedbook-rag/e4b-c1024-r0.6b-hon/run1/ragas.partial.jsonl",
    "closedbook-rag/e4b-c1024-r0.6b-hon/run1/ragas.key.json",
    "closedbook-rag/e4b-c1024-r0.6b-hon/run1/.done-ragas.json",
]
ELSEWHERE = [
    "out/s/financebench/search/e4b-c512-r0.6b-hon/run1/search.jsonl",
    "out/s/financebench/closedbook/e4b-c1024-r0.6b-hon/run1/answer.jsonl",
    "out/s/bioasq/answer/e4b-c512-r0.6b-hon/run1/answer.jsonl",
    "out/s/bioasq/rebuild.json",
]


def test_unpack_copies_the_answers_without_their_ragas_and_claim_kind_results(
    tmp_path: Path,
) -> None:
    tgz = tmp_path / "fb-answers.tgz"
    _tarball(tgz, [f"out/s/financebench/{n}" for n in KEEP + DROP] + ELSEWHERE)
    out = tmp_path / "fb"
    argv = ["unpack", "--tarball", str(tgz), "--dataset", "financebench", "--out", str(out)]
    assert verify35.main(argv) == 0
    found = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    assert found == sorted(f"financebench/{n}" for n in KEEP)
    text = (out / "financebench/rebuild.json").read_text(encoding="utf-8")
    assert text == "data of out/s/financebench/rebuild.json\n"


def test_unpack_skips_without_its_tarball_and_fails_on_a_tarball_without_answers(
    tmp_path: Path,
) -> None:
    out = tmp_path / "fb"
    argv = ["unpack", "--dataset", "financebench", "--out", str(out), "--tarball"]
    assert verify35.main([*argv, str(tmp_path / "absent.tgz")]) == 77
    other = tmp_path / "other.tgz"
    _tarball(other, ELSEWHERE[2:])
    assert verify35.main([*argv, str(other)]) == 1
    assert not (out / "financebench").exists()


def test_unpack_also_copies_the_seal_environment_the_answer_stages_read(tmp_path: Path) -> None:
    # 2026-11-24 verify pod: ragas-closedbook-fb and kinds-fb-c512 stopped with
    # "out/fb/environment.json is missing" because unpack copied only the answers.
    tgz = tmp_path / "fb-answers.tgz"
    _tarball(tgz, [f"out/s/financebench/{n}" for n in KEEP] + ["out/s/environment.json"])
    out = tmp_path / "fb"
    argv = ["unpack", "--tarball", str(tgz), "--dataset", "financebench", "--out", str(out)]
    assert verify35.main(argv) == 0
    text = (out / "environment.json").read_text(encoding="utf-8")
    assert text == "data of out/s/environment.json\n"


# --- the pre-freeze pod check (freeze_check_stages.txt) -----------------------------------


def _json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _expected(tmp_path: Path, files: dict[str, int]) -> Path:
    return _json(tmp_path / "expected.json", {"samples": {"fsrate": {"files": files}}})


def test_chunks_passes_only_when_every_file_has_the_mac_count(tmp_path: Path) -> None:
    expected = _expected(tmp_path, {"a.md": 2, "b.md": 1})
    good = _json(tmp_path / "good.json", {"files": {"a.md": 2, "b.md": 1}, "failed": []})
    assert verify35.main(["chunks", str(good), "--expected", str(expected)]) == 0
    for name, summary in (
        ("count", {"files": {"a.md": 3, "b.md": 1}, "failed": []}),
        ("zero", {"files": {"a.md": 2, "b.md": 0}, "failed": []}),
        ("missing", {"files": {"a.md": 2}, "failed": []}),
        ("failed", {"files": {"a.md": 2}, "failed": ["b.md"]}),
        ("extra", {"files": {"a.md": 2, "b.md": 1, "c.md": 1}, "failed": []}),
    ):
        path = _json(tmp_path / f"{name}.json", summary)
        assert verify35.main(["chunks", str(path), "--expected", str(expected)]) == 1, name


def test_chunks_names_each_difference(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    expected = _expected(tmp_path, {"a.md": 2, "b.md": 1})
    summary = _json(tmp_path / "s.json", {"files": {"a.md": 3, "b.md": 0}, "failed": []})
    verify35.main(["chunks", str(summary), "--expected", str(expected), "--sample", "fsrate"])
    out = capsys.readouterr().out
    assert "a.md: 3 chunks, the Mac gives 2" in out and "b.md: 0 chunks" in out
    assert "[chunks] FAILED: 2 of 2 files differ" in out


def test_expect_checks_each_field_of_each_matching_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("x", "y"):
        _json(tmp_path / name / "s.json", {"missing": 0, "seal": {"sha": "ab", "list": []}})
    pattern = str(tmp_path / "*" / "s.json")
    good = ["expect", pattern, "--count", "2", "missing=0", "seal.sha=ab", "seal.list=[]"]
    assert verify35.main(good) == 0
    assert verify35.main(["expect", pattern, "--count", "2", "missing=1"]) == 1
    assert verify35.main(["expect", pattern, "--count", "3", "missing=0"]) == 1
    assert verify35.main(["expect", pattern, "--count", "2", "nothing=0"]) == 1
    out = capsys.readouterr().out
    assert "missing is 0, expected 1" in out and "2 files match, expected 3" in out
    assert "nothing is absent" in out


def test_expect_reads_the_json_of_a_dry_run_plan_after_its_first_line(tmp_path: Path) -> None:
    plan = tmp_path / "dry.txt"
    body = json.dumps({"resolved": {"file_type_routing": False}}, indent=2)
    plan.write_text("[dry-run] nothing started, nothing sent\n" + body + "\n", encoding="utf-8")
    assert verify35.main(["expect", str(plan), "resolved.file_type_routing=false"]) == 0
    assert verify35.main(["expect", str(plan), "resolved.file_type_routing=true"]) == 1


def _answers(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_finish_tallies_the_finish_reasons_and_refuses_a_row_without_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = _answers(
        tmp_path / "a" / "answer.jsonl",
        [
            {"qid": "1", "finish_reasons": ["stop"], "output_tokens": 300},
            {"qid": "2", "finish_reasons": ["length"], "output_tokens": 2048},
            {"qid": "3", "missing": True},
        ],
    )
    out = tmp_path / "finish.json"
    assert verify35.main(["finish", str(good), "--cap", "2048", "--out", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["files"][str(good)] == {
        "rows": 3,
        "missing": 1,
        "reasons": {"length": 1, "stop": 1},
    }
    assert report["ok"] is True
    for name, row in (
        ("none", {"qid": "1", "output_tokens": 10}),
        ("null", {"qid": "1", "finish_reasons": [None], "output_tokens": 10}),
        ("over", {"qid": "1", "finish_reasons": ["stop"], "output_tokens": 2049}),
    ):
        bad = _answers(tmp_path / name / "answer.jsonl", [row])
        assert verify35.main(["finish", str(bad), "--cap", "2048", "--out", str(out)]) == 1, name
    assert "no finish reason" in capsys.readouterr().out
    assert verify35.main(["finish", str(tmp_path / "nope.jsonl"), "--cap", "2048"]) == 1


def test_chunks_without_a_mac_count_needs_files_none_failed_and_none_empty(tmp_path: Path) -> None:
    good = _json(tmp_path / "good.json", {"files": {"a.pdf": 9}, "failed": []})
    assert verify35.main(["chunks", str(good)]) == 0
    for name, summary in (
        ("zero", {"files": {"a.pdf": 9, "b.pdf": 0}, "failed": []}),
        ("failed", {"files": {"a.pdf": 9}, "failed": ["b.pdf"]}),
        ("empty", {"files": {}, "failed": []}),
    ):
        path = _json(tmp_path / f"{name}.json", summary)
        assert verify35.main(["chunks", str(path)]) == 1, name


def test_chunks_checks_every_summary_it_names(tmp_path: Path) -> None:
    good = _json(tmp_path / "good.json", {"files": {"a.pdf": 9}, "failed": []})
    bad = _json(tmp_path / "bad.json", {"files": {"a.pdf": 0}, "failed": []})
    assert verify35.main(["chunks", str(good), str(good)]) == 0
    assert verify35.main(["chunks", str(bad), str(good)]) == 1
    assert verify35.main(["chunks", str(good), str(bad)]) == 1
