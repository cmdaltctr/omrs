"""Experiment 35 OSF time-stamp record, ``osf35.py record`` (review S8; pre-registration 14.2).

The record holds ``uploaded_at``, ``file_sha256`` (hashed from the uploaded
file, never typed) and ``configuration_hash`` (copied from ``selection.json``).
It is written atomically and opens the half-B guard.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tests._exp35_fixtures import load

osf35 = load("osf35")
scoring35 = load("scoring35")


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    out = tmp_path / "out"
    out.mkdir()
    (out / "selection.json").write_text(json.dumps({"configuration_hash": "c" * 64}))
    upload = tmp_path / "configuration-hash.txt"
    upload.write_text("c" * 64 + "\n")
    return out, upload


def _record(out: Path, upload: Path, when: str = "2026-12-01T10:00:00Z") -> int:
    argv = ["record", "--out-dir", str(out), "--uploaded-at", when, "--file", str(upload)]
    return osf35.main(argv)


def test_record_hashes_the_file_and_copies_the_configuration_hash(tmp_path: Path) -> None:
    out, upload = _setup(tmp_path)
    assert _record(out, upload) == 0
    saved = json.loads((out / "osf-timestamp.json").read_text())
    assert saved == {
        "uploaded_at": "2026-12-01T10:00:00Z",
        "file_sha256": hashlib.sha256(upload.read_bytes()).hexdigest(),
        "configuration_hash": "c" * 64,
    }
    assert not list(out.glob("*.tmp"))  # written atomically
    scoring35.require_half_b(out)  # the guard opens


@pytest.mark.parametrize("broken", ["no file", "no selection", "bad time"])
def test_record_refuses_and_writes_nothing(tmp_path: Path, broken: str) -> None:
    out, upload = _setup(tmp_path)
    when = "2026-12-01T10:00:00Z"
    if broken == "no file":
        upload.unlink()
    elif broken == "no selection":
        (out / "selection.json").unlink()
    else:
        when = "yesterday"
    with pytest.raises(SystemExit) as caught:
        _record(out, upload, when)
    assert caught.value.code == 2
    assert not (out / "osf-timestamp.json").exists()
