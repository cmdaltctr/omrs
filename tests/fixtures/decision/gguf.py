"""Build small GGUF headers for the decision model quantisation tests.

The layout follows the GGUF v3 file format: magic ``GGUF``, a uint32
version, uint64 tensor and key-value counts, then the key-value pairs. Each
key is a uint64 length plus UTF-8 bytes; each value has a uint32 type.
"""

from __future__ import annotations

import struct
from typing import Any

UINT32 = 4
STRING = 8
ARRAY = 9

#: ``general.file_type`` values (llama.cpp ``llama_ftype``).
FILE_TYPES = {"F32": 0, "F16": 1, "Q4_0": 2, "Q8_0": 7, "Q4_K_M": 15, "Q6_K": 18, "BF16": 32}


def _string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _value(kind: int, value: Any) -> bytes:
    if kind == UINT32:
        return struct.pack("<I", value)
    if kind == STRING:
        return _string(value)
    # An array of strings.
    return struct.pack("<IQ", STRING, len(value)) + b"".join(_string(v) for v in value)


def gguf_header(pairs: list[tuple[str, int, Any]], *, magic: bytes = b"GGUF") -> bytes:
    """Return a GGUF header that holds *pairs* as ``(key, type, value)``."""
    body = b"".join(
        _string(key) + struct.pack("<I", kind) + _value(kind, v) for key, kind, v in pairs
    )
    return magic + struct.pack("<IQQ", 3, 0, len(pairs)) + body


def header_with_type(name: str, *, tokens: int = 3) -> bytes:
    """Return a header whose ``general.file_type`` is *name*, after a string array."""
    return gguf_header(
        [
            ("general.architecture", STRING, "clef"),
            ("tokenizer.ggml.tokens", ARRAY, [f"tok{i}" for i in range(tokens)]),
            ("general.file_type", UINT32, FILE_TYPES[name]),
        ]
    )
