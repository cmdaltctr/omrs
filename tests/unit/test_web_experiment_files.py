"""Reading experiment files (experiments-in-web-workspace D6, task 3.4)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_web_experiment_library_support import (  # noqa: E402
    FIRST,
    add_project,
    make_project,
    open_client,
)

from omrs.core.workspace import experiment_pages as pages  # noqa: E402

MIB = 1024 * 1024


@pytest.fixture
def web(tmp_path: Path, effective_settings: Any):  # type: ignore[no-untyped-def]
    root = make_project(tmp_path)
    with open_client(tmp_path, effective_settings()) as (client, policy, app):
        project_id = add_project(client, root)["project_id"]
        yield client, root / "experiments" / FIRST, f"/v1/experiment-projects/{project_id}"


def _get(web: Any, name: str, folder: str = FIRST) -> Any:
    client, _, base = web
    return client.get(f"{base}/experiments/{folder}/files/{name}")


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("notes.md", "# Notes"),
        ("data.json", "{}"),
        ("rows.jsonl", "{}\n"),
        ("log.txt", "ok"),
        ("table.csv", "a,b"),
        ("conf.yaml", "a: 1"),
        ("conf.yml", "b: 2"),
        ("analysis.py", "print(1)"),
    ],
)
def test_allowed_suffixes_return_json_text(web: Any, name: str, text: str) -> None:
    (web[1] / name).write_text(text, encoding="utf-8")
    response = _get(web, name)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "status": "ok",
        "name": name,
        "text": text,
        "truncated": False,
        "size": len(text),
    }


def test_an_html_review_page_is_refused(web: Any) -> None:
    response = _get(web, "review.html")
    assert response.status_code == 400
    assert "<script>" not in response.text


@pytest.mark.parametrize("name", ["..secret.md", ".hidden.md", "a\\b.md"])
def test_unsafe_names_are_refused(web: Any, name: str) -> None:
    assert _get(web, name).status_code == 400


def test_a_missing_file_is_404(web: Any) -> None:
    assert _get(web, "absent.md").status_code == 404


def test_a_file_of_an_unknown_folder_is_404(web: Any) -> None:
    assert _get(web, "report.md", folder="9-nope-2026-01-01").status_code == 404


def test_a_link_pointing_out_of_the_folder_is_refused(web: Any, tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("private", encoding="utf-8")
    (web[1] / "leak.txt").symlink_to(secret)
    response = _get(web, "leak.txt")
    assert response.status_code == 400
    assert "private" not in response.text


def test_a_file_over_one_mib_is_cut(web: Any) -> None:
    (web[1] / "big.txt").write_bytes(b"a" * (MIB + 10))
    body = _get(web, "big.txt").json()
    assert body["truncated"] is True
    assert len(body["text"]) == MIB
    assert body["size"] == MIB + 10


def test_a_file_of_exactly_one_mib_is_not_cut(web: Any) -> None:
    (web[1] / "edge.txt").write_bytes(b"a" * MIB)
    assert _get(web, "edge.txt").json()["truncated"] is False


def test_invalid_utf8_is_replaced(web: Any) -> None:
    (web[1] / "bytes.txt").write_bytes(b"ok \xff end")
    assert _get(web, "bytes.txt").json()["text"] == "ok � end"


@pytest.mark.parametrize("name", ["../../secret.txt", "sub/report.md", "..", ".env"])
def test_names_are_refused_before_any_file_access(tmp_path: Path, name: str) -> None:
    missing = tmp_path / "does-not-exist"  # any disk access would raise another error
    with pytest.raises(pages.ExperimentRefusedError):
        pages.read_file(missing, FIRST, name)


def test_a_folder_link_pointing_out_of_the_project_is_not_served(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    elsewhere = make_project(tmp_path, "elsewhere") / "experiments" / FIRST
    linked = root / "experiments" / "5-linked-2026-05-01"
    linked.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(pages.ExperimentNotFoundError):  # linked folders are not listed
        pages.read_file((root / "experiments").resolve(), "5-linked-2026-05-01", "report.md")


def test_the_opener_refuses_a_link_at_open_time(tmp_path: Path) -> None:
    (tmp_path / "real.md").write_text("text", encoding="utf-8")
    (tmp_path / "swapped.md").symlink_to(tmp_path / "real.md")
    with pytest.raises(pages.ExperimentRefusedError):
        pages.read_regular_file(tmp_path, "swapped.md")


def test_the_opener_refuses_a_file_that_is_not_regular(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe.md")
    with pytest.raises(pages.ExperimentRefusedError):
        pages.read_regular_file(tmp_path, "pipe.md")


def test_the_opener_reads_at_most_the_limit_plus_one_byte(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_bytes(b"a" * (MIB + 50))
    data, size = pages.read_regular_file(tmp_path, "big.txt")
    assert (len(data), size) == (MIB + 1, MIB + 50)
