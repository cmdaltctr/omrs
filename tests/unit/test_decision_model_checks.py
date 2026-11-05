"""Decision model checks: GGUF quantisation, model-name marker, projector smoke test.

Tasks 2.2 and 2.3 of document-reading-routers (design D6, gotcha 16).
"""

from __future__ import annotations

import io
import struct

import pytest
from tests.fixtures.decision.gguf import STRING, UINT32, gguf_header, header_with_type

from omrs.core.providers.decision import checks


def _write(tmp_path, data: bytes, name: str = "model.gguf"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("name", ["Q8_0", "F16", "BF16", "F32"])
def test_eight_bit_or_higher_is_accepted(tmp_path, name: str) -> None:
    result = checks.quantisation_from_file(_write(tmp_path, header_with_type(name)))
    assert result.status == checks.ACCEPTED
    assert result.type_name == name


@pytest.mark.parametrize("name", ["Q4_K_M", "Q4_0", "Q6_K"])
def test_lower_types_are_refused_with_the_rule(tmp_path, name: str) -> None:
    result = checks.quantisation_from_file(_write(tmp_path, header_with_type(name)))
    assert result.status == checks.REFUSED
    assert result.type_name == name
    assert name in result.message
    assert checks.EIGHT_BIT_RULE in result.message
    assert "8-bit or higher" in checks.EIGHT_BIT_RULE


def test_reader_skips_a_large_array_before_the_type(tmp_path) -> None:
    path = _write(tmp_path, header_with_type("Q8_0", tokens=5000))
    assert checks.quantisation_from_file(path).type_name == "Q8_0"


def test_reader_reads_only_the_header_bytes() -> None:
    header = header_with_type("Q8_0")
    stream = _Counting(header + b"\0" * 1_000_000)
    assert checks.gguf_file_type(stream) == 7
    assert stream.read_bytes <= len(header)


def test_not_a_gguf_file_is_not_checked(tmp_path) -> None:
    path = _write(tmp_path, gguf_header([], magic=b"NOPE"))
    result = checks.quantisation_from_file(path)
    assert result.status == checks.NOT_CHECKED
    assert result.message == checks.NOT_CHECKED_TEXT == "Quantisation not checked"


def test_header_without_the_type_is_not_checked(tmp_path) -> None:
    path = _write(tmp_path, gguf_header([("general.name", STRING, "clef")]))
    assert checks.quantisation_from_file(path).status == checks.NOT_CHECKED


def test_truncated_header_is_not_checked(tmp_path) -> None:
    path = _write(tmp_path, header_with_type("Q8_0")[:30])
    assert checks.quantisation_from_file(path).status == checks.NOT_CHECKED


def test_missing_file_is_not_checked(tmp_path) -> None:
    assert checks.quantisation_from_file(tmp_path / "absent.gguf").status == checks.NOT_CHECKED


def test_unknown_type_number_is_refused_by_number(tmp_path) -> None:
    path = _write(tmp_path, gguf_header([("general.file_type", UINT32, 99)]))
    result = checks.quantisation_from_file(path)
    assert result.status == checks.REFUSED
    assert "99" in result.message


@pytest.mark.parametrize(
    ("name", "status"),
    [
        ("models/Clef-Flash-Q8_0.gguf", checks.ACCEPTED),
        ("clef-flash:q8_0", checks.ACCEPTED),
        ("Clef-Flash-BF16.gguf", checks.ACCEPTED),
        ("Clef-Flash-F16", checks.ACCEPTED),
        ("Clef-Flash-Q4_K_M.gguf", checks.REFUSED),
        ("clef-flash:q4_k_m", checks.REFUSED),
        ("Clef-Flash-IQ3_XS.gguf", checks.REFUSED),
        ("clef-flash", checks.NOT_CHECKED),
        ("", checks.NOT_CHECKED),
    ],
)
def test_model_name_marker(name: str, status: str) -> None:
    result = checks.quantisation_from_name(name)
    assert result.status == status
    if status == checks.REFUSED:
        assert checks.EIGHT_BIT_RULE in result.message


def test_smoke_image_is_small_png() -> None:
    image = checks.smoke_image()
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(image) < 50 * 1024
    width, height = struct.unpack(">II", image[16:24])
    assert max(width, height) <= 1568


def test_smoke_texts_differ() -> None:
    assert checks.SMOKE_RIGHT_TEXT.strip()
    assert checks.SMOKE_WRONG_TEXT.strip()
    assert checks.SMOKE_RIGHT_TEXT != checks.SMOKE_WRONG_TEXT


def test_margin_is_versioned_and_from_experiment_43() -> None:
    assert checks.SMOKE_MARGIN == 0.2
    assert checks.SMOKE_MARGIN_VERSION


def _fake_ask(right: float | None, wrong: float | None):
    seen: list[tuple[str, bytes]] = []

    def ask(question: str, text: str, image: bytes) -> float | None:
        seen.append((text, image))
        assert question == checks.SMOKE_QUESTION
        return right if text == checks.SMOKE_RIGHT_TEXT else wrong

    return ask, seen


def test_smoke_passes_when_right_beats_wrong_by_the_margin() -> None:
    ask, seen = _fake_ask(0.9, 0.07)
    assert checks.run_smoke_test(ask) is None
    assert [text for text, _ in seen] == [checks.SMOKE_RIGHT_TEXT, checks.SMOKE_WRONG_TEXT]
    assert all(image == checks.smoke_image() for _, image in seen)


@pytest.mark.parametrize(
    ("right", "wrong"),
    [(0.5, 0.5), (0.39, 0.2), (0.1, 0.9), (None, 0.1), (0.9, None)],
)
def test_smoke_fails_without_the_margin(right, wrong) -> None:
    ask, _ = _fake_ask(right, wrong)
    assert checks.run_smoke_test(ask) == checks.PROJECTOR_NOT_LOADED


def test_smoke_passes_at_exactly_the_margin() -> None:
    ask, _ = _fake_ask(0.7, 0.5)
    assert checks.run_smoke_test(ask) is None


class _Counting(io.BytesIO):
    """A stream that counts the bytes read from it."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.read_bytes = 0

    def read(self, size: int | None = -1) -> bytes:  # type: ignore[override]
        chunk = super().read(size)
        self.read_bytes += len(chunk)
        return chunk
