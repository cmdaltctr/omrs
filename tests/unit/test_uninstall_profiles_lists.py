"""The uninstall check finds a reader in a Read document step in either form.

Change ordered-reader-and-ocr-lists, task 4.1. A step sets ``pdf_reader`` or
the ``pdf_readers`` list that replaces it.
"""

from __future__ import annotations

from typing import Any

from tests.unit.test_web_integration_uninstall_profiles import FakeCatalogue, profile

from omrs.core.settings import EffectiveSettings
from omrs.transports.api.uninstall_profiles import InUse, in_use


def _step(params: dict[str, Any], *, enabled: bool = True, node: str = "read") -> dict[str, Any]:
    return {"id": node, "operation": "read.document", "params": params, "enabled": enabled}


def _use(*nodes: dict[str, Any]) -> InUse | None:
    catalogue = FakeCatalogue(profile("p-lists", "Lists", *nodes))
    return in_use("pdf-pypdfium2", EffectiveSettings(), {}, catalogue)


def test_a_step_list_that_names_the_reader_blocks_the_extra() -> None:
    found = _use(_step({"pdf_readers": ["pdf_inspector", "pypdfium2"]}))
    assert found == InUse("pdf_readers", {"id": "p-lists", "title": "Lists"})


def test_the_old_option_still_blocks_and_names_its_own_key() -> None:
    found = _use(_step({"pdf_reader": "pypdfium2"}))
    assert found == InUse("pdf_reader", {"id": "p-lists", "title": "Lists"})


def test_a_step_list_without_the_reader_does_not_block() -> None:
    assert _use(_step({"pdf_readers": ["pdf_inspector", "pypdf"]})) is None


def test_a_disabled_step_list_does_not_block() -> None:
    assert _use(_step({"pdf_readers": ["pypdfium2"]}, enabled=False)) is None


def test_the_second_step_is_checked_in_either_form() -> None:
    found = _use(_step({"pdf_readers": ["pypdf"]}), _step({"pdf_reader": "pypdfium2"}, node="r2"))
    assert found is not None and found.setting == "pdf_reader"


def test_names_are_matched_without_case_or_padding() -> None:
    assert _use(_step({"pdf_readers": [" PyPdfium2 "]})) is not None
