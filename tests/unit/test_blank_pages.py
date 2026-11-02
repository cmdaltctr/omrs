"""The blank-page test module (change skip-blank-pages-before-worker, task 1.1).

Fixtures are small generated images, one per behaviour the design pins:

- an empty grain-noise page (scanned paper with grain) counts blank;
- an empty sheet with a dark lid band and a scanner frame counts blank
  (the frame is border-connected ink and must be removed);
- a page with one dark 12 pt word never counts blank (mutation check);
- a page with an 11-character header near the top counts blank never;
- a page of faint pencil-like strokes keeps its normal OCR route;
- a dense text page keeps its normal OCR route;
- a page carrying only isolated dust specks counts blank (speck guard).

The render path (LiteParse screenshots in batches of 16, safe failure)
is tested against a fake ``liteparse.LiteParse``; no real PDF is read.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from omrs.integrations.pdf.blank_pages import (
    BLANK_PAGE_INK_THRESHOLD,
    BLANK_PAGE_TEST_VERSION,
    find_blank_pages,
    page_ink_score,
    score_is_blank,
)

PAGE = (850, 1100)  # width, height — a letter page near 100 dpi


def _png_bytes(image: Image.Image) -> bytes:
    """Serialise *image* as PNG, the shape LiteParse screenshot returns."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def grain_empty_page() -> Image.Image:
    """White paper with ±7 grain noise and no marks."""
    generator = np.random.default_rng(101)
    array = np.full((PAGE[1], PAGE[0]), 246, dtype=np.int16)
    array += generator.integers(-7, 8, size=array.shape)
    return Image.fromarray(array.clip(0, 255).astype(np.uint8), "L")


def dark_border_empty_page() -> Image.Image:
    """An empty sheet: dark lid band, white paper, scanner frame line.

    The lid band is a large dark area (no ink after closing). The frame
    line is thin, high-contrast ink connected to the image border: only
    the border-connected removal keeps this page blank.
    """
    generator = np.random.default_rng(102)
    array = np.full((PAGE[1], PAGE[0]), 246, dtype=np.int16)  # white paper
    array += generator.integers(-6, 7, size=array.shape)
    array[:190, :] = 38  # the scanner lid, a large dark band at the top
    image = Image.fromarray(array.clip(0, 255).astype(np.uint8), "L")
    ImageDraw.Draw(image).rectangle([0, 0, 849, 1099], outline=60, width=4)
    return image


def one_dark_word_page() -> Image.Image:
    """White grain page whose only content is one dark short word."""
    image = grain_empty_page()
    draw = ImageDraw.Draw(image)
    _glyphs(draw, x=380, y=520, count=5, height=15, thickness=4, fill=25)
    return image


def header_near_top_page() -> Image.Image:
    """White grain page with an 11-character header 60 px below the top."""
    image = grain_empty_page()
    draw = ImageDraw.Draw(image)
    _glyphs(draw, x=270, y=60, count=11, height=16, thickness=4, fill=25)
    return image


def faint_pencil_page() -> Image.Image:
    """White grain page with several light-grey pencil-like strokes."""
    image = grain_empty_page()
    draw = ImageDraw.Draw(image)
    for row in range(7):
        y = 220 + row * 100
        draw.line([(120, y), (300, y - 25), (520, y + 15), (720, y - 10)], fill=185, width=3)
    return image


def dense_text_page() -> Image.Image:
    """White page of dashed text-like lines."""
    generator = np.random.default_rng(103)
    array = np.full((PAGE[1], PAGE[0]), 248, dtype=np.int16)
    array += generator.integers(-5, 6, size=array.shape)
    image = Image.fromarray(array.clip(0, 255).astype(np.uint8), "L")
    draw = ImageDraw.Draw(image)
    for row in range(44):
        y = 120 + row * 20
        for start in range(90, 740, 18):  # dashes with gaps, like words
            draw.rectangle([start, y, start + 11, y + 4], fill=30)
    return image


def dust_speck_page() -> Image.Image:
    """White grain page carrying only isolated single-pixel specks."""
    generator = np.random.default_rng(104)
    array = np.full((PAGE[1], PAGE[0]), 246, dtype=np.int16)
    array += generator.integers(-7, 8, size=array.shape)
    pixels = {(int(x), int(y)) for x, y in generator.integers(60, 790, size=(300, 2))}
    for x, y in pixels:
        array[y, x] = 40
    return Image.fromarray(array.clip(0, 255).astype(np.uint8), "L")


def _glyphs(
    draw: ImageDraw.ImageDraw, *, x: int, y: int, count: int, height: int, thickness: int, fill: int
) -> None:
    """Draw *count* letter-like glyphs left to right from (*x*, *y*)."""
    for index in range(count):
        left = x + index * (thickness * 2 + 3)
        draw.rectangle([left, y, left + thickness, y + height], fill=fill)
        if index % 3 == 0:  # a crossbar every third glyph, like letter arms
            draw.rectangle(
                [left, y + height // 3, left + thickness + 4, y + height // 3 + thickness],
                fill=fill,
            )


# ── The score on generated fixtures ────────────────────────────────────


def test_version_pins_the_identity_constant() -> None:
    """The blank-test version joins the page-unit index identity: pin it."""
    assert BLANK_PAGE_TEST_VERSION == 1


def test_threshold_is_the_measured_constant() -> None:
    """The threshold is the calibrated 1.5e-4 ink fraction (design.md)."""
    assert BLANK_PAGE_INK_THRESHOLD == 1.5e-4


def test_empty_grain_page_is_blank() -> None:
    assert page_ink_score(grain_empty_page()) == 0.0
    assert score_is_blank(page_ink_score(grain_empty_page()))


def test_empty_sheet_with_dark_border_is_blank() -> None:
    """The border fixture stays blank only with border-connected removal."""
    score = page_ink_score(dark_border_empty_page())
    assert score < BLANK_PAGE_INK_THRESHOLD, f"dark-border fixture scored {score}"


def test_one_dark_word_is_never_blank() -> None:
    """Mutation check: a single dark word must score at or above the cut."""
    score = page_ink_score(one_dark_word_page())
    assert score >= BLANK_PAGE_INK_THRESHOLD, f"one-word page scored {score}"
    assert not score_is_blank(score)


def test_header_near_top_is_not_blank() -> None:
    score = page_ink_score(header_near_top_page())
    assert not score_is_blank(score)


def test_faint_pencil_strokes_are_not_blank() -> None:
    assert not score_is_blank(page_ink_score(faint_pencil_page()))


def test_dense_text_is_not_blank() -> None:
    score = page_ink_score(dense_text_page())
    assert not score_is_blank(score)
    assert score > 10 * BLANK_PAGE_INK_THRESHOLD  # far from the cut


def test_isolated_dust_specks_are_blank() -> None:
    """300 isolated specks would pass the threshold; the speck guard drops them."""
    assert page_ink_score(dust_speck_page()) < BLANK_PAGE_INK_THRESHOLD


def test_small_image_is_not_upscaled() -> None:
    """A page already under 1000 px keeps its size (downscale only)."""
    small = Image.new("L", (200, 300), 250)
    assert page_ink_score(small) == 0.0


def test_rgb_image_is_converted() -> None:
    """Renderers may hand back RGB; the score reads it as grey."""
    rgb = Image.new("RGB", (400, 500), (250, 250, 250))
    assert page_ink_score(rgb) == 0.0


# ── The render path against a fake LiteParse ───────────────────────────


class _FakeResult:
    def __init__(self, page_num: int, image: Image.Image) -> None:
        self.page_num = page_num
        self.image_bytes = _png_bytes(image)
        self.width, self.height = image.size
        self.is_solid_fill = False


class _FakeLiteParse:
    """Records screenshot calls and serves images from a page map."""

    last: _FakeLiteParse | None = None

    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[list[int]] = []
        self.images: dict[int, Image.Image] = {}
        self.error: Exception | None = None
        self.serve_only: set[int] | None = None  # pages missing from results
        _FakeLiteParse.last = self

    def screenshot(self, file_path, *, page_numbers=None):
        requested = list(page_numbers or [])
        self.calls.append(requested)
        if self.error is not None:
            raise self.error
        served = (
            requested if self.serve_only is None else [p for p in requested if p in self.serve_only]
        )
        return [_FakeResult(page, self.images[page]) for page in served if page in self.images]


@pytest.fixture()
def fake_liteparse(monkeypatch: pytest.MonkeyPatch) -> _FakeLiteParse:
    import liteparse

    fake = _FakeLiteParse()
    monkeypatch.setattr(liteparse, "LiteParse", lambda *a, **k: fake)
    return fake


def test_find_blank_pages_renders_in_batches_of_16(
    fake_liteparse: _FakeLiteParse, tmp_path: Path
) -> None:
    pages = list(range(1, 41))
    fake_liteparse.images = {page: dense_text_page() for page in pages}
    fake_liteparse.images[2] = grain_empty_page()
    fake_liteparse.images[18] = grain_empty_page()

    blank = find_blank_pages(tmp_path / "scan.pdf", pages)

    assert blank == {2, 18}
    assert fake_liteparse.calls == [
        list(range(1, 17)),
        list(range(17, 33)),
        list(range(33, 41)),
    ]


def test_find_blank_pages_returns_empty_without_pages(
    fake_liteparse: _FakeLiteParse, tmp_path: Path
) -> None:
    assert find_blank_pages(tmp_path / "scan.pdf", []) == frozenset()
    assert fake_liteparse.calls == []


def test_render_error_is_safe_failure(
    fake_liteparse: _FakeLiteParse, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake_liteparse.error = RuntimeError("pdfium exploded")

    with caplog.at_level("WARNING", logger="omrs.integrations.pdf.blank_pages"):
        blank = find_blank_pages(tmp_path / "scan.pdf", [1, 2, 3])

    assert blank == frozenset()
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "scan.pdf" in warnings[0].getMessage()


def test_missing_render_result_is_not_blank(fake_liteparse: _FakeLiteParse, tmp_path: Path) -> None:
    """A page the renderer never returned follows today's route."""
    fake_liteparse.images = {1: grain_empty_page(), 3: grain_empty_page()}
    fake_liteparse.serve_only = {1, 3}

    blank = find_blank_pages(tmp_path / "scan.pdf", [1, 2, 3])

    assert blank == {1, 3}


def test_pages_are_deduplicated_for_rendering(
    fake_liteparse: _FakeLiteParse, tmp_path: Path
) -> None:
    fake_liteparse.images = {4: grain_empty_page(), 5: dense_text_page()}

    blank = find_blank_pages(tmp_path / "scan.pdf", [5, 4, 4, 5])

    assert blank == {4}
    assert fake_liteparse.calls == [[4, 5]]
