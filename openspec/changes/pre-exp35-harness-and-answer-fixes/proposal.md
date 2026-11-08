# Proposal: pre-Experiment-35 bug fixes (answer sampling, ingest overhead, harness, login-item paths)

## Why

Experiment 48 (the pipeline sweep, PASS, merged 2026-11-08) cleared OMRS to freeze Experiment 35a, but it left gaps that would make 35a's numbers weaker or its run slower:

- OMRS has no temperature or seed setting for answers or the claim judge. No seed is sent. The temperature sent is a hidden library default: LlamaIndex adds `temperature: 0.1` to every request on the OpenAI-compatible providers (llama.cpp, OpenRouter, OpenAI-compatible; checked 2026-11-08). Experiment 35 design D3 needs temperature 0 and a fixed seed on every answer, and the 35a protocol fixes the seed at 20261101, so answer scores repeat. Today they cannot, and no record says what was sent.
- Ingest spends about 0.88 s per file on work that is neither reading, chunking nor embedding (Experiment 48 Part B: 176 of 270 s for 200 FreshStack files). FreshStack has 10,024 files and BioASQ 40.2K abstracts, so this cost sets 35a's run time and RunPod bill. Nobody knows yet where it goes.
- Four small harness bugs in the Experiment 48 code that 35a will reuse.
- `omrs web install` still drops `INDRA_OCR_MODEL_DIR` from the login item (issue #175, rest of it).

## What Changes

- **Answer sampling settings.** New `answer.temperature`, `answer.seed`, `answer.verify_temperature` and `answer.verify_seed`. Empty keeps today's request unchanged (the library default, so no behaviour changes for existing users). A set value goes on every Chat or claim-judge request through the provider registry (the same pattern as `answer.reasoning`). A provider that cannot take a field reports that it ignores it. Settings shows the four values on the Chat and Judge panels; only the web app writes them to `omrs.jsonc` (ADR-087). Every answer result records the temperature and seed the request carried, including a library default.
- **Per-file ingest overhead.** Profile one 200-file FreshStack ingest on the Mac, record the profile as evidence, and fix only what the profile shows. If the fix changes behaviour, its requirement is added to this change before code (via `openspec-update-change`).
- **Shared benchmark harness.** Move the Experiment 48 code that 35a reuses into `experiments/_lib/` (Experiment 48's folder stays as it ran), and fix four bugs on the way:
  - neighbour lists include the query chunk on a slice with 10 or fewer chunks;
  - Part C vector files are not written atomically;
  - the determinism comparison never compares a question present only in run 1 (the Experiment 48 call site keys both rankings on run 2's questions; run-2-only questions are already reported as incomplete);
  - a relative GGUF folder path fails later, in the router config.
- **Login item keeps the OCR variables (#175).** `omrs web install` keeps `INDRA_OCR_MODEL_DIR`, `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` from the plist it replaces, and takes them from the installing shell when set there.
- **CI flakes.** Two llama.cpp router tests failed once each on `v3` (runs 42509580109 and 42516121302). Fix the cause found in task group 6.
- **No pod rerun.** Experiment 48's missing Part C speeds and full-corpus token counts (its tasks 4.3, 5.4, 5.5) are not rerun. 35a's own first timing step measures them; master task 6.1 writes that into the 35a plan.

## Capabilities

### New Capabilities

- `answer-sampling`: temperature and seed for the Chat and claim-judge models, sent only when set, shown in Settings and recorded with each answer.
- `benchmark-harness`: the shared experiment code under `experiments/_lib/` that compares rankings and neighbour lists and writes timing outputs.

### Modified Capabilities

- `web-login-item`: the login item keeps the local OCR environment variables across a re-install.

## Impact

- Code: `src/omrs/core/answer/settings.py`, `src/omrs/core/settings.py` (`AnswerBlock`), `src/omrs/core/providers/llm/` (registry plus `openrouter.py`, `openai_compatible.py`, `llamacpp.py`, `anthropic.py`, `ollama.py`), `src/omrs/compose_answer.py`, answer results, `transports/api/routes/chat_settings.py`, `judge_settings.py` and `chat_reasoning.py`, `engine_providers.py` (`_EDITABLE_ANSWER`), `config/provider_sources.py` (`PROVIDER_FIELDS`), `transports/api/openapi.yaml`, the MCP `answer_documents` output, the Chat and Judge panels in `web/src/`, `transports/cli/_web_login_item.py` and `web_login_item.py`, `experiments/_lib/`, and whatever the profile names.
- Tests: new cases change the tripwire pins (`_BASE_EXECUTED`, `_WEB_EXTRA_CASES`).
- Docs: `docs/guides/configuration.md`, `docs/guides/mcp-tools.md` (answer result) and `docs/guides/cli-reference.md` (`omrs web install`).
- No new dependency. No live-app change. No pod, no spend.
- Out of scope: issue #161 (needs an experiment), #159 (no code path triggers it), and the low-severity UI and tech-debt issues.
