"""Experiment folder naming and number order (experiment-format-v1, task 3.1, D5)."""

from __future__ import annotations

from datetime import date

import pytest

from omrs.core.experiment_records.naming import (
    FolderName,
    folder_name,
    folder_sort_key,
    is_valid_number,
    is_valid_slug,
    number_key,
    parse_folder_name,
    whole_number,
)


def test_numbered_folder_name_parses() -> None:
    parsed = parse_folder_name("22-raw-query-qwen4b-baseline-2026-09-07")
    assert parsed == FolderName(
        number="22", slug="raw-query-qwen4b-baseline", date=date(2026, 9, 7)
    )


@pytest.mark.parametrize(
    ("name", "number", "slug"),
    [
        ("5b-persistent-mps-reranker-worker-2026-08-20", "5b", "persistent-mps-reranker-worker"),
        (
            "10.1-doc-similarity-threshold-calibration-2026-06-29",
            "10.1",
            "doc-similarity-threshold-calibration",
        ),
        ("2-embedding-model-comparison-2026-05-19", "2", "embedding-model-comparison"),
        ("9a-rerun-post-adr021-reranker-2026-06-29", "9a", "rerun-post-adr021-reranker"),
    ],
)
def test_number_and_slug_are_split(name: str, number: str, slug: str) -> None:
    parsed = parse_folder_name(name)
    assert parsed is not None
    assert (parsed.number, parsed.slug) == (number, slug)


def test_unnumbered_name_parses_with_empty_number() -> None:
    parsed = parse_folder_name("leiden-vs-louvain-2026-08-14")
    assert parsed == FolderName(number="", slug="leiden-vs-louvain", date=date(2026, 8, 14))


@pytest.mark.parametrize(
    "name",
    [
        "_lib",
        "ARCHIVED",
        "example",
        "22-raw-query-2026-13-01",  # no 13th month
        "22-raw-query-2026-02-30",  # no 30 February
        "22-Raw-Query-2026-09-07",  # upper case
        "22-raw--query-2026-09-07",  # double hyphen
        "22-2026-09-07",  # no slug
        "22-raw-query",  # no date
        "22-raw_query-2026-09-07",  # underscore
        "",
    ],
)
def test_names_that_do_not_match(name: str) -> None:
    assert parse_folder_name(name) is None


@pytest.mark.parametrize("slug", ["ocr", "ocr-text-quality", "qwen3-4b", "a1-b2"])
def test_valid_slugs(slug: str) -> None:
    assert is_valid_slug(slug)


@pytest.mark.parametrize(
    "slug", ["", "OCR", "ocr--text", "-ocr", "ocr-", "ocr_text", "ocr text", "ócr"]
)
def test_invalid_slugs(slug: str) -> None:
    assert not is_valid_slug(slug)


@pytest.mark.parametrize("number", ["1", "22", "5b", "10.1", ""])
def test_valid_numbers(number: str) -> None:
    assert is_valid_number(number)


@pytest.mark.parametrize("number", ["5B", "5bb", "10.", "a", "١٢", "10.1b"])
def test_invalid_numbers(number: str) -> None:
    assert not is_valid_number(number)


@pytest.mark.parametrize(("number", "whole"), [("5", 5), ("5b", 5), ("10.1", 10), ("", None)])
def test_whole_number(number: str, whole: int | None) -> None:
    assert whole_number(number) == whole


def test_folder_name_is_built_from_parts() -> None:
    assert (
        folder_name("43", "ocr-text-quality", date(2026, 10, 26))
        == "43-ocr-text-quality-2026-10-26"
    )


def test_folder_name_refuses_a_bad_slug() -> None:
    with pytest.raises(ValueError, match="slug"):
        folder_name("43", "OCR text", date(2026, 10, 26))


def test_natural_number_order() -> None:
    shuffled = ["10b", "6", "10.1", "5b", "10", "5"]
    assert sorted(shuffled, key=number_key) == ["5", "5b", "6", "10", "10.1", "10b"]


def test_folder_order_puts_unnumbered_last_by_name() -> None:
    entries = [
        ("zeta-2026-01-01", ""),
        ("10-b-2026-01-01", "10"),
        ("alpha-2026-01-01", ""),
        ("9a-y-2026-01-01", "9a"),
        ("9a-x-2026-01-01", "9a"),
        ("2-a-2026-01-01", "2"),
    ]
    ordered = sorted(entries, key=lambda item: folder_sort_key(item[1], item[0]))
    assert [name for name, _ in ordered] == [
        "2-a-2026-01-01",
        "9a-x-2026-01-01",
        "9a-y-2026-01-01",
        "10-b-2026-01-01",
        "alpha-2026-01-01",
        "zeta-2026-01-01",
    ]
