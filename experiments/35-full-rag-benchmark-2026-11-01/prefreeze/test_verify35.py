"""Checks on verify35.py, the helper of the fix check pod session (verify_session_stages.txt).

No OCR engine, model or network is used: the OCR passes and the timed ingest run
small Python children that print what the real ones print.
"""

from __future__ import annotations

import inspect
import io
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
