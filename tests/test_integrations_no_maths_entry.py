"""The Integrations catalogue has no maths rendering entry.

Pins the "No catalogue entry" scenario of ``render-maths-in-web-workspace``:
KaTeX ships in the base web install, so it is neither an extra nor an
installable integration.
"""

from __future__ import annotations

import re
from pathlib import Path

_CATALOGUE = (
    Path(__file__).resolve().parents[1] / "src/omrs/transports/api/integrations_catalogue.py"
)


def test_catalogue_names_no_maths_package() -> None:
    source = _CATALOGUE.read_text(encoding="utf-8").lower()
    assert source
    assert "katex" not in source
    assert "remark-math" not in source
    assert not re.search(r"\bmaths?\b|latex", source)
