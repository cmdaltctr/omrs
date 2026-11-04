# src/omrs/integrations (external services)

Adapters for optional tools and services: PDF readers, Magika, Azure and OCR.

## What belongs here

- One module or folder per external system. Each degrades gracefully when its dependency is missing.

## What it must not import

- `omrs.core`, `omrs.transports` or `omrs.daemon` (contract `integrations-are-leaves`).
- The sanctioned exceptions read `omrs.core.settings` only.

## Rules

1. Import optional SDKs inside functions, never at module top (ADR-024; see `azure.py`).
2. Degrade gracefully when an optional dependency or a cloud service is missing. Cloud use is opt-in.
3. A test patches an availability probe at its own module, for example `omrs.integrations.magika`.
4. A new module needs a row in the integration inventory in `docs/guides/architecture.md`. `tests/test_strategy_registration_inventory.py` checks it.
5. Page rules live in `pdf/page_rules/` and local OCR backends in `pdf/local_ocr/`. Each part is one file plus one lazy `register()` line in the folder's `registry.py`. The shared helper is `part_registry.py`.
6. A new part also needs a descriptor in `core/reading_parts.py`. This folder cannot import `core`, so the descriptor is a second line. `tests/unit/test_reading_parts_pins.py` fails when the two disagree.

## Links

- [Root AGENTS.md](../../../AGENTS.md)
- [Architecture guide](../../../docs/guides/architecture.md)
