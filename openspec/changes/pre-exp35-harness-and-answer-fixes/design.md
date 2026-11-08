# Design: pre-Experiment-35 bug fixes

## Context

- Experiment 48 is closed (PASS). Its report lists the gaps this change closes: no answer temperature or seed (known difference), about 0.88 s per file of unexplained ingest time (Part B), harness bugs scored 3 or below, and missing Part C speeds and token counts (D1, D5).
- `answer.reasoning` and `answer.verify_reasoning` already flow from settings through `compose_answer.py` to each provider's `reasoning_kwargs` (spec `answer-reasoning-and-usage`). Temperature and seed follow the same path.
- LlamaIndex's OpenAI classes default to `temperature: 0.1` and put it on every request (`OpenAILike._get_model_kwargs()`, checked 2026-11-08). So "no setting" today means 0.1 on llama.cpp, OpenRouter and OpenAI-compatible, not "no temperature".
- `experiments/CLAUDE.md`: in a finished experiment only `experiment.json`, `protocol.md` and the report may change. The Experiment 48 harness files are therefore frozen.
- Issue #175: PR #176 (merged 2026-11-05) made the `pp-ocrv6-small` backend set `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` itself in every process. What is left is `INDRA_OCR_MODEL_DIR`: the live login item has it by hand, and `omrs web install` drops it (`render_plist` writes only `PATH`).
- Issue #177 was closed on 2026-11-08 (fixed by `b62605f8`, then by the router change). Issue #180 was closed (fixed by PR #181, `da15df97`).

## Goals / Non-Goals

**Goals:**

- Answers and judge calls can run at a fixed temperature and seed, set in the GUI, and every answer says what it sent.
- Know where the per-file ingest time goes, and remove it if it is waste.
- One harness for 35a with the four known bugs fixed.
- A re-install of the login item keeps the OCR variables.
- CI on `v3` stops failing at random on the two router tests.

**Non-Goals:**

- No pod run. Part C speeds and full-corpus token counts come from 35a's first timing step (D6).
- No change to Experiment 48's folder, gates or report numbers.
- No temperature or seed for metadata classification (a separate call path; metadata extraction is `disabled` in every 35a arm).
- No fix for #161 (needs an experiment) or #159 (no code path opens two OCR clients today; the 35a harness opens one).

## Decisions

### D1. Four settings, two per role, beside the reasoning levels

`answer.temperature`, `answer.seed`, `answer.verify_temperature`, `answer.verify_seed`, all optional (`None` = empty). Declared once in `core/answer/settings.py` and mirrored in the frozen `AnswerBlock`, as the reasoning levels are.

Alternatives: one shared pair for both roles (rejected: the judge and Chat are different models and the 35a judge is hosted with its own seed rule); a `sampling` sub-block (rejected: the reasoning pair already set the flat `verify_*` convention).

### D2. Provider mapping through the registry, no branching on names

Each provider module may export `sampling_kwargs(temperature, seed) -> dict | None` and the builder passes the result to the LLM constructor (`temperature=`) and `additional_kwargs` (`seed`). The registry gets `sampling_kwargs(name, ...)` and `ignored_sampling(name) -> set[str]`, like `reasoning_kwargs` and `ignores_reasoning`. Known mappings (verify each in the apply step against the provider's API docs through Context7):

| Provider | Temperature | Seed |
| --- | --- | --- |
| llamacpp | `temperature` | `seed` (llama-server) |
| openrouter | `temperature` | `seed` |
| openai_compatible | `temperature` | `seed` |
| ollama | `temperature` | `seed` (options) |
| anthropic | `temperature` | ignored (API has no seed) |

Empty values return nothing, so the constructor keeps its library default (spec: empty leaves the request unchanged).

### D3. Record what the request carried

The answer result gets a `sampling` record per role: `{"temperature": float | None, "seed": int | None}`. The value is read from the built LLM object after construction (its `temperature` attribute and `additional_kwargs`), so a library default is recorded as the number it is. Recording reads the object; it never re-derives the value from settings.

### D4. Shared harness in `experiments/_lib/`

New modules `experiments/_lib/ranking.py` (ranking and neighbour comparison, result-id and source matching), `experiments/_lib/timing.py` (timing rows, atomic writes) and `experiments/_lib/router_env.py` (GGUF folder and router config from the environment), each with its test file beside it. They start as copies of the Experiment 48 functions plus the four fixes, and keep the review lessons already in that code: blank result ids refused, empty comparisons reported as incomplete, a `--limit` smoke run never writes resumable outputs, tuple keys never used as JSON keys, `omrs.jsonc` values not beaten by stray environment overrides.

Alternative: patch Experiment 48 in place (rejected: breaks the frozen-folder rule and changes the code the PASS was measured with). Alternative: copy into the 35a folder (rejected: the next experiment would copy again).

### D5. Profile first, fix only what it shows

Profile one 200-file FreshStack ingest on the Mac with the Experiment 48 harness shape (one `ingest_path_async` call per file, local router, 4B, metadata `disabled`) under `cProfile` plus wall-clock spans around each ingest stage. Save the profile and a one-page summary to `~/Development/DATA/omrs/experiments/` and cite it in the PR. Likely candidates to check, not to assume: per-call collection open and store handle setup, BM25 cache rebuild after each write (gotcha 14), per-call settings resolution, router lease or readiness probes, and per-file tokenizer load. Then:

- if the cost is in OMRS, fix it in `core/` with a test that fails on the old behaviour, and add the requirement through `openspec-update-change` before the code;
- if the cost is only the harness calling per file, the shared harness ingests a folder in one call and records per-file timing from the ingest result instead.

Score each found cause with likelihood x impact. Below 4, propose an issue instead.

### D6. Part C speeds and token counts come from 35a, not a rerun

Experiment 48 tasks 4.3, 5.4 and 5.5 stay open in its archive. 35a's first timing step (on its own pod, before the freeze) records exact and fast speeds and the full-corpus token counts for FreshStack, BioASQ and FinanceBench. Master task 6.1 adds this to the 35a protocol. This change only states it.

### D7. Login item carries three named variables

`build_plan` reads the three variables from `os.environ`, else from the installed plist's `EnvironmentVariables`, and `render_plist` writes them beside `PATH`. The allow-list is a tuple constant in `_web_login_item.py`. Alternative: make the Indra folder an `omrs.jsonc` setting (ADR-087 single store). Rejected for now: it adds a setting, a GUI field and a migration for a path that only the live Mac uses; PR #176 already chose "OMRS finds its own libraries" for the other two. Revisit if a second machine needs it.

### D8. Flaky router tests

Two router tests failed once each in CI on `v3`: `test_llamacpp_router_download_failure.py::test_every_download_failing_ends_failed_with_one_attempt_per_model[plan]` (ubuntu, run 42509580109) and `test_llamacpp_router_readiness.py::test_changed_file_refused_and_others_serve` (macOS, run 42516121302, `IncompleteRead`). Diagnosis (2026-11-08, read-only subagent):

- Test 1 is a product race. A user Start sets a "waiting" flag (`transports/api/llamacpp_server.py:318`) and then reads status (`:228`). A fast-failing download calls `load()` (`router_autodownload.py:173`), which starts the router again (`llamacpp_server.py:390`) and clears the flag (`:295`). Nothing locks this state, so the Start reply can say `stopped` with no reason. Reproduced 5 of 5 with injected delays. It also caused run 42393529772. Score: likelihood 3 x impact 2 = 6. Fix: one re-entrant lock around `start`, `load`, `stop` and `status` in `RouterControl` (re-entrant because `load` calls `start`), with a delay-injected regression test.
- Test 2: the fake router sends headers and closes before the body. `integrations/llamacpp_runtime/process.py:183-186` catches only `OSError` and `ValueError`, so `http.client.IncompleteRead` escapes as a crash instead of "unreachable" `(0, {})`. Trigger not proven; likely `free_port()` in `tests/unit/test_llamacpp_router_worker.py:36-40` frees its port before the fake binds, and macOS hands ports out in order. Score: CI 5 x 2 = 10; product 2 x 3 = 6. Fix: catch `http.client.HTTPException` there (product), and let the fake bind port 0 and report its port (test).

### D9. RunPod machine for 35a (recommendation, no pod created)

Live catalogue reads on 2026-11-08 (`get-gpu-type`, `get-capacity`, secure cloud, pods product):

| GPU | Secure price | Floor vCPU | Floor RAM | Stock (data centres) |
| --- | ---: | ---: | ---: | --- |
| RTX 4090 24 GB | $0.89/h | 12 | 31 GB | Low (EU-CZ-1, EUR-IS-1, US-IL-1) |
| RTX 5090 32 GB | $1.19/h | 15 | 92 GB | Low (EU-RO-1, EUR-NO-1) |
| A40 48 GB | $0.59/h | 9 | 43 GB | High (CA-MTL-1), Low (EU-SE-1) |

Recommendation: **RTX 4090, secure cloud, $0.89/h, host CUDA 13.2, data centres EUR-IS-1 then EU-CZ-1 then US-IL-1, `minVcpuCountPerGpu: 16`, `minRamPerGpu: 64`, falling back to the 12-vCPU floor if no host matches.** Why:

- Same GPU, cloud and CUDA as both sweep pods (`aixzxy2y2h6zb9`, `3b3vfm9qez83fn`, 12 vCPU, about 100 GB RAM), so Part B timings carry over.
- `minVcpuCountPerGpu` is a placement filter, not a paid extra: the price stays $0.89/h, and the API returns the real count in `gpu.vcpuCount`. A create that finds no matching host fails without a charge, so trying 16 first costs nothing.
- More vCPUs help only if the work runs in parallel. The sweep showed single-core chunking and per-file overhead dominate. D5 decides whether ingest can use more cores; until then, 16 is a cheap hedge, not a promise of speed.
- RTX 5090 costs 34% more for 3 more floor vCPUs and a faster GPU the run does not need, and breaks timing carry-over. A40 is cheaper and in stock but its 9-vCPU floor is slower where it matters (CPU) and is a different GPU.
- The sweep's data centre (EUR-IS-2) shows no 4090 stock today; EUR-IS-1 is the nearest listed.

This also corrects the 35a protocol section 7, which still says 6 vCPU and 41 GB RAM (task 1.5, 2026-11-01). Master task 6.1 writes the amendment; stock and price are re-read live before any create.

## Risks / Trade-offs

- [The profile shows the time is spread thinly with no single cause] → record it, keep per-file ingest, and size 35a on the measured rate. No speculative optimisation.
- [A provider rejects `seed` (HTTP 400)] → the mapping test for each provider checks the request body; an apply-time check with Context7 confirms each API. A provider that rejects it is marked "ignores seed".
- [Changing the shared harness later shifts 35a after its freeze] → 35a's plan pins the commit; a later change to `_lib` needs a 35a amendment (existing rule).
- [Recording sampling values adds fields to answer results and the OpenAPI contract] → contract first; `additionalProperties: false` tests catch drift.
- [Carrying plist variables could carry a stale path] → `install` prints each carried variable and its source; the Integrations page already shows an OCR backend that is not ready.
