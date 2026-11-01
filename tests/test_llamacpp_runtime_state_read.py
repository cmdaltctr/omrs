"""``read_server_record`` never raises, whatever the file holds (design D3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omrs.integrations.llamacpp_runtime.state import SERVER_FILE, read_server_record

GOOD = {"pid": 1, "port": 2, "binary": "/b/llama-server", "digest": "d"}


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        "[1, 2]",
        '"text"',
        "null",
        "42",
        "{}",
        json.dumps({k: v for k, v in GOOD.items() if k != "pid"}),
        json.dumps({k: v for k, v in GOOD.items() if k != "digest"}),
        json.dumps({**GOOD, "pid": "not a number"}),
        json.dumps({**GOOD, "port": None}),
        '{"pid": 1, "port": ',
        "\x00\x01",
    ],
)
def test_a_file_that_is_not_a_record_reads_as_no_record(tmp_path: Path, text: str) -> None:
    (tmp_path / SERVER_FILE).write_text(text, encoding="utf-8")
    assert read_server_record(tmp_path) is None


def test_a_minimal_record_reads_with_defaults(tmp_path: Path) -> None:
    (tmp_path / SERVER_FILE).write_text(json.dumps(GOOD), encoding="utf-8")
    record = read_server_record(tmp_path)
    assert record is not None
    assert (record.state, record.stopped_by, record.generation, record.reason) == (
        "starting",
        None,
        1,
        None,
    )


def test_a_file_that_is_not_utf8_reads_as_no_record(tmp_path: Path) -> None:
    (tmp_path / SERVER_FILE).write_bytes(b"\xff\xfe{")
    assert read_server_record(tmp_path) is None
