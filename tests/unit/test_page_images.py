"""The page renderer list (change document-reading-routers, task 3.6, design D5).

An image router renders one page at 150 DPI, PNG, long side at most 1,568 px,
with the first available renderer of ``ORDER``. LiteParse is installed in the
test environment, so its tests render real fixture pages. pypdfium2 is an
optional extra and is not installed here: its tests inject a stub module.
"""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from omrs.integrations.pdf import page_images
from omrs.integrations.pdf.page_images import registry

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
LETTER = FIXTURES / "smoke_text.pdf"  # one US Letter page with vector text
FIVE_PAGES = FIXTURES / "page_routing" / "routing_fixture.pdf"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ADAPTERS = (
    "omrs.integrations.pdf.page_images.liteparse",
    "omrs.integrations.pdf.page_images.pypdfium2",
)


def png_size(data: bytes) -> tuple[int, int]:
    """Return ``(width, height)`` from the IHDR chunk of a PNG."""
    assert data[:8] == PNG_SIGNATURE, "not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


@pytest.fixture(autouse=True)
def _restore_registry():
    state = registry.RENDERERS.snapshot()
    yield
    registry.RENDERERS.restore(state)


class FakeRenderer:
    """A renderer that sizes a 612 x 792 pt page from the DPI; it records each DPI."""

    def __init__(self, points: tuple[float, float] = (612, 792), *, bump: int = 0) -> None:
        self.points = points
        self.bump = bump  # pixels added to the second render, as a renderer that rounds up
        self.calls: list[float] = []

    def render(self, file: Path, page: int, dpi: float) -> tuple[bytes, tuple[int, int]]:
        self.calls.append(dpi)
        width = round(self.points[0] * dpi / 72)
        height = round(self.points[1] * dpi / 72)
        if len(self.calls) == 2:
            height += self.bump
        return f"png-{len(self.calls)}".encode(), (width, height)


def use_fakes(monkeypatch: pytest.MonkeyPatch, fakes: dict[str, Any]) -> None:
    """Make only the names in *fakes* installed, and serve each fake renderer."""
    monkeypatch.setattr(registry.RENDERERS, "installed", lambda name: name in fakes)
    registry.RENDERERS.cache.update(fakes)


# ── Order and registry ───────────────────────────────────────────────────


def test_order_is_liteparse_then_pypdfium2_and_each_is_registered() -> None:
    assert registry.ORDER == ("liteparse", "pypdfium2")
    assert registry.RENDERERS.names() == ["liteparse", "pypdfium2"]
    assert registry.RENDERERS.describe("liteparse")["probe_module"] == "liteparse"
    assert registry.RENDERERS.describe("pypdfium2")["probe_module"] == "pypdfium2"


def test_first_available_renderer_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = FakeRenderer(), FakeRenderer()
    use_fakes(monkeypatch, {"liteparse": first, "pypdfium2": second})
    page_images.render_page(LETTER, 1)
    assert first.calls and not second.calls


def test_second_renderer_is_used_when_the_first_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    second = FakeRenderer()
    use_fakes(monkeypatch, {"pypdfium2": second})
    assert page_images.available() is True
    page_images.render_page(LETTER, 1)
    assert second.calls


def test_no_renderer_means_not_available_and_render_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_fakes(monkeypatch, {})
    assert page_images.available() is False
    with pytest.raises(page_images.NoRendererError):
        page_images.render_page(LETTER, 1)


def test_available_imports_no_renderer_module(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*ADAPTERS, "liteparse", "pypdfium2"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    assert page_images.available() is True  # LiteParse is installed here
    for name in (*ADAPTERS, "liteparse", "pypdfium2"):
        assert name not in sys.modules, f"available() imported {name}"


# ── Size cap ─────────────────────────────────────────────────────────────


def test_small_page_renders_once_at_150_dpi(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRenderer(points=(500, 600))  # 1042 x 1250 px at 150 DPI
    use_fakes(monkeypatch, {"liteparse": fake})
    assert page_images.render_page(LETTER, 1) == b"png-1"
    assert fake.calls == [150]


def test_large_page_renders_again_with_long_side_1568(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRenderer()  # US Letter: 1275 x 1650 px at 150 DPI
    use_fakes(monkeypatch, {"liteparse": fake})
    assert page_images.render_page(LETTER, 1) == b"png-2"
    assert fake.calls[0] == 150
    assert fake.calls[1] == pytest.approx(150 * 1568 / 1650)


def test_renderer_that_rounds_up_past_the_cap_renders_a_third_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRenderer(bump=1)  # the second render comes back 1,569 px long
    use_fakes(monkeypatch, {"liteparse": fake})
    assert page_images.render_page(LETTER, 1) == b"png-3"
    assert len(fake.calls) == 3
    assert fake.calls[2] < fake.calls[1]


# ── LiteParse (installed: real renders) ──────────────────────────────────


def test_liteparse_renders_a_real_letter_page_as_png_with_long_side_1568() -> None:
    data = page_images.render_page(LETTER, 1)
    assert png_size(data) == (1212, 1568)


def test_liteparse_page_numbers_are_one_based() -> None:
    data = page_images.render_page(FIVE_PAGES, 5)  # the last page; 0-based would be out of range
    assert max(png_size(data)) <= 1568
    with pytest.raises(Exception):  # noqa: B017 - LiteParse raises its own ParseError
        page_images.render_page(FIVE_PAGES, 6)


def test_liteparse_adapter_passes_dpi_and_one_based_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class StubLiteParse:
        def __init__(self, **kwargs: Any) -> None:
            seen["init"] = kwargs

        def screenshot(self, file: Any, *, page_numbers: list[int]) -> list[Any]:
            seen["file"], seen["pages"] = file, page_numbers
            return [SimpleNamespace(page_num=3, width=10, height=20, image_bytes=b"img")]

    stub = ModuleType("liteparse")
    stub.LiteParse = StubLiteParse  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "liteparse", stub)
    from omrs.integrations.pdf.page_images.liteparse import RENDERER

    assert RENDERER.render(LETTER, 3, 150) == (b"img", (10, 20))
    assert seen["init"] == {"quiet": True, "dpi": 150}
    assert seen["pages"] == [3]


# ── pypdfium2 (not installed: stub module) ───────────────────────────────


def _stub_pypdfium2(record: dict[str, Any]) -> ModuleType:
    """Return a stub ``pypdfium2`` whose pages render a blank image sized from the scale."""

    class StubPage:
        def __init__(self, index: int) -> None:
            self.index = index

        def render(self, *, scale: float) -> Any:
            record["index"], record["scale"] = self.index, scale
            size = (round(612 * scale), round(792 * scale))
            return SimpleNamespace(to_pil=lambda: Image.new("RGB", size, "white"))

    class StubDocument:
        def __init__(self, path: str) -> None:
            record["path"] = path

        def __getitem__(self, index: int) -> StubPage:
            return StubPage(index)

        def close(self) -> None:
            record["closed"] = True

    stub = ModuleType("pypdfium2")
    stub.PdfDocument = StubDocument  # type: ignore[attr-defined]
    return stub


def test_pypdfium2_adapter_renders_png_from_the_zero_based_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: dict[str, Any] = {}
    monkeypatch.setitem(sys.modules, "pypdfium2", _stub_pypdfium2(record))
    from omrs.integrations.pdf.page_images.pypdfium2 import RENDERER

    data, size = RENDERER.render(LETTER, 2, 150)
    assert size == (1275, 1650)
    assert png_size(data) == size
    assert Image.open(io.BytesIO(data)).format == "PNG"
    assert record["index"] == 1  # page 2, numbered from 1, is index 1
    assert record["scale"] == pytest.approx(150 / 72)
    assert record["closed"] is True


def test_render_page_uses_pypdfium2_when_liteparse_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: dict[str, Any] = {}
    monkeypatch.setitem(sys.modules, "pypdfium2", _stub_pypdfium2(record))
    monkeypatch.setattr(registry.RENDERERS, "installed", lambda name: name == "pypdfium2")
    data = page_images.render_page(LETTER, 1)
    assert png_size(data) == (1212, 1568)
    assert record["index"] == 0
