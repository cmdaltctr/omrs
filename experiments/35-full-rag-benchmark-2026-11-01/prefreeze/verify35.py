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
"""

from __future__ import annotations

import argparse
import fnmatch
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
    args = parser.parse_args(argv)
    if args.cmd == "rate":
        args.command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not args.command:
            parser.error("rate needs -- and the ingest command")
    return {"ocr": ocr, "rate": rate, "unpack": unpack}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
