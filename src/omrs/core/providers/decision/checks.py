"""Decision model checks: quantisation and the vision projector (design D6).

- Quantisation (AGENTS.md gotcha 16): a decision model on this machine runs at
  8-bit or higher. A managed entry reads ``general.file_type`` from the GGUF
  header of its model file, without loading the model. An external entry
  reads the quantisation marker in the model name its server reports. When
  neither tells, the result is "Quantisation not checked".
- Projector: one bundled page image, sent with its right text and with wrong
  text. The check passes when P(yes) for the right text exceeds P(yes) for
  the wrong text by :data:`SMOKE_MARGIN`.

Nothing here sends a request: the caller passes the function that asks.
"""

from __future__ import annotations

import re
import struct
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import BinaryIO

ACCEPTED = "accepted"
REFUSED = "refused"
NOT_CHECKED = "not-checked"
NOT_CHECKED_TEXT = "Quantisation not checked"
QUANTISATION_REFUSED = "quantisation-refused"
PROJECTOR_NOT_LOADED = "projector-not-loaded"
#: The rule a refused type breaks (AGENTS.md gotcha 16, Experiment 38).
EIGHT_BIT_RULE = (
    "Decision models run at 8-bit or higher (Q8_0, F16, BF16 or F32): "
    "a 4-bit build gave different answers in Experiment 38."
)
#: The llama.cpp build of the Experiment 43 image requests (design, Open Question 2).
BUILD_FLOOR = 11941

#: ``general.file_type`` values (llama.cpp ``llama_ftype``) by number.
FILE_TYPE_NAMES: dict[int, str] = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 7: "Q8_0", 8: "Q5_0", 9: "Q5_1",
    10: "Q2_K", 11: "Q3_K_S", 12: "Q3_K_M", 13: "Q3_K_L", 14: "Q4_K_S", 15: "Q4_K_M",
    16: "Q5_K_S", 17: "Q5_K_M", 18: "Q6_K", 19: "IQ2_XXS", 20: "IQ2_XS", 21: "Q2_K_S",
    22: "IQ3_XS", 23: "IQ3_XXS", 24: "IQ1_S", 25: "IQ4_NL", 26: "IQ3_S", 27: "IQ3_M",
    28: "IQ2_S", 29: "IQ2_M", 30: "IQ4_XS", 31: "IQ1_M", 32: "BF16", 36: "TQ1_0",
    37: "TQ2_0", 38: "MXFP4_MOE",
}  # fmt: skip
ACCEPTED_TYPES = frozenset({"Q8_0", "F16", "BF16", "F32"})

# ── Smoke test ──────────────────────────────────────────────────────────
#: The margin and its version. Experiment 43 recorded a margin of 0.2 (plan
#: rule R4 and output/runtime_check_*.json): Clef-Flash Q8_0 gave 0.903 against
#: 0.069, hosted Jev 0.39 against 0.01. Design D6 named 0.5 only until these
#: results were read; 0.5 would fail the recorded Jev pass.
SMOKE_MARGIN = 0.2
SMOKE_MARGIN_VERSION = "exp43-r4-2026-11-02"
#: The Experiment 43 question.
SMOKE_QUESTION = "Does the text match the text written or printed on the page image?"
SMOKE_IMAGE = "smoke_page.png"
#: The text printed on the bundled image. It holds no personal data.
SMOKE_RIGHT_TEXT = (
    "Harbour weather notes\n"
    "Monday: light rain in the morning, dry later.\n"
    "Tuesday: sunny spells and a gentle breeze.\n"
    "Wednesday: cloudy with showers near the coast.\n"
    "Thursday: strong wind, boats stay in the harbour."
)
SMOKE_WRONG_TEXT = (
    "Garden supply order 4417\n"
    "Three bags of compost and two spades.\n"
    "One wooden ladder, five metres long.\n"
    "Delivery to the side gate after noon.\n"
    "Total due on arrival: fifty-eight pounds."
)

# ── GGUF header reader ──────────────────────────────────────────────────
_MAGIC = b"GGUF"
_FILE_TYPE_KEY = b"general.file_type"
_STRING, _ARRAY = 8, 9
#: Byte sizes of the fixed-size GGUF value types.
_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
_INT_FORMATS = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 10: "<Q", 11: "<q"}
#: The reader gives up past this offset: a header is a few megabytes at most.
_HEADER_LIMIT = 64 * 1024 * 1024
_MAX_PAIRS = 100_000


class _BadHeader(Exception):
    """The header is not a GGUF header the reader understands."""


def _read(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise _BadHeader
    return data


def _uint(stream: BinaryIO, fmt: str) -> int:
    return int(struct.unpack(fmt, _read(stream, struct.calcsize(fmt)))[0])


def _skip(stream: BinaryIO, size: int) -> None:
    """Move past *size* bytes without reading them."""
    if stream.seek(size, 1) > _HEADER_LIMIT:
        raise _BadHeader


def _skip_value(stream: BinaryIO, kind: int) -> None:
    if kind in _SIZES:
        _skip(stream, _SIZES[kind])
    elif kind == _STRING:
        _skip(stream, _uint(stream, "<Q"))
    elif kind == _ARRAY:
        item, count = _uint(stream, "<I"), _uint(stream, "<Q")
        if item in _SIZES:
            _skip(stream, _SIZES[item] * count)
        else:
            for _ in range(count):
                _skip_value(stream, item)
    else:
        raise _BadHeader


def gguf_file_type(stream: BinaryIO) -> int | None:
    """Return ``general.file_type`` from the GGUF header in *stream*, or ``None``.

    The reader reads key names and the one value it needs, and seeks past
    every other value, so it reads the header bytes only. It stops at the key.
    """
    try:
        if _read(stream, 4) != _MAGIC or _uint(stream, "<I") < 2:
            return None
        _uint(stream, "<Q")  # tensor count
        pairs = _uint(stream, "<Q")
        for _ in range(min(pairs, _MAX_PAIRS)):
            length = _uint(stream, "<Q")
            if length > 1024:
                return None
            key, kind = _read(stream, length), _uint(stream, "<I")
            if key == _FILE_TYPE_KEY:
                return _uint(stream, _INT_FORMATS[kind]) if kind in _INT_FORMATS else None
            _skip_value(stream, kind)
    except (_BadHeader, OSError, struct.error):
        return None
    return None


@dataclass(frozen=True)
class QuantisationResult:
    """The result of a quantisation check.

    Attributes:
        status: ``accepted``, ``refused`` or ``not-checked``.
        type_name: The quantisation type, when known.
        message: What the entry and the router test show.
    """

    status: str
    type_name: str | None
    message: str


_NOT_CHECKED = QuantisationResult(NOT_CHECKED, None, NOT_CHECKED_TEXT)


def _verdict(type_name: str) -> QuantisationResult:
    if type_name in ACCEPTED_TYPES:
        return QuantisationResult(ACCEPTED, type_name, f"Quantisation {type_name}.")
    return QuantisationResult(REFUSED, type_name, f"The model is {type_name}. {EIGHT_BIT_RULE}")


def quantisation_from_file(path: str | Path) -> QuantisationResult:
    """Check the quantisation type in the GGUF header of the model file at *path*."""
    try:
        with Path(path).expanduser().open("rb") as stream:
            number = gguf_file_type(stream)
    except OSError:
        return _NOT_CHECKED
    if number is None:
        return _NOT_CHECKED
    return _verdict(FILE_TYPE_NAMES.get(number, f"file type {number}"))


_MARKER = re.compile(
    r"(?<![A-Za-z0-9])(I?Q\d(?:_[A-Za-z0-9]+)*|T?Q\d_\d|BF16|F16|F32|MXFP4[A-Za-z0-9_]*)"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def quantisation_from_name(name: str) -> QuantisationResult:
    """Check the quantisation marker in a reported model name (the last marker wins)."""
    markers = _MARKER.findall(name or "")
    return _verdict(markers[-1].upper()) if markers else _NOT_CHECKED


def smoke_image() -> bytes:
    """Return the bundled smoke-test page image (PNG)."""
    return resources.files(__package__).joinpath(SMOKE_IMAGE).read_bytes()


def run_smoke_test(ask: Callable[[str, str, bytes], float | None]) -> str | None:
    """Run the projector smoke test.

    Args:
        ask: Sends ``(question, text, image)`` and returns P(yes), or ``None``
            when the request failed.

    Returns:
        ``None`` when the test passes, else ``projector-not-loaded``.
    """
    image = smoke_image()
    right = ask(SMOKE_QUESTION, SMOKE_RIGHT_TEXT, image)
    wrong = ask(SMOKE_QUESTION, SMOKE_WRONG_TEXT, image)
    if right is None or wrong is None:
        return PROJECTOR_NOT_LOADED
    # Rounding keeps a gap of exactly the margin from failing on float error.
    return None if round(right - wrong, 9) >= SMOKE_MARGIN else PROJECTOR_NOT_LOADED
