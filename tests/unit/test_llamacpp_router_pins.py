"""The pinned llama.cpp build list (change one-llamacpp-router, task 6.1, design D12).

The list is data. These tests pin its tag to the dots-mocr engine, check the
shape of every hash and check the lookup. The lookup does no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
from tests.fixtures.ocr_worker.dots_llamacpp import engine_modules

from omrs.integrations.llamacpp_runtime import pins

SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: Values copied from the release (``gh api .../releases/tags/b11941``).
EXPECTED = {
    "metal": {
        "llama-b11941-bin-macos-arm64.tar.gz": (
            "fb5c491b35c75731019caa85d704fb839532c15dbb9bd3f6b3f75a667e7ac49a"
        ),
    },
    "cpu": {
        "llama-b11941-bin-ubuntu-x64.tar.gz": (
            "e8a1ee13aa19c6c78f5651457758160da27410301b179d6ef3505c81c8ea31f1"
        ),
    },
    "cuda": {
        "llama-b11941-bin-ubuntu-cuda-12.8-x64.tar.gz": (
            "9945330f20a35b9a30fbac43f99f5b7f88ae7dd32dc2e5089af5c75310d3acf1"
        ),
        "cudart-llama-b11941-bin-ubuntu-cuda-12.8-x64.tar.gz": (
            "3011ef1b30e73a3059c5a4d3d44446562155aff49035efc49e7e2f1c370524f8"
        ),
    },
}

PLATFORMS = {
    "metal": ("darwin", "arm64"),
    "cpu": ("linux", "x86_64"),
    "cuda": ("linux", "x86_64"),
}


@pytest.fixture
def dots_pins(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Import the dots-mocr engine's ``pins`` module from source."""
    with engine_modules(monkeypatch) as load:
        yield load("pins")


def _build(flavour: str) -> pins.PinnedBuild:
    system, machine = PLATFORMS[flavour]
    return pins.pinned_build(flavour, system, machine)


def test_tag_equals_the_dots_mocr_engine_tag(dots_pins: Any) -> None:
    """The router and the OCR engine pin one llama.cpp build."""
    assert pins.LLAMA_TAG == dots_pins.LLAMA_TAG == "b11941"
    assert pins.LLAMA_BUILD == dots_pins.LLAMA_BUILD == 11941


def test_archive_hashes_equal_the_dots_mocr_engine_where_both_pin_them(dots_pins: Any) -> None:
    """The two copies of a shared archive carry the same hash."""
    assert _build("metal").archives[0].sha256 == dots_pins.MACOS_ARM64.sha256
    assert _build("cpu").archives[0].sha256 == dots_pins.UBUNTU_X64.sha256


@pytest.mark.parametrize("flavour", sorted(EXPECTED))
def test_every_archive_matches_the_release_value(flavour: str) -> None:
    """Names and hashes are the values read from the release."""
    got = {a.name: a.sha256 for a in _build(flavour).archives}
    assert got == EXPECTED[flavour]


@pytest.mark.parametrize("flavour", sorted(EXPECTED))
def test_every_sha256_is_64_lowercase_hex_characters(flavour: str) -> None:
    for archive in _build(flavour).archives:
        assert SHA256.match(archive.sha256), archive.name


def test_cuda_flavour_carries_the_cudart_archive_after_the_server_archive() -> None:
    names = [a.name for a in _build("cuda").archives]
    assert names == [
        "llama-b11941-bin-ubuntu-cuda-12.8-x64.tar.gz",
        "cudart-llama-b11941-bin-ubuntu-cuda-12.8-x64.tar.gz",
    ]


@pytest.mark.parametrize("flavour", ["metal", "cpu"])
def test_flavours_without_cuda_carry_one_archive(flavour: str) -> None:
    assert len(_build(flavour).archives) == 1


def test_archive_url_points_at_the_pinned_release() -> None:
    archive = _build("cpu").archives[0]
    assert archive.url == (
        "https://github.com/ggml-org/llama.cpp/releases/download/b11941/"
        "llama-b11941-bin-ubuntu-x64.tar.gz"
    )


def test_each_flavour_has_its_own_folder_name() -> None:
    """Flavours unpack apart (design D12): the folder name holds the flavour."""
    assert [_build(f).folder_name for f in ("cpu", "cuda", "metal")] == [
        "b11941-cpu",
        "b11941-cuda",
        "b11941-metal",
    ]


@pytest.mark.parametrize(
    ("system", "machine", "flavour"),
    [
        ("darwin", "x86_64", "metal"),
        ("win32", "AMD64", "cpu"),
        ("linux", "aarch64", "cpu"),
        ("darwin", "arm64", "cuda"),
        ("linux", "x86_64", "metal"),
        ("linux", "x86_64", "rocm"),
    ],
)
def test_lookup_refuses_an_unpinned_platform_with_not_supported(
    system: str, machine: str, flavour: str
) -> None:
    with pytest.raises(pins.NotSupported) as caught:
        pins.pinned_build(flavour, system, machine)
    assert caught.value.reason == "not-supported"
    assert system in str(caught.value)


def test_lookup_reads_machine_names_case_insensitively() -> None:
    assert pins.pinned_build("cpu", "linux", "AMD64").flavour == "cpu"
    assert pins.pinned_build("metal", "darwin", "aarch64").flavour == "metal"
