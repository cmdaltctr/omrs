"""omrs-ocr-dots-mocr-llamacpp: dots.mocr as a client of a llama.cpp server.

This package runs inside the engine-owned environment declared by
``ocr-workers/engines/dots-mocr-llamacpp/pyproject.toml``. That environment
holds no PyTorch. The engine starts no server: the pyproject declares the
pinned ``llama-server`` and OMRS runs it (change dots-mocr-llamacpp-backend,
design D2). The worker reads the address in ``OMRS_OCR_RUNTIME_URL``.
"""

from __future__ import annotations
