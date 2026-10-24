# src/omrs/core/providers (LLM and embedding providers)

One module per provider, found through a lazy registry.

## What belongs here

- `llm/`: chat, answer and metadata providers. `embeddings/`: embedding providers.
- One file per provider with a `build` callable. Each LLM module also defines `CONNECTION`, a `ConnectionDescriptor` (`llm/connection.py`) for its Providers card.
- `llm/registry.py` and `embeddings/registry.py` map a name to a `"module:attr"` string. `get()` imports it on first use.
- `common.py`: shared endpoint and key reads.

## What it must not do

- Import a provider SDK at module level. Import it inside `build()`, as `core/providers/llm/anthropic.py` does. `describe_all()` imports every LLM module, so a top-level SDK import fails without the extra.
- Branch on provider names with `if/elif` in dispatch code (root invariant 11). Register the provider instead.
- Be imported directly from elsewhere. Only `compose` and this folder may import the concrete modules that the import-linter contract `providers-constructed-only-in-compose` lists.

## Rules

1. Add a provider with one file and one `register()` line at the bottom of its registry.
2. A provider that needs a `pyproject.toml` extra goes into `_PROVIDER_EXTRAS` in its registry. `extra_for()` reads that map.
3. The uninstall in-use check (`transports/api/uninstall_plan.py`) reads `extra_for()`. Without the entry, the app can remove an extra that a setting still uses.
4. Set the same extra on `ConnectionDescriptor.extra`. The Providers card names it in its install hint. Use `None` for a base-install provider. No test compares the two maps.
5. A role setting can hold `local` or `cloud`. Resolve it through `local_backend` or `cloud_backend`, as `src/omrs/compose_connections.py` and `uninstall_plan.py` do.

## Links

- [Root AGENTS.md](../../../../AGENTS.md)
- [Core guide](../AGENTS.md)
- [ADR-096: uninstall from the app](../../../../docs/adr/096-app-uninstalls-extras-it-can-install.md)
