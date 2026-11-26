"""OSF time-stamp record of Experiment 35 (review S8; pre-registration section 14.2 step 4).

Usage (on the Mac, after the configuration hash is uploaded to the registered
OSF project)::

    osf35.py record --out-dir OUT --uploaded-at 2026-12-01T10:00:00Z --file UPLOADED_FILE

It hashes the uploaded file (SHA-256), copies ``configuration_hash`` from
``OUT/selection.json`` and writes ``OUT/osf-timestamp.json`` atomically, so no
field is typed by hand. The half-B guard (``scoring35.require_half_b``) reads
it. Exit codes: 0 written; 2 refused (no file, no selection, or a time that is
not ISO 8601), and nothing is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

from outputs35 import write_json  # noqa: E402
from scoring35 import SELECTION_FILE, TIMESTAMP_FILE  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    """Write ``osf-timestamp.json``; return 0 (a refusal exits 2)."""
    parser = argparse.ArgumentParser(prog="osf35.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record")
    record.add_argument("--out-dir", type=Path, required=True, help="the run output folder")
    record.add_argument("--uploaded-at", required=True, help="OSF upload time, ISO 8601")
    record.add_argument("--file", type=Path, required=True, help="the file uploaded to OSF")
    args = parser.parse_args(argv)
    try:
        datetime.fromisoformat(args.uploaded_at)
    except ValueError:
        parser.error(f"--uploaded-at {args.uploaded_at!r} is not an ISO 8601 time")
    if not args.file.is_file():
        parser.error(f"--file {args.file} does not exist")
    selection = args.out_dir / SELECTION_FILE
    if not selection.is_file():
        parser.error(f"{selection} does not exist; run select35.py first")
    digest = json.loads(selection.read_text(encoding="utf-8")).get("configuration_hash")
    if not digest:
        parser.error(f"{selection} holds no configuration_hash")
    stamp = {
        "uploaded_at": args.uploaded_at,
        "file_sha256": hashlib.sha256(args.file.read_bytes()).hexdigest(),
        "configuration_hash": digest,
    }
    write_json(args.out_dir / TIMESTAMP_FILE, stamp)
    print(f"[osf] {args.out_dir / TIMESTAMP_FILE}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
