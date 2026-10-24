# TDR-038: The Ollama floor took only true or false for thinking, so raise it to 0.9.1

- **Date:** 2026-10-24
- **Status:** Accepted
- **Deciders:** Aizat Hawari
- **Tags:** dependencies | floors | ollama | reasoning | ci

## Context

On 2026-10-24 all 10 "Floor resolution" jobs failed on v3 (GitHub run 40093080026). The other CI jobs passed. The floor jobs install each direct dependency at its lowest declared version (`--resolution lowest-direct`) and run the fast suite (ADR-042).

Each floor job failed the same test:

```text
FAILED tests/unit/test_llm_reasoning_providers.py::test_ollama_sends_think[low-low]
pydantic_core._pydantic_core.ValidationError: 1 validation error for Ollama
thinking
```

### Root Cause Analysis

The Chat reasoning level maps to Ollama's `think` field in `core/providers/llm/ollama.py`. The levels `low`, `medium` and `high` go to Ollama as text. Other levels send `True`, and `none` sends `False`. `build()` passes the value to the LlamaIndex `Ollama` class as `thinking=`.

`pyproject.toml` declared `llama-index-llms-ollama>=0.9.0`. In 0.9.0 the `thinking` field accepts only a boolean, so `thinking="low"` fails pydantic validation. Release 0.9.1 is the first that accepts a level text. The lock file has 0.10.1, so the normal test jobs never saw the fault. Only the floor jobs installed 0.9.0.

We reproduced the failure by installing 0.9.0 in a scratch environment. The test passed after we installed 0.9.1.

## Decision

Raise the floor to the first version that accepts a level text. The comment beside the requirement records the reason:

```toml
# 0.9.1 is the first release whose ``thinking`` field takes a level text
# ("low", "medium", "high"); 0.9.0 takes only true or false, so the Chat
# reasoning level "low" fails there (CI floors run 40093080026).
"llama-index-llms-ollama>=0.9.1",
```

`uv.lock` changes only the declared minimum. The locked version stays 0.10.1. The floor is within one minor of the lock, so `tests/test_dependency_floors.py` needs no exemption.

## Consequences

### Positive

- The floor jobs test the same reasoning behaviour that users get from the lock.
- A user who installs at the floor gets working reasoning levels on Ollama.

### Negative

- Environments pinned to 0.9.0 must upgrade.

### Neutral

- No code changed. The level mapping and its tests are the same.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Send `True` instead of a level text when the installed version is 0.9.0 | Adds a version check to the provider for one old patch release. The user's chosen level would be dropped without a message. |
| Skip the level test on the floor jobs | Hides a real fault: a user at the floor gets a validation error in Chat. |
| Raise the floor to the locked 0.10.1 | 0.9.1 is the lowest version proven safe. ADR-042 sets the floor at the lowest safe version, not the lock. |

## How to Recognise / Handle This Again

1. **Symptom:** only the "Floor resolution" jobs fail, with a pydantic `ValidationError` for a provider class. The normal test jobs pass.
2. **Find the version:** read the failed log with `gh run view <id> --log-failed`. Note the package and field in the error.
3. **Reproduce at the floor:** in a scratch environment, install the declared minimum (`uv pip install "<package>==<floor>"`). Run the failing test.
4. **Find the first good release:** install each later patch release in turn until the test passes. Read that release's changelog to confirm the cause.
5. **Fix:** raise the floor in `pyproject.toml` with a comment that names the reason and the CI run. Run `uv lock`. Check `uv run pytest tests/test_dependency_floors.py`.

## Revisit Triggers

- The Ollama provider sends a new value type in `thinking`, or uses a new request field.
- `llama-index-llms-ollama` reaches 1.0 or renames the `thinking` field.
- ADR-042's floor policy changes.

## References

- Fix commit: `b652e253` (`fix(deps): raise the llama-index-llms-ollama floor to 0.9.1`)
- Failed CI run: 40093080026
- `src/omrs/core/providers/llm/ollama.py` (`_THINK_LEVELS`, `reasoning_kwargs`, `build`)
- `tests/unit/test_llm_reasoning_providers.py::test_ollama_sends_think`
- `tests/test_dependency_floors.py`
- ADR-042 (dependency floors)
- TDR-036 (earlier Ollama answer fix in the same provider)
