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
from omrs.integrations.pdf.page_rules import registry as page_rule_registry

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


#: The facts a page rule descriptor and its registration both carry.
_PAGE_RULE_FIELDS = (
    "import_path",
    "order",
    "drops_pages",
    "sends_direct",
    "has_post_check",
    "has_degrade",
    "source",
)


def test_every_page_rule_descriptor_has_a_registration_and_back() -> None:
    """Names agree in both directions, so a missing line names the rule."""
    described = set(reading_parts.names(reading_parts.PAGE_RULES))
    registered = set(page_rule_registry.available())
    assert described - registered == set(), "descriptor without register(): "
    assert registered - described == set(), "register() without descriptor: "


def test_page_rule_descriptor_and_registration_agree_on_each_fact() -> None:
    """Import path, order, the four hook flags and the source agree."""
    problems = []
    for descriptor in reading_parts.PAGE_RULES:
        entry = page_rule_registry.describe(descriptor.name)
        for field in _PAGE_RULE_FIELDS:
            if entry[field] != getattr(descriptor, field):
                value = getattr(descriptor, field)
                problems.append(f"{descriptor.name}.{field}: {value!r} != {entry[field]!r}")
    assert problems == []
