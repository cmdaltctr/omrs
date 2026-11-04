"""Pin each built-in part descriptor to its integration ``register()`` line.

Change local-ocr-backends, design D3: integration code cannot import
``core/reading_parts.py`` (contract ``integrations-are-leaves``), so each
built-in part has two lines, a descriptor entry and a lazy ``register()``
line. This test fails when one of the two is missing or when a shared fact
differs between them.
"""

from __future__ import annotations

from omrs.core import reading_parts
from omrs.integrations.pdf import registry as pdf_registry

#: The facts a PDF reader descriptor and its registration both carry.
_PDF_READER_FIELDS = ("import_path", "probe_module", "text_format", "page_provenance")


def test_every_pdf_reader_descriptor_has_a_registration_and_back() -> None:
    """Names agree in both directions, so a missing line names the part."""
    described = set(reading_parts.names(reading_parts.PDF_READERS))
    registered = set(pdf_registry.available())
    assert described - registered == set(), "descriptor without register(): "
    assert registered - described == set(), "register() without descriptor: "


def test_pdf_reader_descriptor_and_registration_agree_on_each_fact() -> None:
    """Import path, probe, text format, page provenance and output revision agree."""
    problems = []
    for descriptor in reading_parts.PDF_READERS:
        entry = pdf_registry.describe(descriptor.name)
        expected = {field: getattr(descriptor, field) for field in _PDF_READER_FIELDS}
        expected["output_revision"] = descriptor.output_revision
        for field, value in expected.items():
            if entry[field] != value:
                problems.append(f"{descriptor.name}.{field}: {value!r} != {entry[field]!r}")
    assert problems == []
