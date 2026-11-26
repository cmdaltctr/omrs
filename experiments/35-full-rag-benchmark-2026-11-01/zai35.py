"""The GLM-5.3 endpoint of the ``chat`` claim checker (the Z.ai API, owner 2026-11-26).

The repository is public, so the base URL is in no tracked file. It comes from
``OMRS_EXP35_ZAI_BASE_URL`` (on the pod, from the mode-600 file the Mac watcher writes)
or from the owner's mode-600 file ``~/.config/omrs/secrets/zai-exp35.base_url`` (on the
Mac). ``plan.json`` pins its SHA-256 (``pins.glm_judge.base_url_sha256``), so the frozen
endpoint is still enforced. OMRS gets the value through its process environment
(``OPENAI_COMPATIBLE_BASE_URL``), never through the scratch ``omrs.jsonc``, so no
settings file, trace, run record or report holds it. No message prints the value.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

BASE_URL_ENV = "OMRS_EXP35_ZAI_BASE_URL"
#: The OMRS setting ``openai_compatible_base_url`` as an environment variable.
OMRS_ENV = "OPENAI_COMPATIBLE_BASE_URL"
FILE_NAME = "zai-exp35.base_url"


class EndpointError(Exception):
    """The base URL is missing, or its SHA-256 is not the ``plan.json`` pin."""


def url_sha256(url: str) -> str:
    """Return the SHA-256 of the exact URL string."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def base_url_file() -> Path:
    """Return the owner's base URL file on the Mac (outside the repository)."""
    return Path.home() / ".config" / "omrs" / "secrets" / FILE_NAME


def base_url(plan: Mapping[str, Any], environ: Mapping[str, str] | None = None) -> str:
    """Return the GLM-5.3 base URL after the check against the ``plan.json`` hash.

    Raises:
        EndpointError: No value in the environment or the file, no pin in the plan,
            or a value with another SHA-256. The message never holds the value.
    """
    env = os.environ if environ is None else environ
    url = env.get(BASE_URL_ENV, "").strip()
    path = base_url_file()
    if not url and path.is_file():
        url = path.read_text(encoding="utf-8").strip()
    if not url:
        raise EndpointError(
            f"no GLM-5.3 base URL: set {BASE_URL_ENV} or fill ~/.config/omrs/secrets/{FILE_NAME}"
        )
    want = ((plan.get("pins") or {}).get("glm_judge") or {}).get("base_url_sha256")
    if not want:
        raise EndpointError("plan.json has no pins.glm_judge.base_url_sha256")
    if url_sha256(url) != want:
        raise EndpointError(
            f"the {BASE_URL_ENV} value does not match plan.json "
            "pins.glm_judge.base_url_sha256 (the value is not printed)"
        )
    return url
