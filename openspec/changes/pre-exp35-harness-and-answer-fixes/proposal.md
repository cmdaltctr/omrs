# Proposal: pre-Experiment-35 fixes (answer sampling, host pin, claim judges, ingest overhead, harness, login item)

## Why

Experiment 48 (the pipeline sweep, PASS, merged 2026-11-08) cleared OMRS to freeze Experiment 35a, but it left gaps that would make 35a's numbers weaker or its run slower:

- OMRS has no temperature or seed setting for answers or the claim judge. No seed is sent. The temperature sent is a hidden library default: LlamaIndex adds `temperature: 0.1` to every request on the OpenAI-compatible providers (llama.cpp, OpenRouter, OpenAI-compatible; checked 2026-11-08). Experiment 35 design D3 needs temperature 0 and a fixed seed on every answer, and the 35a protocol fixes the seed at 20261101, so answer scores repeat. Today they cannot, and no record says what was sent.
- Ingest spends about 0.88 s per file on work that is neither reading, chunking nor embedding (Experiment 48 Part B: 176 of 270 s for 200 FreshStack files). FreshStack has 10,024 files and BioASQ 40.2K abstracts, so this cost sets 35a's run time and RunPod bill. Nobody knows yet where it goes.
- On OpenRouter a host can drop `seed`. A public read of the `deepseek/deepseek-v4.1-flash-1017` endpoints showed several hosts without it, including the cheapest. OMRS cannot tell today which host served a call or whether that host honoured the seed.
- OMRS checks claims by sending a chat prompt and reading a one-word reply (`core/answer/verify.py`). The 35a claim check needs two typed checkers that use other interfaces: Clef-Flash 9B (a decision model on `/v1/systemone`) and IBM Granite Guardian 3.3 8B (its own guardian prompt). OMRS has no way to register either.
- Four small harness bugs in the Experiment 48 code that 35a will reuse.
- `omrs web install` still drops `INDRA_OCR_MODEL_DIR` from the login item (issue #175, rest of it).

## What Changes

- **Answer sampling settings.** New `answer.temperature`, `answer.seed`, `answer.verify_temperature` and `answer.verify_seed`. Empty keeps today's request unchanged (the library default, so no behaviour changes for existing users). A set value goes on every Chat or claim-judge request through the provider registry (the same pattern as `answer.reasoning`). A provider that cannot take a field reports that it ignores it. Settings shows the four values on the Chat and Judge panels; only the web app writes them to `omrs.jsonc` (ADR-087). Every answer result records the temperature and seed the request carried, including a library default.
- **Allowed OpenRouter hosts.** New `answer.allowed_hosts` and `answer.verify_allowed_hosts`. A set list limits OpenRouter answer and judge calls to those hosts, and OMRS refuses a call when none of them takes every value the request sets. The `sampling` record says which host served the call and which of temperature and seed that host accepts, not only what OMRS sent.
- **Claim-judge strategies.** A small registry in `core/answer/judges/` (none exists; `verify_provider` names an LLM provider, not a judge strategy) and a new setting `answer.verify_judge`. Three strategies: `chat` (today's behaviour, serves GLM-5.3; the default), `clef_flash` (Cloudflare Clef-Flash 9B Q8_0 on `/v1/systemone`; main checker) and `granite_guardian` (IBM Granite Guardian 3.3 8B, groundedness criterion; confirmation checker). Each is one file plus one `register()` line. Each call records model id, host or GGUF SHA-256, prompt-format version and settings.
- **Per-file ingest overhead.** Profile one 200-file FreshStack ingest on the Mac, record the profile as evidence, and fix only what the profile shows. If the fix changes behaviour, its requirement is added to this change before code (via `openspec-update-change`).
- **Shared benchmark harness.** Move the Experiment 48 code that 35a reuses into `experiments/_lib/` (Experiment 48's folder stays as it ran), and fix four bugs on the way:
  - neighbour lists include the query chunk on a slice with 10 or fewer chunks;
  - Part C vector files are not written atomically;
  - the determinism comparison never compares a question present only in run 1 (the Experiment 48 call site keys both rankings on run 2's questions; run-2-only questions are already reported as incomplete);
  - a relative GGUF folder path fails later, in the router config.
- **Login item keeps the OCR folder (#175).** `omrs web install` keeps `INDRA_OCR_MODEL_DIR` from the plist it replaces, and takes it from the installing shell when set there. `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` stay out: PR #176 made OMRS find those libraries itself. `web_login_item.py` (493 lines) is split first, because the new printed lines would push it over 500.
- **Contract and pin gaps from the review.** `AnswerResponse` in `openapi.yaml` gains `sampling`, `judge_calls`, `usage` and `reasoning` and is closed. A test pins that `AnswerBlock` mirrors `AnswerSettings`.
- **Experiment 35a model matrix.** Design D12 fixes which model does what in 35a, with the evidence for each choice. Master task 6.1 copies it into the 35a plan.
- **One pre-freeze RunPod session.** Design D13: the 20-answer measurement, the Part C timing step, the full LLM-AggreFact run on Clef-Flash and Granite Guardian, all on one pod. GLM-5.3 runs the same split through the Z.AI API. Experiment 20's 120 claim triples run again on GLM-5.3 at reasoning `low`. The session needs the operator's go and the new judges merged first.
- **CI flakes.** Two llama.cpp router tests failed once each on `v3` (runs 42509580109 and 42516121302). Fix the cause found in task group 6.
- **No separate pod for Experiment 48's gaps.** Its missing Part C speeds and full-corpus token counts (tasks 4.3, 5.4, 5.5) are measured in the one pre-freeze session (D13). Master task 6.1 writes that into the 35a plan.

## Capabilities

### New Capabilities

- `answer-sampling`: temperature, seed and allowed OpenRouter hosts for the Chat and claim-judge models, sent only when set, shown in Settings and recorded with each answer.
- `claim-judge-strategies`: a registry of claim-judge strategies (`chat`, `clef_flash`, `granite_guardian`) and the per-call record each judge keeps.
- `benchmark-harness`: the shared experiment code under `experiments/_lib/` that compares rankings and neighbour lists and writes timing outputs.

### Modified Capabilities

- `web-login-item`: the login item keeps the local OCR environment variables across a re-install.

## Impact

- Code: `src/omrs/core/answer/judges/` (new), `src/omrs/core/answer/verify.py`, `src/omrs/core/answer/settings.py`, `src/omrs/core/settings.py` (`AnswerBlock`), `src/omrs/core/providers/llm/` (registry plus `openrouter.py`, `openai_compatible.py`, `llamacpp.py`, `anthropic.py`, `ollama.py`), `src/omrs/compose_answer.py`, answer results, `transports/api/routes/chat_settings.py`, `judge_settings.py` and `chat_reasoning.py`, `engine_providers.py` (`_EDITABLE_ANSWER`), `config/provider_sources.py` (`PROVIDER_FIELDS`), `transports/api/openapi.yaml`, the MCP `answer_documents` output, the Chat and Judge panels in `web/src/`, `transports/cli/_web_login_item.py` and `web_login_item.py` (split), `experiments/_lib/`, and whatever the profile names.
- Tests: new cases change the tripwire pins (`_BASE_EXECUTED`, `_WEB_EXTRA_CASES`).
- Docs: `docs/guides/configuration.md`, `docs/guides/mcp-tools.md` (answer result) and `docs/guides/cli-reference.md` (`omrs web install`).
- No new dependency. No live-app change. This change spends nothing; the D13 session is a later, operator-gated step.
- Out of scope: issue #161 (needs an experiment), #159 (no code path triggers it), and the low-severity UI and tech-debt issues.
