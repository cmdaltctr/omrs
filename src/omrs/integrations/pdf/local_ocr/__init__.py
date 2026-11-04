"""Local OCR backends of the page unit (change local-ocr-backends, design D7 and D8).

The package marker imports no backend module. ``registry`` holds one lazy
``register()`` line per built-in backend, ``base`` the contract and ``chain``
the ordered list the local tier reads with.
"""

from __future__ import annotations
