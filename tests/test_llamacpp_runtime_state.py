"""State root resolution and the atomic ``server.json`` (design D3).

The state root comes from the environment alone so the CLI, which cannot
see ``omrs web`` flags, agrees with the web app. ``server.json`` is written
to a temporary file and renamed, so no reader ever sees a partial record,
and a broken file reads as no record.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from omrs.integrations.llamacpp_runtime.state import (
    SERVER_FILE,
    ServerRecord,
    read_server_record,
    runtime_dir,
    state_root,
    write_server_record,
)


def test_each_root_source_in_order(monkeypatch) -> None:
    monkeypatch.delenv("OMRS_STATE_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", "/home/example")
    assert state_root() == Path("/home/example/.local/state/omrs")
    monkeypatch.setenv("XDG_STATE_HOME", "/xdg")
    assert state_root() == Path("/xdg/omrs")
    monkeypatch.setenv("OMRS_STATE_DIR", "/tmp/s")
    assert state_root() == Path("/tmp/s")


def test_the_autouse_fixture_keeps_the_root_out_of_the_home_folder(
    tmp_path: Path,
) -> None:
    root = state_root()
    assert Path(os.environ["OMRS_STATE_DIR"]) == root
    assert not root.is_relative_to(Path.home())
    assert "omrs-state" in str(root)


def test_runtime_folder_layout_and_id_rule(tmp_path: Path) -> None:
    assert runtime_dir(tmp_path, "chat") == tmp_path / "runtimes" / "chat"
    assert (
        runtime_dir(tmp_path, "ocr-dots-mocr-llamacpp")
        == tmp_path / "runtimes" / "ocr-dots-mocr-llamacpp"
    )
    for bad in ("../chat", "chat/../../x", "ocr-/../escape", "", "Chat"):
        try:
            runtime_dir(tmp_path, bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} must be refused")


def _record(**over) -> ServerRecord:
    values = dict(
        pid=123,
        port=8081,
        binary="/b/llama-server",
        digest="0" * 64,
        build=None,
        state="running",
        stopped_by=None,
        generation=3,
        reason=None,
    )
    values.update(over)
    return ServerRecord(**values)


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    folder = runtime_dir(tmp_path, "chat")
    write_server_record(folder, _record())
    assert read_server_record(folder) == _record()
    assert (folder / SERVER_FILE).exists()


def test_a_broken_file_reads_as_no_record(tmp_path: Path) -> None:
    folder = runtime_dir(tmp_path, "chat")
    folder.mkdir(parents=True)
    (folder / SERVER_FILE).write_text("{not json", encoding="utf-8")
    assert read_server_record(folder) is None


def test_a_missing_file_reads_as_no_record(tmp_path: Path) -> None:
    assert read_server_record(runtime_dir(tmp_path, "chat")) is None


def test_a_write_never_leaves_a_partial_file(tmp_path: Path) -> None:
    folder = runtime_dir(tmp_path, "chat")
    write_server_record(folder, _record(state="starting", generation=1))
    write_server_record(folder, _record(state="running", generation=2))
    assert not (folder / f"{SERVER_FILE}.tmp").exists()
    text = (folder / SERVER_FILE).read_text(encoding="utf-8")
    assert json.loads(text)["generation"] == 2  # the whole record, always valid JSON


def test_every_record_field_survives_the_round_trip(tmp_path: Path) -> None:
    folder = runtime_dir(tmp_path, "chat")
    write_server_record(
        folder,
        _record(
            build=11941,
            state="stopped",
            stopped_by="operator",
            generation=9,
            reason="wrong-build",
        ),
    )
    record = read_server_record(folder)
    assert record is not None
    assert record.build == 11941
    assert record.state == "stopped"
    assert record.stopped_by == "operator"
    assert record.generation == 9
    assert record.reason == "wrong-build"


def test_a_crash_during_the_write_keeps_the_old_record(tmp_path: Path, monkeypatch) -> None:
    folder = runtime_dir(tmp_path, "chat")
    write_server_record(folder, _record(state="running", generation=4))
    real_write = type(folder / SERVER_FILE).write_text

    def crashing_write(self, data, encoding=None):
        # Simulate a crash halfway: a partial write to this file, then death.
        real_write(self, data[:5], encoding=encoding)
        raise RuntimeError("crashed mid-write")

    monkeypatch.setattr("pathlib.Path.write_text", crashing_write)
    try:
        write_server_record(folder, _record(state="stopped", generation=5))
    except RuntimeError:
        pass
    finally:
        monkeypatch.setattr("pathlib.Path.write_text", real_write)
    record = read_server_record(folder)
    assert record is not None
    assert record.generation == 4, "the old record must survive a crashed write"
