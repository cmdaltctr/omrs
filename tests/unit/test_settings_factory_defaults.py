"""Metadata defaults of the ``effective_settings`` test factory.

The ``MetadataBlock`` class default is ``extraction_mode="llamaindex"`` with
three classify attempts. A test that ingests with those values makes a real
LLM call that waits on network retries and then falls back without a sign.
The factory therefore pins metadata extraction off and one attempt, unless
the caller asks for something else (design D1 of speed-up-fast-test-suite).
"""

from __future__ import annotations

from omrs.core.settings import MetadataBlock


def test_factory_default_disables_metadata_extraction(effective_settings) -> None:
    """A factory-built object has extraction off and one classify attempt."""
    settings = effective_settings()

    assert settings.metadata.extraction_mode == "disabled"
    assert settings.metadata.classify_max_attempts == 1


def test_dotted_metadata_override_keeps_the_other_defaults(effective_settings) -> None:
    """A dotted override changes one field and keeps both factory defaults."""
    settings = effective_settings(**{"metadata.classify_timeout": 7.0})

    assert settings.metadata.classify_timeout == 7.0
    assert settings.metadata.extraction_mode == "disabled"
    assert settings.metadata.classify_max_attempts == 1


def test_whole_metadata_block_is_kept_as_given(effective_settings) -> None:
    """A whole ``MetadataBlock`` from the caller gets no factory defaults."""
    block = MetadataBlock(extraction_mode="keyword", classify_max_attempts=2)

    settings = effective_settings(metadata=block)

    assert settings.metadata is block
    assert settings.metadata.extraction_mode == "keyword"
    assert settings.metadata.classify_max_attempts == 2
