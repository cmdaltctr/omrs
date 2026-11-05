"""Pure-data descriptors of the parts of page reading (change local-ocr-backends, D2).

A reading part is a PDF reader, a local OCR backend or a page rule. Each built-in
part has one frozen descriptor here. The descriptor holds the facts that
``config/``, ``core/ingestion/``, ``compose*.py`` and ``transports/`` need without
importing the part: its name, import path, settings, index-identity contribution
and health facts. Integration code keeps a lazy ``register()`` line per part, and a
pin test compares the two (design D3).

Parts that entry-point discovery accepts (design D11) join the built-in tables
through :func:`install_discovered`. Only the composition root calls it, so the
lookups here see built-in parts only until compose has run discovery.

This module imports only the standard library, like ``core/reading_lists.py``. A test
reads its syntax tree and fails on any ``omrs`` import.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, TypeVar

KIND_PDF_READER = "pdf_reader"
KIND_LOCAL_OCR_BACKEND = "local_ocr_backend"
KIND_PAGE_RULE = "page_rule"

SOURCE_BUILT_IN = "built-in"


@dataclass(frozen=True, kw_only=True)
class SettingField:
    """One setting that a part reads.

    Attributes:
        name: Settings field name, for example ``ocr_maths_routing_enabled``.
        env: Environment variable, for example ``OCR_MATHS_ROUTING_ENABLED``.
        default: Code default of the field.
        accepted: Accepted values for a choice field, or ``None`` when free.
        enters_identity: True when the value takes part in the index identity.
    """

    name: str
    env: str
    default: Any
    accepted: tuple[str, ...] | None = None
    enters_identity: bool = False


@dataclass(frozen=True, kw_only=True)
class IdentitySpec:
    """Where a part contributes to the index identity.

    Attributes:
        block: Identity block: ``ocr_routing``, ``maths_routing`` or ``parser``.
        keys: Keys that the part writes in that block.
        presence: When the block is present. ``always``; ``pdf_when_on`` (only PDF
            sources, and only when the part is on); ``with_local_tier``
            (only when the local OCR tier is in use).
    """

    block: str
    keys: tuple[str, ...]
    presence: str


@dataclass(frozen=True, kw_only=True)
class HealthFacts:
    """Facts that a health check reads about a part.

    Attributes:
        model_files: File names that the part needs on disk.
        cache_folder: Folder of those files, relative to the model directory.
        licence: Licence note to show to the operator.
    """

    model_files: tuple[str, ...] = ()
    cache_folder: str | None = None
    licence: str | None = None


@dataclass(frozen=True, kw_only=True)
class PartDescriptor:
    """Facts common to every reading part.

    Attributes:
        name: Part name, unique within its kind.
        kind: ``pdf_reader``, ``local_ocr_backend`` or ``page_rule``.
        import_path: ``module:attr`` of the implementation, loaded on first use.
        label: Short name for the UI.
        help_key: Key of the help text.
        extra: Optional-dependency group that installs the part, or ``None`` when
            the package is in the base install.
        probe_module: Module that the installed check looks for without importing it.
        settings: Settings that the part reads, with their defaults.
        options: Settings of a part that has no flat keys.
        identity: Index-identity contribution, or ``None``.
        version: Integer that the part bumps when its output changes.
        health: Facts for health checks.
        source: ``built-in`` or the name of the distribution that adds the part.
    """

    name: str
    kind: str
    import_path: str
    label: str
    help_key: str
    extra: str | None = None
    probe_module: str | None = None
    settings: tuple[SettingField, ...] = ()
    options: tuple[SettingField, ...] = ()
    identity: IdentitySpec | None = None
    version: int = 1
    health: HealthFacts = HealthFacts()
    source: str = SOURCE_BUILT_IN


def _require_kind(descriptor: PartDescriptor, expected: str) -> None:
    if descriptor.kind != expected:
        raise ValueError(
            f"{type(descriptor).__name__} {descriptor.name!r} has kind "
            f"{descriptor.kind!r}, expected {expected!r}"
        )


@dataclass(frozen=True, kw_only=True)
class PdfReaderDescriptor(PartDescriptor):
    """A PDF reader.

    Attributes:
        text_format: ``plain`` or ``markdown``.
        page_provenance: True when each document carries its page number.
        output_revision: Revision of the reader output; a change re-ingests.
    """

    kind: str = field(default=KIND_PDF_READER, init=False)
    text_format: str
    page_provenance: bool
    output_revision: int = 1

    def __post_init__(self) -> None:
        _require_kind(self, KIND_PDF_READER)


@dataclass(frozen=True, kw_only=True)
class LocalOcrBackendDescriptor(PartDescriptor):
    """A local OCR backend of the local tier.

    Attributes:
        min_confidence: Registered escalation cut, or ``None`` (not listable).
        calibrated_by: Experiment folder that measured the cut. Required with a cut.
        keeps_scripts: Lower-case Unicode script names the backend may keep, or
            ``None`` for no script filter.
        producer: ``ocr_backend`` value of the pages the backend keeps.
        model: Expected model identity as ``name@revision``, or ``None``.
    """

    kind: str = field(default=KIND_LOCAL_OCR_BACKEND, init=False)
    min_confidence: float | None = None
    calibrated_by: str | None = None
    keeps_scripts: frozenset[str] | None = None
    producer: str
    model: str | None = None

    def __post_init__(self) -> None:
        _require_kind(self, KIND_LOCAL_OCR_BACKEND)
        if self.min_confidence is not None and not self.calibrated_by:
            raise ValueError(
                f"local OCR backend {self.name!r} has a cut ({self.min_confidence}) "
                "but no calibrated_by experiment"
            )


@dataclass(frozen=True, kw_only=True)
class PageRuleDescriptor(PartDescriptor):
    """A page rule of the page-reading hook.

    Attributes:
        order: Position among the rules; unique across page rules.
        drops_pages: True when the rule can drop a page.
        sends_direct: True when the rule can send a page straight to OCR.
        has_post_check: True when the rule checks the OCR output.
        has_degrade: True when the rule can degrade a page to local text.
        adds_pages: True when the rule can add unflagged pages to the OCR route
            (change document-reading-routers, design D4).
    """

    kind: str = field(default=KIND_PAGE_RULE, init=False)
    order: int
    drops_pages: bool = False
    sends_direct: bool = False
    has_post_check: bool = False
    has_degrade: bool = False
    adds_pages: bool = False

    def __post_init__(self) -> None:
        _require_kind(self, KIND_PAGE_RULE)


D = TypeVar("D", bound="PartDescriptor")


def names(table: tuple[PartDescriptor, ...]) -> tuple[str, ...]:
    """Return the part names of *table* in table order."""
    return tuple(descriptor.name for descriptor in table)


def by_name(table: tuple[D, ...], name: str) -> D:
    """Return the descriptor called *name*.

    Raises:
        KeyError: If *name* is not in *table*. The message lists the names.
    """
    for descriptor in table:
        if descriptor.name == name:
            return descriptor
    raise KeyError(f"unknown reading part {name!r}; known: {', '.join(names(table))}")


def check_table(table: tuple[PartDescriptor, ...]) -> None:
    """Refuse a table with a repeated name within a kind or a repeated page rule order.

    Raises:
        ValueError: Naming the duplicate.
    """
    seen_names: set[tuple[str, str]] = set()
    seen_orders: dict[int, str] = {}
    for descriptor in table:
        key = (descriptor.kind, descriptor.name)
        if key in seen_names:
            raise ValueError(f"duplicate {descriptor.kind} name {descriptor.name!r}")
        seen_names.add(key)
        if isinstance(descriptor, PageRuleDescriptor):
            if descriptor.order in seen_orders:
                raise ValueError(
                    f"duplicate page rule order {descriptor.order}: "
                    f"{seen_orders[descriptor.order]!r} and {descriptor.name!r}"
                )
            seen_orders[descriptor.order] = descriptor.name


#: Built-in order equals ``PDF_READER_NAMES`` in ``config/rules.py`` without ``auto``.
PDF_READERS: tuple[PdfReaderDescriptor, ...] = (
    PdfReaderDescriptor(
        name="liteparse",
        import_path="omrs.integrations.pdf.liteparse:LiteParseReader",
        label="LiteParse",
        help_key="pdf_reader.liteparse",
        probe_module="liteparse",
        text_format="plain",
        page_provenance=True,
    ),
    PdfReaderDescriptor(
        name="pdf_inspector",
        import_path="omrs.integrations.pdf.pdf_inspector:PdfInspectorReader",
        label="pdf-inspector",
        help_key="pdf_reader.pdf_inspector",
        probe_module="pdf_inspector",
        text_format="markdown",
        page_provenance=True,
        output_revision=2,
    ),
    PdfReaderDescriptor(
        name="pypdfium2",
        import_path="omrs.integrations.pdf.pypdfium:PyPDFium2Reader",
        label="pypdfium2",
        help_key="pdf_reader.pypdfium2",
        extra="pdf-pypdfium2",
        probe_module="pypdfium2",
        text_format="plain",
        page_provenance=True,
    ),
    PdfReaderDescriptor(
        name="pypdf",
        import_path="omrs.integrations.pdf.pypdf:PyPDFReader",
        label="pypdf",
        help_key="pdf_reader.pypdf",
        probe_module="pypdf",
        text_format="plain",
        page_provenance=True,
    ),
)

LOCAL_OCR_BACKENDS: tuple[LocalOcrBackendDescriptor, ...] = (
    LocalOcrBackendDescriptor(
        name="pp-ocrv6-small",
        import_path="omrs.integrations.pdf.local_ocr.pp_ocrv6_small:BACKEND",
        label="PP-OCRv6 small",
        help_key="local_ocr_backend.pp-ocrv6-small",
        probe_module="pdf_inspector",
        settings=(
            SettingField(
                name="ocr_local_min_confidence",
                env="OCR_LOCAL_MIN_CONFIDENCE",
                # Unset: each listed backend uses its own cut (design D9).
                default=None,
                enters_identity=True,
            ),
            SettingField(name="ocr_local_offline", env="OCR_LOCAL_OFFLINE", default=False),
            SettingField(
                name="ocr_local_model_directory",
                env="OCR_LOCAL_MODEL_DIRECTORY",
                default="",
            ),
        ),
        identity=IdentitySpec(
            block="ocr_routing",
            keys=("local_tier",),
            presence="with_local_tier",
        ),
        health=HealthFacts(
            model_files=("pp-ocrv6_small_det.onnx", "pp-ocrv6_small_rec.onnx", "ppocrv6_dict.txt"),
            cache_folder="pp-ocrv6-small/oar-ocr-v0.7.0",
        ),
        min_confidence=0.9,
        calibrated_by="39-local-tier-escalation-2026-09-30",
        keeps_scripts=None,
        producer="pdf_inspector_ocr",
        model="pp-ocrv6-small@oar-ocr-v0.7.0",
    ),
    LocalOcrBackendDescriptor(
        name="indra",
        import_path="omrs.integrations.pdf.local_ocr.indra:BACKEND",
        label="Indra OCR",
        help_key="local_ocr_backend.indra",
        # Exact pin indra-ocr==1.1.2: the cut was measured on 1.1.2 only (design D19).
        extra="local-ocr-indra",
        probe_module="indra_ocr",
        # The folder is INDRA_OCR_MODEL_DIR or the Hugging Face cache, so no
        # cache_folder: health reports the files as unknown. Weights tree hash
        # 1a9ef1fc65c0546f63b89eed936e524077ba94dcd1d7689de89265b158b9324f.
        health=HealthFacts(
            model_files=("det.onnx", "rec.onnx", "meta.json"),
            licence=(
                "code Apache-2.0; weights modified OpenRAIL-M, read by the operator on 2026-11-04"
            ),
        ),
        min_confidence=0.90,
        calibrated_by="46-local-ocr-backends-2026-11-04",
        keeps_scripts=frozenset({"arabic", "devanagari"}),
        producer="indra_ocr",
        model="datalab-to/indra-ocr@bd02167fdf2005a19962cc15188f8496a2c87d3b",
    ),
)

PAGE_RULES: tuple[PageRuleDescriptor, ...] = (
    PageRuleDescriptor(
        name="blank",
        import_path="omrs.integrations.pdf.page_rules.blank:RULE",
        label="Blank pages",
        help_key="page_rule.blank",
        identity=IdentitySpec(block="ocr_routing", keys=("blank_page_test",), presence="always"),
        order=10,
        drops_pages=True,
    ),
    PageRuleDescriptor(
        name="maths",
        import_path="omrs.integrations.pdf.page_rules.maths:RULE",
        label="Maths pages",
        help_key="page_rule.maths",
        settings=(
            SettingField(
                name="ocr_maths_routing_enabled",
                env="OCR_MATHS_ROUTING_ENABLED",
                default=True,
                enters_identity=True,
            ),
        ),
        identity=IdentitySpec(
            block="maths_routing",
            keys=("enabled", "detector_version"),
            presence="always",
        ),
        order=20,
        sends_direct=True,
    ),
    PageRuleDescriptor(
        name="non_latin",
        import_path="omrs.integrations.pdf.page_rules.non_latin:RULE",
        label="Non-Latin scripts",
        help_key="page_rule.non_latin",
        settings=(
            SettingField(
                name="ocr_non_latin_routing",
                env="OCR_NON_LATIN_ROUTING",
                default="off",
                accepted=("off", "detect", "always"),
                enters_identity=True,
            ),
        ),
        identity=IdentitySpec(
            block="parser",
            keys=("non_latin_routing",),
            presence="pdf_when_on",
        ),
        order=30,
        sends_direct=True,
        has_post_check=True,
        has_degrade=True,
    ),
    PageRuleDescriptor(
        name="document_router",
        import_path="omrs.integrations.pdf.page_rules.document_router:RULE",
        label="Document router",
        help_key="page_rule.document_router",
        # "" means no router. The router recipe, not its name, enters the identity.
        settings=(SettingField(name="document_router", env="DOCUMENT_ROUTER", default=""),),
        identity=IdentitySpec(block="parser", keys=("document_router",), presence="pdf_when_on"),
        order=40,
        has_degrade=True,
        adds_pages=True,
    ),
)

check_table(PDF_READERS)
check_table(LOCAL_OCR_BACKENDS)
check_table(PAGE_RULES)

#: Default ``ocr_local_backends``: the first backend of the table (design D8).
DEFAULT_LOCAL_OCR_BACKENDS: tuple[str, ...] = (LOCAL_OCR_BACKENDS[0].name,)


#: The implicit option of every page rule (design D12). A discovered rule runs
#: only when it is ``true``; a built-in rule ignores it.
RULE_ENABLED_OPTION = SettingField(name="enabled", env="", default=False)

#: The descriptors that discovery accepted, set by :func:`install_discovered`.
_discovered: tuple[PartDescriptor, ...] = ()
#: ``(kind, name) -> problem`` of the discovered parts that failed to load.
_broken: dict[tuple[str, str], str] = {}


def install_discovered(
    descriptors: Iterable[PartDescriptor], broken: Iterable[tuple[str, str, str]] = ()
) -> None:
    """Add the discovered parts to the lookups (composition root only).

    Args:
        descriptors: The accepted descriptors.
        broken: ``(kind, name, problem)`` of each part that failed to load. A
            setting may name such a part; it is off.
    """
    global _discovered, _broken
    _discovered = tuple(descriptors)
    _broken = {(kind, name): problem for kind, name, problem in broken}


def reset_discovered() -> None:
    """Forget the discovered parts (test seam)."""
    global _discovered, _broken
    _discovered = ()
    _broken = {}


def broken(kind: str | None = None) -> dict[str, str]:
    """Return ``name -> problem`` of the broken discovered parts, of one *kind* when given."""
    return {name: problem for (k, name), problem in _broken.items() if kind is None or k == kind}


def discovered(kind: str | None = None) -> tuple[PartDescriptor, ...]:
    """Return the discovered descriptors, of one *kind* when it is given."""
    return tuple(d for d in _discovered if kind is None or d.kind == kind)


def parts_named(name: str) -> tuple[PartDescriptor, ...]:
    """Return every built-in and discovered descriptor called *name*, of any kind."""
    table = (*PDF_READERS, *LOCAL_OCR_BACKENDS, *PAGE_RULES, *_discovered)
    return tuple(d for d in table if d.name == name)


def local_backend(name: str) -> LocalOcrBackendDescriptor:
    """Return the local OCR backend called *name*, built-in or discovered.

    The table is read at call time, so a test can patch
    :data:`LOCAL_OCR_BACKENDS` on this module.

    Raises:
        KeyError: If no backend has that name.
    """
    extra: tuple[Any, ...] = discovered(KIND_LOCAL_OCR_BACKEND)
    return by_name((*LOCAL_OCR_BACKENDS, *extra), name)


def effective_cut(settings: Any, name: str) -> float | None:
    """Return the confidence cut backend *name* applies (design D9).

    The operator value ``ocr_local_min_confidence`` replaces the cut of every
    listed backend when it is set. Unset, the backend keeps its own cut.
    """
    override = getattr(settings, "ocr_local_min_confidence", None)
    return override if override is not None else local_backend(name).min_confidence
