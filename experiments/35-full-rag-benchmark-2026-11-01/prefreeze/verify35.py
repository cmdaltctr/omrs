"""Helpers of the Experiment 35 fix check session (verify_session_stages.txt).

Run from the Experiment 35 folder, through ``uv run --no-sync python``:

  ocr     read 29 pages of one PDF with PP-OCRv6 small in a fresh process, N times;
          each pass must return every page within its time limit (fix 0bebdb1d).
  rate    run a ``run_arms.py --stage ingest`` command and print one line per block of
          files: files, wall seconds, seconds per file, chunks (fix bcd11389). Block 1
          includes the engine start. The command's exit code is returned.
  unpack  copy the ``answer`` and ``closedbook-rag`` folders and ``rebuild.json`` of one
          dataset out of a session tarball, without their Ragas and claim-kind results
          (fix b98f536f). Exit 77 (the chain's "skipped") when the tarball is absent.

The pre-freeze pod check (freeze_check_stages.txt) adds three read-only checks. Each
prints one line per finding and exits 0 (pass) or 1 (fail):

  chunks  compare an ``ingest-summary.json`` with the Mac chunk counts of the same
          files (fs_chunks_c1024_expected.json): every file present, none failed,
          none with 0 chunks, each count equal.
  expect  check fields of JSON files: ``PATH=VALUE`` with a dotted path and a JSON
          value (a bare word is a string). A glob names several files; ``--count``
          sets how many must match. A dry-run plan (one text line, then JSON) reads too.
  finish  tally the ``finish_reasons`` of answer rows (amendment A7): every answered
          row has at least one, none is null, and ``output_tokens`` stays within
          ``--cap`` per reply. ``--out`` writes the tally.
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import re
import subprocess
import sys
import tarfile
import time
from collections.abc import Sequence
from pathlib import Path

PAGES = list(range(90, 147, 2))
OCR_CODE = """
import sys
from pathlib import Path
from omrs.compose import get_settings
from omrs.integrations.pdf.local_ocr.pp_ocrv6_small import PpOcrV6Small
pages = [int(p) for p in sys.argv[2].split(",")]
print(len(PpOcrV6Small().read_pages(Path(sys.argv[1]), pages, settings=get_settings())))
"""
_FILE = re.compile(r"^\[ingest\] .+: (?:ERROR .*|(\d+) chunks)$")
KEEP = ("answer/", "closedbook-rag/", "rebuild.json")
SEAL_ENV = "out/s/environment.json"
DROP = (
    "closedbook-rag/*/run1/ragas*",
    "closedbook-rag/*/run1/.done-ragas*",
    "answer/*/run1/claim-kinds*",
    "answer/*/run1/claimkinds*",
    "answer/*/run1/.done-claimkinds*",
)


def say(text: str) -> None:
    print(text, flush=True)


def ocr_passes(cmd: list[str], *, passes: int, expect: int, timeout: float) -> int:
    """Run *cmd* *passes* times; return how many printed *expect* in time."""
    good = 0
    for n in range(1, passes + 1):
        started = time.monotonic()
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)  # noqa: S603
        except subprocess.TimeoutExpired:
            say(f"[ocr] pass {n}/{passes}: FAILED (no result after {timeout:g} s)")
            continue
        seconds = time.monotonic() - started
        found = (done.stdout.strip().splitlines() or [""])[-1]
        if done.returncode != 0:
            say(f"[ocr] pass {n}/{passes}: FAILED (exit {done.returncode}) {done.stderr[-300:]}")
        elif found != str(expect):
            say(f"[ocr] pass {n}/{passes}: FAILED ({found or 'no'} pages, expected {expect})")
        else:
            good += 1
            say(f"[ocr] pass {n}/{passes}: {expect} pages in {seconds:.1f} s")
    return good


def ocr(args: argparse.Namespace) -> int:
    cmd = [sys.executable, "-c", OCR_CODE, str(args.pdf), ",".join(map(str, PAGES))]
    good = ocr_passes(cmd, passes=args.passes, expect=len(PAGES), timeout=args.timeout)
    say(f"[ocr] {good}/{args.passes} passes returned {len(PAGES)} pages in time")
    return 0 if good == args.passes else 1


def rate(args: argparse.Namespace) -> int:
    started = last = time.monotonic()
    files = chunks = first = 0

    def block() -> None:
        nonlocal last, chunks, first
        now = time.monotonic()
        seconds, count = now - last, files - first
        say(
            f"[rate] files {first + 1}-{files}: {seconds:.1f} s, "
            f"{seconds / count:.2f} s/file, {chunks} chunks"
        )
        last, chunks, first = now, 0, files

    child = subprocess.Popen(args.command, stdout=subprocess.PIPE, text=True, bufsize=1)  # noqa: S603
    for line in child.stdout or ():
        print(line, end="", flush=True)
        found = _FILE.match(line.rstrip("\n"))
        if found:
            files, chunks = files + 1, chunks + int(found[1] or 0)
            if files - first == args.block:
                block()
    code = child.wait()
    if files > first:
        block()
    say(f"[rate] total: {files} files in {time.monotonic() - started:.1f} s (exit {code})")
    return code


def unpack(args: argparse.Namespace) -> int:
    if not args.tarball.is_file():
        say(f"[unpack] {args.tarball} is not on the pod: skipped")
        return 77
    prefix, copied = f"out/s/{args.dataset}/", 0
    with tarfile.open(args.tarball) as tar:
        for member in tar:
            if member.name == SEAL_ENV and member.isfile():
                # The answer stages refuse to start without the seal record beside them.
                member.name = "environment.json"
                tar.extract(member, args.out, filter="data")
                continue
            rel = member.name.removeprefix(prefix)
            wanted = rel != member.name and rel.startswith(KEEP) and member.isfile()
            if not wanted or any(fnmatch.fnmatch(rel, p) for p in DROP):
                continue
            member.name = f"{args.dataset}/{rel}"
            tar.extract(member, args.out, filter="data")
            copied += 1
    if not copied:
        say(f"[unpack] {args.tarball} holds no {prefix}answer files")
        return 1
    say(f"[unpack] {copied} files of {prefix} into {args.out / args.dataset}")
    return 0


def _load(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except ValueError:
        return json.loads(text[text.index("\n{") + 1 :])  # a dry-run plan: JSON after line 1


def chunks(args: argparse.Namespace) -> int:
    codes = [_chunks_one(path, args) for path in args.summaries]
    return max(codes)


def _chunks_one(path: Path, args: argparse.Namespace) -> int:
    summary = json.loads(path.read_text(encoding="utf-8"))
    found, failed = summary.get("files") or {}, list(summary.get("failed") or [])
    if args.expected is None:  # no Mac count (PDFs): every file ingested, none with 0 chunks
        want = {n: max(int(c), 1) for n, c in found.items()} or {"(no file)": 1}
    else:
        samples = json.loads(args.expected.read_text(encoding="utf-8"))["samples"]
        want = samples[args.sample]["files"]
    bad = [f"{n}: failed to ingest" for n in failed]
    for name in sorted(set(want) | set(found)):
        if name in failed:
            continue
        if name not in found:
            bad.append(f"{name}: not in the summary")
        elif name not in want:
            bad.append(f"{name}: not in the Mac sample")
        elif found[name] == 0 or found[name] != want[name]:
            bad.append(f"{name}: {found[name]} chunks, the Mac gives {want[name]}")
    for line in bad:
        say(f"[chunks] {line}")
    total = sum(int(v) for v in found.values())
    if bad:
        say(f"[chunks] FAILED: {len(bad)} of {len(want)} files differ ({path})")
        return 1
    rule = "every count equals the Mac count" if args.expected else "none failed, none empty"
    say(f"[chunks] {path}: {len(want)} files, {total} chunks: {rule}")
    return 0


def _field(data: object, path: str) -> tuple[bool, object]:
    for part in path.split("."):
        if not isinstance(data, dict) or part not in data:
            return False, None
        data = data[part]
    return True, data


def _value(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        return text


def expect(args: argparse.Namespace) -> int:
    paths = sorted(Path(p) for p in glob.glob(args.pattern))
    bad = 0
    if args.count is not None and len(paths) != args.count:
        say(f"[expect] {args.pattern}: {len(paths)} files match, expected {args.count}")
        bad += 1
    if not paths:
        say(f"[expect] {args.pattern}: no file")
        return 1
    for path in paths:
        data = _load(path)
        for check in args.checks:
            name, _, text = check.partition("=")
            present, found = _field(data, name)
            if not present:
                say(f"[expect] {path}: {name} is absent")
                bad += 1
            elif found != _value(text):
                say(f"[expect] {path}: {name} is {json.dumps(found)}, expected {text}")
                bad += 1
    if bad:
        say(f"[expect] FAILED: {bad} check(s) of {args.pattern}")
        return 1
    say(f"[expect] {len(paths)} file(s), {len(args.checks)} field(s) each: ok ({args.pattern})")
    return 0


def finish(args: argparse.Namespace) -> int:
    paths = sorted(Path(p) for pattern in args.paths for p in glob.glob(pattern))
    report: dict[str, object] = {"cap": args.cap, "files": {}}
    bad = 0 if paths else 1
    if not paths:
        say(f"[finish] no answer file matches {' '.join(args.paths)}")
    for path in paths:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        reasons: dict[str, int] = {}
        for row in rows:
            if row.get("missing"):
                continue
            found = row.get("finish_reasons") or []
            if not found or None in found:
                say(f"[finish] {path}: {row.get('qid')}: no finish reason on every reply")
                bad += 1
            if int(row.get("output_tokens") or 0) > args.cap * max(len(found), 1):
                say(f"[finish] {path}: {row.get('qid')}: output tokens above the cap {args.cap}")
                bad += 1
            for reason in found:
                reasons[str(reason)] = reasons.get(str(reason), 0) + 1
        missing = sum(1 for r in rows if r.get("missing"))
        entry = {"rows": len(rows), "missing": missing, "reasons": dict(sorted(reasons.items()))}
        report["files"][str(path)] = entry  # type: ignore[index]
        say(f"[finish] {path}: {entry['reasons']}")
    report["ok"] = bad == 0
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if bad == 0 else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ocr", help="N fresh OCR reads of 29 pages of one PDF")
    p.add_argument("--pdf", type=Path, required=True)
    p.add_argument("--passes", type=int, default=20)
    p.add_argument("--timeout", type=float, default=300, help="seconds per pass")
    p = sub.add_parser("rate", help="time an ingest command per block of files")
    p.add_argument("--block", type=int, default=200)
    p.add_argument("command", nargs=argparse.REMAINDER, help="-- then the ingest command")
    p = sub.add_parser("unpack", help="copy one dataset's answers out of a session tarball")
    p.add_argument("--tarball", type=Path, required=True)
    p.add_argument("--dataset", required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("chunks", help="compare an ingest summary with the Mac chunk counts")
    p.add_argument("summaries", nargs="+", type=Path, help="ingest-summary.json files")
    p.add_argument("--expected", type=Path, help="fs_chunks_c1024_expected.json (default: none)")
    p.add_argument("--sample", default="fsrate", help="the sample of the expected file")
    p = sub.add_parser("expect", help="check fields of JSON files (PATH=VALUE)")
    p.add_argument("pattern", help="a JSON file, or a glob")
    p.add_argument("checks", nargs="+", help="PATH=VALUE, PATH dotted, VALUE JSON")
    p.add_argument("--count", type=int, help="how many files must match")
    p = sub.add_parser("finish", help="tally the finish reasons of answer rows")
    p.add_argument("paths", nargs="+", help="answer.jsonl files or globs")
    p.add_argument("--cap", type=int, required=True, help="the max_tokens cap per reply")
    p.add_argument("--out", type=Path, help="write the tally here")
    args = parser.parse_args(argv)
    if args.cmd == "rate":
        args.command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not args.command:
            parser.error("rate needs -- and the ingest command")
    commands = {"ocr": ocr, "rate": rate, "unpack": unpack, "chunks": chunks}
    return {**commands, "expect": expect, "finish": finish}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
