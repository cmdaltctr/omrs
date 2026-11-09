# Design: pre-Experiment-35 fixes

## Context

- Experiment 48 is closed (PASS). Its report lists the gaps this change closes: no answer temperature or seed (known difference), about 0.88 s per file of unexplained ingest time (Part B), harness bugs scored 3 or below, and missing Part C speeds and token counts (D1, D5).
- `answer.reasoning` and `answer.verify_reasoning` already flow from settings through `compose_answer._level()` as a `reasoning=` keyword to each provider's `build()`, which maps it with its own module-level `reasoning_kwargs` (spec `answer-reasoning-and-usage`). OpenRouter and OpenAI-compatible put the result in `additional_kwargs`; Ollama passes it to the constructor as `thinking=`; llama.cpp and Anthropic ignore it. The registry's `reasoning_kwargs(name, level)` has no caller; only `ignores_reasoning` is used (`routes/chat_reasoning.py`). Chat reads its values from `Settings.answer`; the judge (`build_verify_llm`) reads them from the `AnswerBlock`. Temperature and seed follow the same path.
- LlamaIndex's OpenAI classes default to `temperature: 0.1` and put it on every request (`OpenAI._get_model_kwargs()`, inherited by `OpenAILike`; checked 2026-11-08). So "no setting" today means 0.1 on llama.cpp, OpenRouter and OpenAI-compatible, not "no temperature". LlamaIndex `Ollama` defaults to `None`, so the Ollama server uses the model's own default. The Anthropic default was not checked (package not installed in the dev environment).
- `experiments/CLAUDE.md`: in a finished experiment only `experiment.json`, `protocol.md` and the report may change. The Experiment 48 harness files are therefore frozen.
- Issue #175: PR #176 (merged 2026-11-05) made the `pp-ocrv6-small` backend set `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` itself in every process. What is left is `INDRA_OCR_MODEL_DIR`: the live login item has it by hand, and `omrs web install` drops it (`render_plist` writes only `PATH`).
- The claim check today: `verify_claims()` in `core/answer/verify.py` builds one chat prompt per claim, sends it through a `CompletionSeam` (prompt to reply text) and reads the last word `supported` or `unsupported`. The seam comes from `compose_answer.build_verify_llm` and `engine_answer.build_verifier`. No registry of judge strategies exists: `answer.verify_provider` names an LLM provider, not a way of judging. Decision models (`core/providers/decision/`, ADR-074, ADR-103) already call `/v1/systemone` for OCR page decisions through a registry of kinds, with the 8-bit check (root gotcha 16).
- Issue #177 was closed on 2026-11-08 (fixed by `b62605f8`, then by the router change). Issue #180 was closed (fixed by PR #181, `da15df97`).

## Goals / Non-Goals

**Goals:**

- Answers and judge calls can run at a fixed temperature and seed, set in the GUI, and every answer says what it sent.
- Know where the per-file ingest time goes, and remove it if it is waste.
- One harness for 35a with the four known bugs fixed.
- A re-install of the login item keeps `INDRA_OCR_MODEL_DIR`.
- Two typed claim judges (Clef-Flash 9B, Granite Guardian 3.3 8B) register beside the chat judge, and every judge call records what produced the verdict.
- OMRS refuses, or records, an OpenRouter host that drops `seed`.
- One pre-freeze pod session with a written plan, and the 35a model matrix fixed in one place.
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

Following the reasoning precedent, `compose_answer.py` passes `temperature=` and `seed=` keywords to each provider's `build()`, and each provider module maps them with its own `sampling_kwargs(temperature, seed) -> dict | None`. The mapping is per provider, not one generic split: OpenRouter and OpenAI-compatible already fill `additional_kwargs` with the reasoning field, so the seed must merge with it; LlamaIndex `Ollama` merges `additional_kwargs` into `options`. The registry gets `ignored_sampling(name) -> set[str]`, like `ignores_reasoning`. Known mappings (verify each in the apply step against the provider's API docs through Context7):

| Provider | Temperature | Seed |
| --- | --- | --- |
| llamacpp | `temperature` | `seed` (llama-server) |
| openrouter | `temperature` | `seed` |
| openai_compatible | `temperature` | `seed` |
| ollama | `temperature` | `seed` (options) |
| anthropic | ignored (current Claude models do not use sampling values; checked in task 1.1) | ignored (API has no seed) |

Empty values return nothing, so the constructor keeps its library default (spec: empty leaves the request unchanged).

Checked in task 1.1 (2026-11-08, Context7): llama-server takes `temperature` (0 = greedy) and `seed` (-1 = random) in the request; OpenRouter takes `temperature` (0 to 2) and `seed` (integer); OpenAI takes `seed` as best effort (Beta, watch `system_fingerprint`); Ollama `/api/chat` takes both in `options`. The Anthropic Python SDK has removed `temperature`, `top_p` and `top_k` from its message methods because current models do not use them, so `anthropic` maps neither value and reports both as ignored (no model argument in the registry). In code the shared `constructor_kwargs` (`core/providers/llm/sampling.py`) puts the temperature on the constructor and the seed in `additional_kwargs`; each provider module binds it as its own `sampling_kwargs`, so a provider without the attribute reports both values ignored.

Notes from the review (2026-11-08): llama.cpp holds the seed as an unsigned 32-bit number and `-1` means random, so the 0 to 2^31 - 1 range fits. OpenAI marks `seed` as best effort. On OpenRouter the seed reaches the model only if the serving host supports it: a public read of `deepseek/deepseek-v4.1-flash-1017` endpoints showed several hosts without `seed`, including the cheapest (Relace, fp4).

### D3. Record what the request carried

The answer result gets a `sampling` record per role (`sampling.chat`, and `sampling.judge` when the judge ran): `{"temperature": float | None, "seed": int | None, "host": str | None, "accepted": {"temperature": bool, "seed": bool} | None, "host_in_list": bool | None}`. `host_in_list` is `false` when the serving host is outside the allowed list (the mismatch D11 step 3 reports) and `None` when no list is set. A client-sampled answer has no `chat` record, because OMRS sees no request. Temperature and seed are read from the built LLM object after construction (its `temperature` attribute and `additional_kwargs`), so a library default is recorded as the number it is. Recording reads the object; it never re-derives the value from settings. `host` and `accepted` say what the serving host did (D11): `host` is the host the reply names, `accepted` is that host's published support for each value the request set, and both are `None` when the provider does not report them.

### D4. Shared harness in `experiments/_lib/`

New modules `experiments/_lib/ranking.py` (ranking and neighbour comparison, result-id and source matching), `experiments/_lib/timing.py` (timing rows, atomic writes) and `experiments/_lib/router_env.py` (GGUF folder and router config from the environment), each with a test file under `tests/` (for example `tests/test_experiment_lib_ranking.py`), as the existing `_lib` tests are. pytest collects only `testpaths = ["tests"]`, so a test beside the module would not run in CI or count in the tripwire. They start as copies of the Experiment 48 functions plus the four fixes, and keep the review lessons already in that code: blank result ids refused, empty comparisons reported as incomplete, a `--limit` smoke run never writes resumable outputs, tuple keys never used as JSON keys, `omrs.jsonc` values not beaten by stray environment overrides.

Alternative: patch Experiment 48 in place (rejected: breaks the frozen-folder rule and changes the code the PASS was measured with). Alternative: copy into the 35a folder (rejected: the next experiment would copy again).

### D5. Profile first, fix only what it shows

Profile one 200-file FreshStack ingest on the Mac with the Experiment 48 harness shape (one `ingest_path_async` call per file, local router, 4B, metadata `disabled`) under `cProfile` plus wall-clock spans around each ingest stage. Save the profile and a one-page summary to `~/Development/DATA/omrs/experiments/` and cite it in the PR. Likely candidates to check, not to assume: per-call collection open and store handle setup, BM25 cache rebuild after each write (gotcha 14), per-call settings resolution, router lease or readiness probes, and per-file tokenizer load. Then:

- if the cost is in OMRS, fix it in `core/` with a test that fails on the old behaviour, and add the requirement through `openspec-update-change` before the code;
- if the cost is only the harness calling per file, the shared harness ingests a folder in one call and records per-file timing from the ingest result instead.

Score each found cause with likelihood x impact. Below 4, propose an issue instead.

**Follow-up (task 2.1 done; profile in `~/Development/DATA/omrs/experiments/pre-exp35-ingest-profile-2026-11-08/`).** On the Mac, 200 files, the whole call takes 0.849 s per file and 75% of it is the embedding request. Three causes sit in OMRS:

- Markdown splitter rebuilt for every document (`core/chunking/model_token.py`, about 0.085 s of the 0.108 s chunking time per file). Likelihood 10 x impact 3 = 30. Fix: one splitter per tokenizer, capacity and overlap, reused (task 2.3; spec `markdown-aware-chunking`). The chunks do not change.
- Magika started as a separate program for each `ingest_path_async` call (0.071 s per file). Likelihood 10 x impact 2 = 20. Not fixed here. ADR-068 decisions 2 and 6 keep one subprocess transport on purpose (the injected `MAGIKA_BINARY`, model life cycle outside the process) and list the Python API as a rejected option. A change needs a new ADR that supersedes those decisions, so it goes to the operator as an issue.
- The LanceDB store opens the collection about 12 times and runs `count_where` 3 times per file (0.006 s and 0.012 s). Likelihood 10 x impact 1 = 10. Not fixed here. The opens come from five modules under `core/vectordb/lancedb/`, and a cached table handle would need a refresh rule that keeps the cross-process cache check of root gotcha 14. That is not a small local change for about 4 ms per file, so it goes to the operator as an issue.

The Mac does not reproduce the pod's 0.79 s of fixed work before embedding; it stays open for the D13 pod session.

### D6. Part C speeds and token counts come from the pre-freeze session, not a rerun

Experiment 48 tasks 4.3, 5.4 and 5.5 stay open in its archive. The one pre-freeze session (D13) records exact and fast speeds and the full-corpus token counts for FreshStack, BioASQ and FinanceBench, as 35a's first timing step. It replaces the second pod that an earlier draft of this design put before the freeze. Master task 6.1 adds this to the 35a protocol. This change only states it.

### D7. Login item carries one named variable, and the file is split

`build_plan` reads `INDRA_OCR_MODEL_DIR` from `os.environ`, else from the installed plist's `EnvironmentVariables`, and `render_plist` writes it beside `PATH`. The allow-list is a tuple constant in `_web_login_item.py` (one entry; a tuple keeps the "named variables only" rule explicit). `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` stay out: PR #176 made the `pp-ocrv6-small` backend find those libraries in every process, so they only matter when an operator wants to beat the bundled copy, and no one has asked. Alternative: make the Indra folder an `omrs.jsonc` setting (ADR-087 single store). Rejected for now: it adds a setting, a GUI field and a migration for a path that only the live Mac uses. Revisit if a second machine needs it.

`transports/cli/web_login_item.py` is 493 lines, so the printed "carried" lines would push it over the 500-line ceiling (`tests/test_file_size_ceiling.py`). Task 4.2 moves the status helpers (`_installed_plan`, `_read_link`, `_current_port` and the body of `status`) into a new `_web_login_item_status.py`, as the settings and stop text already sit in `_web_login_item_settings.py` and `_web_login_item_stop.py`. Test patch targets follow the function (root gotcha 8b), so patches of the moved names change module in the same task.

### D8. Flaky router tests

Two router tests failed once each in CI on `v3`: `test_llamacpp_router_download_failure.py::test_every_download_failing_ends_failed_with_one_attempt_per_model[plan]` (ubuntu, run 42509580109) and `test_llamacpp_router_readiness.py::test_changed_file_refused_and_others_serve` (macOS, run 42516121302, `IncompleteRead`). Diagnosis (2026-11-08, read-only subagent):

- Test 1 is a product race. A user Start sets a "waiting" flag (`transports/api/llamacpp_server.py:318`) and then reads status (`:228`). A fast-failing download calls `load()` (`router_autodownload.py:173`), which starts the router again (`llamacpp_server.py:390`) and clears the flag (`:295`). Nothing locks this state, so the Start reply can say `stopped` with no reason. Reproduced 5 of 5 with injected delays. It also caused run 42393529772. Score: likelihood 3 x impact 2 = 6. Fix: one re-entrant lock around `start`, `load`, `stop` and `status` in `RouterControl` (re-entrant because `load` calls `start`), with a delay-injected regression test.
- Test 2: the fake router sends headers and closes before the body. `integrations/llamacpp_runtime/process.py:181-187` catches only `OSError` and `ValueError`, so `http.client.IncompleteRead` escapes as a crash instead of "unreachable" `(0, {})`. Trigger not proven; likely `free_port()` in `tests/unit/test_llamacpp_router_worker.py:36-40` frees its port before the fake binds, and macOS hands ports out in order. Score: CI 5 x 2 = 10; product 2 x 3 = 6. Fix: catch `http.client.HTTPException` there (product), and let the fake bind port 0 and report its port (test).

### D9. RunPod machine for 35a (recommendation, no pod created)

Live catalogue reads on 2026-11-08 (`get-gpu-type`, `get-capacity`, secure cloud, pods product):

| GPU | Secure price | Floor vCPU | Floor RAM | Stock (data centres) |
| --- | ---: | ---: | ---: | --- |
| RTX 4090 24 GB | $0.89/h | 12 | 31 GB | Low (EU-CZ-1, EUR-IS-1, US-IL-1) |
| RTX 5090 32 GB | $1.19/h | 15 | 92 GB | Low (EU-RO-1, EUR-NO-1) |
| A40 48 GB | $0.59/h | 9 | 43 GB | High (CA-MTL-1), Low (EU-SE-1) |

Recommendation: **RTX 4090, secure cloud, $0.89/h, host CUDA 13.2, data centres EUR-IS-1 then EU-CZ-1 then US-IL-1, `minVcpuCountPerGpu: 16`, `minRamPerGpu: 64`, falling back to the 12-vCPU floor if no host matches.** Why:

- Same GPU, cloud and CUDA as both sweep pods (`aixzxy2y2h6zb9`, `3b3vfm9qez83fn`, 12 vCPU; pod RAM is not in the Experiment 48 records), so Part B timings carry over.
- `minVcpuCountPerGpu` is a placement filter, not a paid extra: the price stays $0.89/h, and the API returns the real count in `gpu.vcpuCount`. A create that finds no matching host fails without a charge, so trying 16 first costs nothing.
- More vCPUs help only if the work runs in parallel. The sweep showed single-core chunking and per-file overhead dominate. D5 decides whether ingest can use more cores; until then, 16 is a cheap hedge, not a promise of speed.
- RTX 5090 costs 34% more for 3 more floor vCPUs and a faster GPU the run does not need, and breaks timing carry-over. A40 is cheaper and in stock but its 9-vCPU floor is slower where it matters (CPU) and is a different GPU.
- The sweep's data centre (EUR-IS-2) showed no 4090 stock in the first read; EUR-IS-1 was the nearest listed. A review re-read later on 2026-11-08 (`get-gpu-type`, secure, pods) gave the same price and floors ($0.89/h, 12 vCPU, 31 GB, CUDA 13.2) but stock Low in EU-RO-1, EUR-IS-2 and US-IL-1 only. Stock moves within hours, so pick the data-centre order from the live read at create time, and prefer EUR-IS-2 when it has stock.

This also corrects the 35a protocol section 7, which still says 6 vCPU and 41 GB RAM (task 1.5, 2026-11-01). Master task 6.1 writes the amendment; stock and price are re-read live before any create.

### D10. Claim-judge strategies in a small registry

A new package `core/answer/judges/` holds a `ClaimJudge` protocol (`judge(claim, evidence_texts)` returns a verdict and a call record), a registry (`registry.py`, same shape as `core/providers/decision/registry.py`: `register`, `get`, `names`) and one file per strategy. Rules from `core/AGENTS.md` apply: a new strategy is one file plus one `register()` line, and the dispatch code never imports a strategy module at module level or branches on names. `verify_claims()` takes a `ClaimJudge` instead of a raw seam. The claim splitter, the evidence handling and the aggregate outcome stay as they are.

| Strategy | What it does | Prompt format version | Role in 35a |
| --- | --- | --- | --- |
| `chat` | Today's behaviour: chat prompt, one-word reply, last word wins. Wraps the existing seam, prompt and parser unchanged. Serves GLM-5.3. | `chat-oneword/1` | Confirmation panel (GLM-5.3) |
| `clef_flash` | One `noul` question on `/v1/systemone` through the decision adapter (`llamacpp` kind, router lease, Q8_0 check from `core/providers/decision/checks.py`). Claim and evidence go in `state.text`. P(yes) at or above 0.5 means `supported`. P(yes) is kept in the call record. | `clef-flash-claim/1` | Main checker, every claim, every arm |
| `granite_guardian` | The guardian prompt through the llama.cpp router: criterion `groundedness`, evidence as the template's `documents`, claim as the only message (role `assistant`), thinking off. OMRS renders the prompt from the model's own chat template and sends it to `/v1/completions` (see the card check below). Guardian answers yes when the risk is present, so `yes` means `unsupported`. | `granite-guardian-3.3-groundedness/1` | Confirmation panel |

**Card check (task 8.1, 2026-11-08, read with the Hugging Face tools, no download).** These points correct the table above and the spec:

1. Granite Guardian 3.3 8B (`ibm-granite/granite-guardian-3.3-8b`, `chat_template.jinja`): the template takes three arguments, `guardian_config` (`{"criteria_id": "groundedness"}`), `documents` (a list of `{doc_id, text}`, rendered as `document` turns before the messages) and `think` (default false, which renders the `judge{no_think}` turn). The groundedness example in the card sends the claim as the only message, with role `assistant`; the scoring line reads the role of the last message. Evidence therefore goes in `documents`, not in a context message.
2. The guardian replies `<score> yes </score>` or `<score> no </score>`. Thinking adds a `<think>...</think>` trace first. OMRS reads the last `<score>` tag; a reply without one is `unparseable`. The card's example runs at temperature 0, so the strategy sends temperature 0 unless `answer.verify_temperature` is set.
3. llama-server takes extra template arguments per request as `chat_template_kwargs` (Jinja is on by default). Its default `--prefill-assistant` treats a request whose last message is an assistant message as a prefill: it drops that message from the template and appends it after the generation prompt, so the guardian judge turn is never rendered. The router preset allow-list has no key to turn this off. The strategy therefore renders the prompt itself, the same text the template renders for `groundedness` with thinking off, and sends it to `/v1/completions`. The prompt-format version pins this rendering.
4. Clef-Flash (`Cloudflare/clef-flash`): a `noul` answer is the probability of true; its two options are true and false, each with an optional `criteria` text. The question id is the key and `instructions` is optional. The state can be text or JSON. P(yes) in this design means that probability. The strategy reuses the decision adapter unchanged: question id `fidelity`, the claim question as `instructions`, the claim and evidence in `state.text`.
5. GGUF builds: `ggml-org/Clef-Flash-GGUF` has Q8_0, BF16 and Q4_K_M (the 8-bit check refuses Q4_K_M); `ibm-granite/granite-guardian-3.3-8b-GGUF` has Q8_0 and f16 beside Q4_K_M, Q5_K_M and Q6_K. Use the Q8_0 file of each.

- **Where it is built.** A strategy module receives its transport as an injected callable, as the chat seam is today, and imports no provider. The router lease and the decision adapter are reached only from the composition root, so construction goes in a new `compose_judges.py` (`compose_answer.py` is 307 lines and keeps its size). The import-linter contract `providers-constructed-only-in-compose` stays satisfied.
- **Which strategy runs.** New setting `answer.verify_judge`, default `chat` (no behaviour change). It is profile-overlaid like the other `verify_*` values and validated at startup against `names()` (same fail-fast rule as `verify_provider`). For `clef_flash` and `granite_guardian`, `answer.verify_provider` is `llamacpp` and `answer.verify_model` names the router model. The 35a harness builds the confirmation panel by building several judges from copies of the answer block, one per strategy, so the panel needs no extra setting. The 200-claim seeded sample belongs to the 35a protocol, not to OMRS.
- **Per-profile choice in Studio (user decision 2026-11-08).** `answer.verify_judge` is also a Studio lever, so one profile can use `clef_flash` while another keeps `chat`. Its options come from the registry through the server catalogue; a strategy whose model is not set up on this host is shown as not ready and is refused at save. The judge's model settings stay host-owned, as today.
- **What each call records.** Per call: strategy, model id, host or GGUF file SHA-256, prompt-format version and the settings the call used (temperature, seed, reasoning, threshold, and Granite's think flag). A local file's SHA-256 is read from the router state (`hashes.json`, ADR-115); a hosted call records the host the reply names. The answer result carries them as `judge_calls`, one entry per claim. Logs hold fixed reasons and counts only, never claim or evidence text.
- **Failure.** A judge that cannot start or fails its Q8_0 check reports `verification_skipped` with a fixed reason and sends no claim request. An unreadable reply counts as `unparseable` for that claim, never as a pass; a run where every reply is unreadable reports `verification_skipped`, as today. A local request that fails for one claim (the router or the model cannot serve) gives that claim `unparseable` with a fixed `error` in its call record; when every claim fails with the same error, the run reports `verification_skipped` naming it.
- **Threshold.** 0.5 for `clef_flash` is the starting value. The D13 full-split run shows whether the leaderboard scoring matches it. The final value goes in the 35a protocol before the freeze. It is not a setting (no configurability nobody asked for).
- **Fallback (handover 2026-11-08).** If Clef-Flash misses the D13 pass rule, GLM-5.3 on the `chat` strategy becomes the main checker with its own full-split number. The strategy stays registered.

Alternatives: reuse `verify_provider` with a "decision" provider (rejected: the provider registry builds LlamaIndex chat objects, and a decision model has no chat interface); send Clef-Flash through the chat path (rejected by the operator: wrong interface); a plug-in entry point for judges (rejected: not needed until a third party writes one).

### D11. Allowed OpenRouter hosts and the host record

`answer.allowed_hosts` (Chat) and `answer.verify_allowed_hosts` (judge) hold OpenRouter host names, separated by commas, in `omrs.jsonc` (ADR-087; env `ANSWER__ALLOWED_HOSTS` and `ANSWER__VERIFY_ALLOWED_HOSTS`). Empty keeps today's request. Both are shown on the Chat and Judge panels beside temperature and seed, with the lock state. Only OpenRouter reads them; other providers report them in the "ignored by this provider" note, like a seed they cannot take.

When a list is set on OpenRouter:

1. The request body gains `provider: {"only": [hosts], "allow_fallbacks": false, "require_parameters": true}` (merged into the same `extra_body` as the reasoning field, D2). `require_parameters` makes OpenRouter skip a host that lacks a field the request sets. Verify the three field names in task 7.1 with Context7 before code. Checked in task 7.1 (2026-11-08): the names are right, and OpenRouter documents `only` entries as provider slugs (as the model page copies them, for example `fireworks` or `deepinfra/fp8`), so the Settings note asks for slugs; OMRS sends the list as typed.
2. Before the first call of a role in a process, OMRS reads the model's endpoint list (`GET /api/v1/models/{author}/{slug}/endpoints`, each entry with `provider_name`, `tag` (the endpoint slug) and `supported_parameters`; the docs list the bearer key as required, so OMRS sends the OpenRouter key to openrouter.ai only). A host matches by provider name in any case or by slug, as OpenRouter matches `only` (`deepinfra` matches `deepinfra/fp8`). The temperature counts as set when the library default (0.1) goes on the request. The list read goes through an injected fetch callable, and a parsed list is kept in process memory; a failed read is not kept. If no allowed host lists every value the request sets (`temperature`, `seed`), OMRS makes no call and refuses with a message that names the model, the hosts and the missing values. On the answer path that is an error result; on the judge path it is `verification_skipped`.
3. The reply names the host that served it in its top-level `provider` field (seen in the recorded 2026-10-23 reply and the OpenRouter debug example; the formal response schema does not list it). The `sampling` record keeps that host and that host's published support for temperature and seed (D3). A host outside the list, or one that lacks a set value, is recorded as such and is a test failure, not a pass.

Why a list and not "refuse any host without seed": the operator picks the hosts once from a live read (35a freeze), and the record then proves the call used one of them. Alternative: always set `require_parameters` with no list (rejected: it hides which host served, and the cheapest host that does take `seed` can change between runs; the list pins the choice). Score from the review: likelihood 7 x impact 6 = 42, so this is fixed in this change.

### D12. Experiment 35a model matrix

Fixed 2026-11-08 (gate G-A). Master task 6.1 copies this table into the 35a plan.

| Role | Model | Settings | Runs on | Evidence |
| --- | --- | --- | --- | --- |
| Answers, every arm that uses an API | `deepseek/deepseek-v4.1-flash-1017` | temperature 0, fixed seed, host pinned by `answer.allowed_hosts` to one that honours `seed` | OpenRouter | Experiment 35 design D3 |
| Main Ragas judge | `openai/gpt-oss-120b` | reasoning `low`, temperature 0, seed, host pinned to one that honours `seed` | OpenRouter, from the 35a harness | Judge's Verdict (arXiv 2510.09738): kappa 0.756, human-like tier |
| Ragas cross-check on 50 hand-checked items | `openai/gpt-6.1-terra` | fixed seed (that route takes no temperature) | OpenRouter, from the 35a harness | Cross-family check of the main judge |
| OMRS claim check, main, every claim in every arm | Clef-Flash 9B, `ggml-org/Clef-Flash-GGUF:Q8_0`, strategy `clef_flash` | threshold per D10 | Local on the pod, through the OMRS router | LLM-AggreFact leaderboard average 76.6, RAGTruth 83.2 (read live 2026-11-08). The model card's "RAGTruth 35.6" is hallucination F1 on its own Decision Index, a different measure. Do not mix the two. |
| Claim-check confirmation, seeded sample of about 200 claims per arm | GLM-5.3 via Z.AI direct, strategy `chat`, reasoning `low` set explicitly (default is max and thinking cannot be off), temperature 0 | as listed | Z.AI API | Experiment 20 judge |
| Claim-check confirmation, same sample | IBM Granite Guardian 3.3 8B, `ibm-granite/granite-guardian-3.3-8b-GGUF`, strategy `granite_guardian` | groundedness criterion | Local on the pod, through the OMRS router, after Clef-Flash | Apache-2.0, granite architecture, LLM-AggreFact 76.5, RAGTruth 82.2 |
| Embeddings | Qwen3-Embedding | none | Local | Embeds only. No judging role. |
| Metadata extraction | off | `disabled` in every 35a arm | n/a | Operator, 2026-11-08 |

**Family rule.** The earlier rule "no judge shares a family with any answer model" is replaced. Same-family checking is allowed and measured. Clef-Flash is Qwen3.5-9B based and one arm uses Qwen3-8B answers. Self-preference is a known judge bias (Panickssery, Bowman and Feng 2024, arXiv 2404.13076; Li et al. 2025, "Preference Leakage", arXiv 2502.01534). Per arm, the 35a report states Clef-Flash agreement with GLM-5.3, with Granite, and with both. The 35a protocol fixes a margin before the run. If an arm's agreement falls by more than that margin, that arm's faithfulness is reported with the panel verdicts beside the Clef-Flash verdicts.

**Rejected, not to be reopened.** Gemini as judge (cost about $236). gpt-4o-mini as judge (not human-like tier). Local Qwen3-8B as claim checker. GLM-5.3 as main Ragas judge. Nemotron 3 Super as claim checker (no published agreement). Clef-Flash through the chat path (wrong interface).

### D13. One pre-freeze RunPod session

Replaces the two pre-freeze pods of the earlier draft. Shape as 35a: secure cloud, RTX 4090 (D9). Pick the data centre from a live `get-gpu-type` and `get-capacity` read at create time. Quote the hourly price and wait for the operator's go before `create-pod`. Chain every step pod-side, copy the outputs back, delete the pod at once. Never end a turn while the pod runs. Start only after this change is merged (the session uses the judges, the host pin and the shared harness).

Steps, in order:

1. Part C timing step (D6): exact and fast speeds and full-corpus token counts for FreshStack, BioASQ and FinanceBench.
2. The 20-answer measurement: 20 real answers plus their Ragas judging through the 35a harness; record tokens, time, and the host that served each call (D11).
3. Full LLM-AggreFact test split (`lytang/LLM-AggreFact`, `test`, 29.3K rows) on Clef-Flash, then on Granite Guardian 3.3 8B, one after the other through the router. VRAM on 24 GB: Clef-Flash about 10 GB, Granite about 9 GB, the 4B embedder about 4.5 GB, so the two judges never load together. Time the first 200 items and report the ETA; run the full set even past 2 hours. Score as the leaderboard does: balanced accuracy per dataset, then the plain mean.
4. Pass rule, per model: the average and the RAGTruth value each within 1 point of the published value (Clef-Flash 76.6 and 83.2; Granite 76.5 and 82.2). The items are the same as the leaderboard's, so only quantisation and prompt can differ.

Outside the pod:

5. GLM-5.3 runs the same full split through the Z.AI API from the Mac (about $11), so the paper has its number.
6. Experiment 20's 120 claim triples run again on GLM-5.3 at reasoning `low` (Experiment 20 left reasoning at the host default). Keep `low` if unsupported recall is 0.95 or more and false rejection is 0.05 or less. Otherwise use `high` and re-price.

5. Arm smoke run, after steps 3 and 4 pass. Run every 35a arm end to end on a fixed, seeded set of 5 questions per dataset: ingest, retrieval, answer, Ragas judging, and the claim check through all three judge strategies (`clef_flash`, `granite_guardian`, `chat` with GLM-5.3). Run each arm twice. Pass rule: zero errors; every claim has a verdict from each strategy; every call record has model id, host or file SHA-256, prompt-format version and settings; the second run gives the same verdicts and the same ranked ids. A failure stops the session and goes to the operator. Nothing in 35a is frozen until this step passes.

Dataset terms: the set is gated (the operator has accepted the terms) and licensed CC-BY-ND-4.0. Use it for evaluation only, never publish a changed copy, and keep it out of git (store under `~/Development/DATA/omrs/`, with its SHA-256 in `DATA_LOCATIONS.md`). If Clef-Flash misses step 4, D10's fallback applies. If Granite misses step 4, the 35a report drops it from the panel and says why; the operator decides whether to replace it.

## Risks / Trade-offs

- [The profile shows the time is spread thinly with no single cause] → record it, keep per-file ingest, and size 35a on the measured rate. No speculative optimisation.
- [A provider rejects `seed` (HTTP 400)] → the mapping test for each provider checks the request body; an apply-time check with Context7 confirms each API. A provider that rejects it is marked "ignores seed".
- [Changing the shared harness later shifts 35a after its freeze] → 35a's plan pins the commit; a later change to `_lib` needs a 35a amendment (existing rule).
- [Recording sampling values adds fields to answer results and the OpenAPI contract] → contract first. The Chat and Judge settings schemas set `additionalProperties: false`, so their tests catch drift. `AnswerResponse` (`openapi.yaml:7133`) does not, and it already omits `usage` and `reasoning` (both are added to the result in `engine_answer.py`). Task 1.5 adds `sampling`, `judge_calls`, `usage` and `reasoning` there, sets `additionalProperties: false`, and a test checks every key the result builders and `engine_answer.py` emit against the declared properties.
- [`AnswerBlock` drifts from `AnswerSettings`] → today only `AnswerBlock(**settings.answer.model_dump())` guards the mirror (`test_provider_symmetry.py:191`), and a field missing on the block fails only at runtime. Task 1.2 adds a test that the two models hold the same field names, as the Metadata pair has.
- [Clef-Flash scored on the leaderboard with a question wording we do not have] → the card gives no prompt (it shows state plus typed questions). D13 step 3 is the test: within 1 point on the full split or D10's fallback applies. The wording is pinned as `clef-flash-claim/1`.
- [Granite's yes means "risk present", which is easy to invert] → a test per direction (`yes` gives `unsupported`, `no` gives `supported`) and a mutation check that flips the mapping.
- [A host list that names a host the model does not use] → OMRS refuses before the call and names the hosts the endpoint list shows. No silent fallback.
- [The endpoint list changes shape] → any unexpected shape gives "support unknown", the call is refused when a list is set, and the message says why.
- [Carrying a plist variable could carry a stale path] → `install` prints the carried variable and its source; the Integrations page already shows an OCR backend that is not ready.
