"""Saved user profiles in the uninstall in-use check (check-saved-profiles-before-uninstall).

Every test passes a small fake catalogue: the profiles that are not deleted and
the current ingest graph of each. No test reads a real workspace.
"""

from __future__ import annotations

from typing import Any

import pytest

from omrs.core.providers.embeddings import registry as embedding_registry
from omrs.core.settings import EffectiveSettings
from omrs.transports.api.uninstall_profiles import InUse, in_use

READER_OPERATION = "read.document"


def _read(reader: str | None, *, enabled: bool = True, node: str = "read") -> dict[str, Any]:
    params = {} if reader is None else {"pdf_reader": reader}
    return {"id": node, "operation": READER_OPERATION, "params": params, "enabled": enabled}


class FakeCatalogue:
    """The two catalogue reads the walk uses."""

    def __init__(self, *profiles: dict[str, Any]) -> None:
        self.profiles = list(profiles)

    def list_profiles(self) -> list[dict[str, Any]]:
        return [profile for profile in self.profiles if not profile.get("archived_at")]

    def slot_document(self, profile_id: str, slot: str) -> dict[str, Any] | None:
        assert slot == "ingest"
        for profile in self.profiles:
            if profile["profile_id"] == profile_id:
                return {"nodes": profile.get("nodes", [])}
        return None


def profile(pid: str, title: str, *nodes: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {
        "profile_id": pid,
        "title": title,
        "nodes": list(nodes),
        "embed_provider": None,
        **fields,
    }


SCANS = profile("p-scans", "Scans", _read("pypdfium2"))


def test_a_read_document_step_with_pypdfium2_blocks_the_extra() -> None:
    found = in_use("pdf-pypdfium2", EffectiveSettings(), {}, FakeCatalogue(SCANS))
    assert found == InUse("pdf_reader", {"id": "p-scans", "title": "Scans"})


def test_a_step_without_a_reader_or_with_a_base_reader_never_blocks() -> None:
    plain = profile("p1", "Plain", _read(None), _read("pypdf", node="r2"))
    assert in_use("pdf-pypdfium2", EffectiveSettings(), {}, FakeCatalogue(plain)) is None


def test_a_disabled_step_does_not_block() -> None:
    off = profile("p1", "Off", _read("pypdfium2", enabled=False))
    assert in_use("pdf-pypdfium2", EffectiveSettings(), {}, FakeCatalogue(off)) is None


def test_a_deleted_profile_does_not_block() -> None:
    gone = {**SCANS, "archived_at": "2026-10-24T10:00:00Z"}
    assert in_use("pdf-pypdfium2", EffectiveSettings(), {}, FakeCatalogue(gone)) is None


def test_a_second_read_step_is_checked_too() -> None:
    two = profile("p2", "Two", _read("pypdf"), _read("pypdfium2", node="r2"))
    found = in_use("pdf-pypdfium2", EffectiveSettings(), {}, FakeCatalogue(two))
    assert found is not None and found.profile == {"id": "p2", "title": "Two"}


def test_the_first_profile_in_creation_order_is_named() -> None:
    other = profile("p-later", "Later", _read("pypdfium2"))
    found = in_use("pdf-pypdfium2", EffectiveSettings(), {}, FakeCatalogue(SCANS, other))
    assert found is not None and found.profile == {"id": "p-scans", "title": "Scans"}


def test_a_profile_embedding_provider_with_an_extra_blocks_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(embedding_registry._PROVIDER_EXTRAS, "fancy", "fancy-extra")
    embedder = profile("p-emb", "Embedder", embed_provider="fancy", embed_model="m")
    found = in_use("fancy-extra", EffectiveSettings(), {}, FakeCatalogue(embedder))
    assert found == InUse("embed_provider", {"id": "p-emb", "title": "Embedder"})


def test_a_base_embedding_provider_never_blocks() -> None:
    local = profile("p-ollama", "Local", embed_provider="ollama", embed_model="m")
    assert in_use("pdf-pypdfium2", EffectiveSettings(), {}, FakeCatalogue(local)) is None


def test_a_global_setting_is_named_before_a_profile() -> None:
    found = in_use(
        "pdf-pypdfium2", EffectiveSettings(), {"pdf_reader": "pypdfium2"}, FakeCatalogue(SCANS)
    )
    assert found == InUse("pdf_reader", None)


def test_no_catalogue_leaves_the_global_check() -> None:
    assert in_use("pdf-pypdfium2", EffectiveSettings(), {}, None) is None
    found = in_use("pdf-pypdfium2", EffectiveSettings(), {"pdf_reader": "pypdfium2"}, None)
    assert found == InUse("pdf_reader", None)


class BrokenCatalogue:
    def list_profiles(self) -> list[dict[str, Any]]:
        raise RuntimeError("database is locked")

    def slot_document(self, profile_id: str, slot: str) -> None:
        raise AssertionError("not reached")


def test_a_catalogue_that_fails_is_logged_and_skipped(caplog: pytest.LogCaptureFixture) -> None:
    assert in_use("pdf-pypdfium2", EffectiveSettings(), {}, BrokenCatalogue()) is None
    assert "Could not read the saved profiles" in caplog.text
    assert "database is locked" not in caplog.text  # the detail stays out of the message


def test_the_walk_reads_only_the_read_document_operation() -> None:
    # A new node parameter that names an extra must extend the walk (design risks).
    from omrs.transports.api import uninstall_profiles

    assert uninstall_profiles.PROFILE_READER_OPERATIONS == frozenset({READER_OPERATION})
