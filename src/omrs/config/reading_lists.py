"""The ordered reader and engine lists of ``Settings`` (change ordered-reader-and-ocr-lists, D4).

``pdf_readers`` and ``ocr_engines`` sit beside the single-value keys
``pdf_reader``, ``ocr_engine_primary`` and ``ocr_engine_fallback``. The single
keys stay valid in every source. This mixin settles which form decides:

- The highest source that sets either form wins (``init``, ``env``,
  ``dotenv``, ``config-file``, ``yaml``).
- Within one source the list key wins, and the single key is logged as ignored.
- A winning single form is expanded into the list, so every reader of the
  list sees one answer. A winning list is shown back through the single keys
  (first entry, and second entry as fallback), so code that still reads them
  stays right.
- With no form set anywhere the defaults stand, and they equal each other
  (the default list is the expansion of the default single keys).

The mixin sits before ``ProviderSourceMixin`` in the ``Settings`` bases, so its
validator runs after ``ProviderSourceMixin`` has recorded ``setting_sources``.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping
from typing import Any

from pydantic import BaseModel, ValidationInfo, field_validator, model_validator

from ..core.reading_lists import (
    OCR_ENGINES_DEFAULT,
    PDF_READERS_DEFAULT,
    NameList,
    expand_ocr_engines,
    expand_pdf_reader,
)
from ..core.reading_parts import (
    DEFAULT_LOCAL_OCR_BACKENDS,
    KIND_LOCAL_OCR_BACKEND,
    discovered,
)
from .provenance import SOURCE_ORDER
from .rules import OLD_READING_KEYS, ignored_old_keys, local_backend_problem

logger = logging.getLogger(__name__)


def _first_word(layers: Mapping[str, Collection[str]], keys: tuple[str, ...]) -> str | None:
    """Return the highest source word whose layer holds any of *keys*."""
    return next(
        (word for word in SOURCE_ORDER if any(key in layers.get(word, ()) for key in keys)), None
    )


def _single_wins(layers: Mapping[str, Collection[str]], list_key: str) -> tuple[bool, str | None]:
    """Return ``(wins, word)``: whether the single-value form decides, and its source word.

    With no list key in any source the single keys decide, even when they hold
    a blank (``OCR_ENGINE_FALLBACK=`` has always meant "no fallback"), and *word*
    is ``None`` when no source set them. At the same source the list key wins.
    """
    listed = _first_word(layers, (list_key,))
    single = _first_word(layers, OLD_READING_KEYS[list_key])
    if listed is None:
        return True, single
    if single is None or SOURCE_ORDER.index(listed) <= SOURCE_ORDER.index(single):
        return False, None
    return True, single


class ReadingListMixin(BaseModel):
    """The ordered list fields of :class:`omrs.config.Settings`."""

    pdf_readers: NameList = PDF_READERS_DEFAULT
    ocr_engines: NameList = OCR_ENGINES_DEFAULT
    # Change local-ocr-backends, design D8: the local OCR tier's backend order.
    ocr_local_backends: NameList = DEFAULT_LOCAL_OCR_BACKENDS
    # Design D12: options of parts without flat keys, keyed by part name. The
    # environment form (READING_PART_OPTIONS) is JSON. Compose checks each entry
    # against the part's descriptor at start-up.
    reading_part_options: dict[str, dict[str, Any]] = {}

    @field_validator("pdf_readers", "ocr_engines", "ocr_local_backends", mode="after")
    @classmethod
    def _blank_means_default(cls, value: tuple[str, ...], info: ValidationInfo) -> tuple[str, ...]:
        """Read ``PDF_READERS=`` (no names) as not set, as other blank lines are."""
        return value or cls.model_fields[str(info.field_name)].default

    @model_validator(mode="after")
    def _check_local_backends(self) -> ReadingListMixin:
        """Stop start-up on an unknown backend or one without a calibrated cut (design D8).

        Backends that compose discovered (design D11) are accepted too; before
        compose runs discovery there are none, so ``config`` reads no entry point.
        """
        extra: tuple[Any, ...] = discovered(KIND_LOCAL_OCR_BACKEND)
        problem = local_backend_problem(self.ocr_local_backends, extra)
        if problem:
            raise ValueError(
                f"OCR_LOCAL_BACKENDS={','.join(self.ocr_local_backends)!r} is not valid. {problem}"
            )
        return self

    @model_validator(mode="after")
    def _settle_reading_lists(self) -> ReadingListMixin:
        """Pick the winning form of each list and make the other form agree with it."""
        layers: Mapping[str, Collection[str]] = getattr(self.__class__, "_source_layers", {})
        sources = dict(getattr(self, "setting_sources", {}))
        self._warn_ignored(layers)
        for list_key in OLD_READING_KEYS:
            wins, word = _single_wins(layers, list_key)
            if not wins:
                self._show_list_as_old_keys(list_key)
                continue
            object.__setattr__(self, list_key, self._expand(list_key))
            if word is not None:
                sources[list_key] = word
        object.__setattr__(self, "setting_sources", sources)
        object.__setattr__(
            self,
            "config_file_fields",
            frozenset(path for path, word in sources.items() if word == "config-file"),
        )
        return self

    def _expand(self, list_key: str) -> tuple[str, ...]:
        """Return the list that the old keys of *list_key* mean."""
        if list_key == "pdf_readers":
            return expand_pdf_reader(self.pdf_reader)  # type: ignore[attr-defined]
        return expand_ocr_engines(
            self.ocr_engine_primary,  # type: ignore[attr-defined]
            self.ocr_engine_fallback,  # type: ignore[attr-defined]
        )

    def _show_list_as_old_keys(self, list_key: str) -> None:
        """Set the old keys from the list, so code that reads them stays right."""
        names: tuple[str, ...] = getattr(self, list_key)
        if list_key == "pdf_readers":
            object.__setattr__(self, "pdf_reader", names[0])
            return
        object.__setattr__(self, "ocr_engine_primary", names[0])
        object.__setattr__(self, "ocr_engine_fallback", names[1] if len(names) > 1 else "")

    @staticmethod
    def _warn_ignored(layers: Mapping[str, Collection[str]]) -> None:
        """Log each old key that sits beside its list key in one source.

        ``omrs.jsonc`` is skipped: the file reader drops the old key and lists
        it as a problem before ``Settings`` is built.
        """
        for word in (w for w in SOURCE_ORDER if w != "config-file"):
            for old, new in ignored_old_keys(layers.get(word, ())):
                logger.warning(
                    "Ignoring %s in the %s source: %s is set there and wins.", old, word, new
                )
