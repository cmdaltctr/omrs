# tests (Python test suite)

Fast tests (`-m "not slow"`) need no Ollama and no disk I/O. Slow tests carry the `slow` marker.

## Where to start

- Read [TEST_README.md](TEST_README.md) first.

## Rules

1. Build settings with the `effective_settings(**overrides)` fixture or `set_default_effective_settings(...)`. The factory sets `extraction_mode="disabled"` and `classify_max_attempts=1`. Do not undo the conftest defaults (`PDF_READER=pypdf`, `extraction_mode="disabled"`).
2. A conftest guard fails a test that dispatches an LLM metadata strategy (any strategy other than `disabled` or `keyword`). Mark a test `@pytest.mark.metadata_llm` only when it calls an LLM strategy on purpose, with the LLM mocked. Otherwise fix its settings.
3. Patch a name at the module that defines it, not at a re-export.
4. Reranker tests call `reset_model_cache()`. Restore any logging handler or level that a test changes.
5. A new fast test changes `_BASE_EXECUTED` in `test_clean_base_tripwire.py`. A new slow test changes `_BASE_DESELECTED`. Update the count with a dated comment.
6. Parallel runs use `--dist loadfile`. Do not pass `--dist load`.
7. Chroma tests skip without the `chroma` extra. CI runs them in the Coverage job, which fails when one skips for a missing chroma extra.

## Links

- [Root AGENTS.md](../AGENTS.md)
- [Testing guide](../docs/guides/testing.md)
