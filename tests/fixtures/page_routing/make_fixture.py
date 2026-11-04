"""Build the page-routing fixture PDF (change local-ocr-backends, task 1.4).

Run ``uv run --no-sync python tests/fixtures/page_routing/make_fixture.py`` to
write ``routing_fixture.pdf`` beside this script. The file is hand-written PDF
syntax, so the output has no timestamp, no document ID and no producer string:
two runs give the same bytes.

Five pages, one of each kind the page unit routes:

1. Native text. Latin text in Helvetica. The page scan does not flag it.
2. Scanned. One grey image of thin strokes and no text layer. The scan flags it
   (``needs_ocr``). The blank test finds ink, so the page is not blank.
3. Blank. One white image and no text layer. The scan flags it, and the blank
   test marks it blank.
4. Maths font. A text layer set in a Computer Modern maths font (CMMI10) with
   no Unicode map, the case the maths-font detector exists for.
5. Arabic. A text layer of Arabic letters, mapped to Unicode by a ToUnicode
   CMap, so ``script_routing.is_non_latin`` is True on its text. A clean Arabic
   text layer is NOT flagged by the scan, and the ``detect`` mode only checks
   flagged pages. So the page also carries a short line of three U+FFFD
   replacement characters. pdf-inspector reads that as garbled text and flags
   the page (its Markdown becomes empty), while the text-position call still
   returns the Arabic letters. That is the shape of a real page whose text layer
   is partly unusable. The three characters add three non-letters and no
   Latin letters, so the Arabic share stays 100 per cent.

Pages 4 and 5: the scan flags page 5 and does not flag page 4. A maths font
without a Unicode map still extracts clean text, so the page stays native
unless maths routing sends it to the OCR engine. The golden test asserts all
of this.
"""

from __future__ import annotations

import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "routing_fixture.pdf"

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
IMAGE_WIDTH = 612
IMAGE_HEIGHT = 792

LATIN_LINES = (
    "Routing fixture, page one: native text.",
    "This page has a real text layer, so the page scan does not flag it.",
    "The quick brown fox jumps over the lazy dog. " * 2,
)
MATHS_LINES = (
    "Maths page: x = a + b, y = c - d.",
    "The text is set in a Computer Modern maths font without a Unicode map.",
)

#: Arabic letters, one per code. Codes 0x41 upward map to these in the CMap.
ARABIC_LETTERS = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"
ARABIC_FIRST_CODE = 0x41


def _arabic_run(length: int) -> bytes:
    """Return *length* codes that the CMap maps to Arabic letters."""
    count = len(ARABIC_LETTERS)
    return bytes(ARABIC_FIRST_CODE + (index * 7) % count for index in range(length))


def _arabic_cmap() -> bytes:
    """Return a ToUnicode CMap mapping the codes to ``ARABIC_LETTERS``."""
    lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CMapName /Adobe-Identity-UCS def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<00> <FF>",
        "endcodespacerange",
        f"{len(ARABIC_LETTERS)} beginbfchar",
    ]
    for offset, letter in enumerate(ARABIC_LETTERS):
        lines.append(f"<{ARABIC_FIRST_CODE + offset:02X}> <{ord(letter):04X}>")
    lines += ["endbfchar", "endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
    return ("\n".join(lines) + "\n").encode("ascii")


def _text_stream(font: str, lines: tuple[bytes, ...]) -> bytes:
    """Return a content stream that writes each line at 14 pt, top down."""
    parts = [b"BT", f"/{font} 14 Tf".encode(), b"16 TL", b"72 720 Td"]
    for line in lines:
        escaped = line.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        parts.append(b"(" + escaped + b") Tj T*")
    parts.append(b"ET")
    return b"\n".join(parts)


def _image_rows(strokes: bool) -> bytes:
    """Return a grey image, white, with thin dark horizontal strokes when asked.

    The strokes are 3 px tall and stay 60 px inside the border, so they are
    thin ink that the blank test counts and no border-connected mark.
    """
    rows = []
    for y in range(IMAGE_HEIGHT):
        row = bytearray(b"\xff" * IMAGE_WIDTH)
        if strokes and 100 <= y < 700 and (y // 3) % 5 == 0:
            start = 60
            for x in range(start, IMAGE_WIDTH - 60):
                if (x // 40) % 7 != 6:  # gaps between "words"
                    row[x] = 0x20
        rows.append(bytes(row))
    return b"".join(rows)


def _arabic_page_content() -> bytes:
    """Return the Arabic lines plus one line of three replacement characters."""
    arabic = _text_stream("F0", tuple(_arabic_run(40) for _ in range(3)))
    garble = b"BT /F1 14 Tf 72 400 Td (" + b"\xef\xbf\xbd" * 3 + b") Tj ET"
    return arabic + b"\n" + garble


class _Pdf:
    """A minimal PDF writer: numbered objects, one xref table, no metadata."""

    def __init__(self) -> None:
        self._objects: list[bytes] = []

    def reserve(self) -> int:
        """Return the number of a new, empty object."""
        self._objects.append(b"")
        return len(self._objects)

    def set(self, number: int, body: bytes) -> None:
        """Fill the object *number* with *body*."""
        self._objects[number - 1] = body

    def add(self, body: bytes) -> int:
        """Add an object and return its number."""
        number = self.reserve()
        self.set(number, body)
        return number

    def stream(self, entries: str, data: bytes, *, compress: bool = True) -> int:
        """Add a stream object. Flate level and zlib header are fixed."""
        extra = ""
        if compress:
            data = zlib.compress(data, 9)
            extra = " /Filter /FlateDecode"
        head = f"<< {entries}{extra} /Length {len(data)} >>".encode("ascii")
        return self.add(head + b"\nstream\n" + data + b"\nendstream")

    def render(self, root: int) -> bytes:
        """Return the file bytes with the catalogue *root*."""
        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for number, body in enumerate(self._objects, start=1):
            offsets.append(len(out))
            out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
        xref_at = len(out)
        out += f"xref\n0 {len(self._objects) + 1}\n".encode("ascii")
        out += b"0000000000 65535 f \n"
        for offset in offsets:
            out += f"{offset:010d} 00000 n \n".encode("ascii")
        out += (
            f"trailer\n<< /Size {len(self._objects) + 1} /Root {root} 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n"
        ).encode("ascii")
        return bytes(out)


def build() -> bytes:
    """Return the bytes of the five-page fixture PDF."""
    pdf = _Pdf()
    catalogue = pdf.reserve()
    pages_node = pdf.reserve()

    helvetica = pdf.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    maths_font = pdf.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /ABCDEF+CMMI10 >>")
    cmap = pdf.stream("", _arabic_cmap(), compress=False)
    arabic_font = pdf.add(
        (
            f"<< /Type /Font /Subtype /Type1 /BaseFont /ArabicFixture /ToUnicode {cmap} 0 R >>"
        ).encode("ascii")
    )

    def image(strokes: bool) -> int:
        entries = (
            f"/Type /XObject /Subtype /Image /Width {IMAGE_WIDTH} /Height {IMAGE_HEIGHT} "
            "/ColorSpace /DeviceGray /BitsPerComponent 8"
        )
        return pdf.stream(entries, _image_rows(strokes))

    def page(resources: str, content: bytes) -> int:
        stream = pdf.stream("", content)
        return pdf.add(
            (
                f"<< /Type /Page /Parent {pages_node} 0 R "
                f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << {resources} >> /Contents {stream} 0 R >>"
            ).encode("ascii")
        )

    full_page = f"q {PAGE_WIDTH} 0 0 {PAGE_HEIGHT} 0 0 cm /Im0 Do Q".encode("ascii")
    kids = [
        page(
            f"/Font << /F0 {helvetica} 0 R >>",
            _text_stream("F0", tuple(line.encode("latin-1") for line in LATIN_LINES)),
        ),
        page(f"/XObject << /Im0 {image(True)} 0 R >>", full_page),
        page(f"/XObject << /Im0 {image(False)} 0 R >>", full_page),
        page(
            f"/Font << /F0 {maths_font} 0 R >>",
            _text_stream("F0", tuple(line.encode("latin-1") for line in MATHS_LINES)),
        ),
        page(
            f"/Font << /F0 {arabic_font} 0 R /F1 {helvetica} 0 R >>",
            _arabic_page_content(),
        ),
    ]
    refs = " ".join(f"{kid} 0 R" for kid in kids)
    pdf.set(pages_node, f"<< /Type /Pages /Kids [{refs}] /Count {len(kids)} >>".encode("ascii"))
    pdf.set(catalogue, f"<< /Type /Catalog /Pages {pages_node} 0 R >>".encode("ascii"))
    return pdf.render(catalogue)


def main() -> int:
    """Write the fixture beside this script."""
    OUTPUT.write_bytes(build())
    print(f"wrote {OUTPUT.name} ({OUTPUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
