## Context

See proposal.md for the motivation. The current state that shapes the approach, checked in the code at `37096f6b`:

- **One address for two roles.** `core/metadata/llamacpp.py` sends classification to `{llamacpp_chat_url}/chat/completions` with `model: llamacpp_chat_model`. `core/metadata/llamaindex.py` calls `llm_registry.get(backend)(resolved, timeout=...)` with no `answer_model`, so `core/providers/llm/llamacpp.py` `build()` gives `OpenAILike(model=llamacpp_chat_model, api_base=llamacpp_chat_url)`.
- **Chat already has its own model.** `compose_answer.build_answer_llm` passes `answer_model=settings.answer.model`. `AnswerSettings.model` defaults to `"qwen3:4b"` with the provider `ollama`, so the value is a string, not `None`. Settings > Chat (`routes/chat_settings.py`, `web/src/settings/ChatSection.tsx`, `ChatModelForm.tsx`) saves `answer.provider` and `answer.model`.
- **The one silent fallback.** `compose_answer.build_verify_llm` passes `answer_model=(verify_model or None)`. For a llama.cpp judge with an empty `answer.verify_model`, `build()` then uses `llamacpp_chat_model`, the classification model. No other caller passes `None` for an answer role: the Chat test passes a checked model, and LlamaIndex classification passes nothing on purpose.
- **Gaps on the Chat path.** With the provider `llamacpp`, an empty `answer.model` reaches `OpenAILike(model="")`. `ChatModelForm.changeProvider` keeps the typed model when the provider changes, so `qwen3:4b` can be saved for llama.cpp. The Llama app router answers an unknown name with an error. A single-model `llama-server` does not read the `model` field of a request at all (llama.cpp server source, `post_chat_completions`; PR ggml-org/llama.cpp#17668 stopped echoing the name). So a wrong or empty name gets an answer from whatever model is loaded, with no sign.
- **Two model settings for one managed server.** The Local server panel saves `llamacpp_server_model` (ADR-084), which the owned `llama-server` loads with `-m` or `-hf`. Chat sends `answer.model` by name. For the reason above, the two can disagree with no sign. ADR-106 "Use this model" writes `llamacpp_server_model`.
- **Who runs the server is guessed.** `ModelDownloadDone.tsx` treats the server as OMRS's when the managed state is `running` or `starting`. `omrs web` does not start the managed server at launch (`owning_lifespan` only stops it), so after each launch the state is `stopped`.
- **Settings plumbing.** Provider addresses that apply live are listed once in `PROVIDER_ADDRESS_FIELDS` (`core/settings.py`). The server settings are listed in `PROVIDER_SERVER_FIELDS` (`config/provider_sources.py`) and `LLAMACPP_SERVER_FIELDS` (`core/providers/llm/llamacpp_rules.py`). `config/__init__.py` is at 468 lines and `core/settings.py` at 464, so new fields go in `ProviderSourceMixin`. The Configuration page may write every scalar setting that has no read-only reason (`config/settings_file_write.py`, ADR-095), with the `manage` scope only.
- **Index identity.** `core/ingestion/source_state.py` puts `llamacpp_chat_model` in `metadata_shape`, but no address.
- **The Llama app.** It runs a router on `127.0.0.1:9931` that picks a model per request by name. The context size of each model is `ctx-size` in `~/.config/llama/models.user.ini`, read only at app launch. A relaunch stops everything on 9931 for some seconds. OMRS never edits that file or signals the app (ADR-084, ADR-106). The app ships one program, `~/.llama-app/llama` (`llama serve`), which fails the ADR-084 program rule. Homebrew `llama.cpp` 0.8.0 gives `/opt/homebrew/bin/llama-server`, which a live check on 2026-10-29 used as the managed server.

## Goals / Non-Goals

**Goals:**

- Classification and Chat each have their own model and their own address on llama.cpp, with defaults that keep an existing install working.
- One place to set each value: the Text model and the classification address on the llama.cpp card or in `omrs.jsonc`, the Chat model in Settings > Chat.
- No path sends a role's request to another role's model without a sign.
- The user states who runs the Chat server, and the page shows the facts for that choice.

**Non-Goals:**

- No change to embeddings, Ollama, OpenRouter, the OpenAI-compatible or Anthropic providers, or the ADR-084 program rule.
- No edit of the Llama app's files and no signal to the app.
- No model list or editing of the Text model on the card. It stays read-only there. The Configuration page already writes it, with a restart, because it is part of the index identity.
- No managed server for classification. OMRS's server serves the Chat model only.
- No rename of `llamacpp_chat_model` or `llamacpp_chat_url`.

## Decisions

### D1. Key names: keep the old keys, add two, retire one

| Key (env) | Role | Default | Change |
| --- | --- | --- | --- |
| `llamacpp_chat_model` (`LLAMACPP_CHAT_MODEL`) | Text model (classification) | `""` | Label only |
| `llamacpp_chat_url` (`LLAMACPP_CHAT_URL`) | Chat address | `http://localhost:8081/v1` | None |
| `llamacpp_classify_url` (`LLAMACPP_CLASSIFY_URL`) | Classification address | `""`: use the Chat address | New |
| `llamacpp_chat_server` (`LLAMACPP_CHAT_SERVER`) | Who runs the Chat server: `external` or `managed` | `external` | New |
| `llamacpp_server_model` (`LLAMACPP_SERVER_MODEL`) | Model of OMRS's server | | Retired (D5) |

Keeping the two old keys means no legacy entry, no file migration and no index identity change. The names are not ideal, so the card labels and the guides carry the meaning.

*Alternative:* rename to `llamacpp_classify_model` and add both old names to `config/legacy.py`. Rejected: every existing install would fail at start-up for a label change, and the identity payload would change, so every collection would look stale.

### D2. The classification address follows the Chat address until set

`llamacpp_classify_url` is a plain field on `ProviderSourceMixin` with the default `""`. It joins `PROVIDER_ADDRESS_FIELDS`, so `EffectiveSettings` carries it, the Engine takes a change at once (ADR-083 decision 3), and `config/rules.py` `ADDRESS_FIELDS` checks it in `omrs.jsonc`. One pure function, `classification_url(settings)` in `core/providers/llm/llamacpp.py`, returns the field when it is not blank, else `llamacpp_chat_url`. Both classification paths and the card call it.

Sources follow ADR-087: the environment and `.env` set and lock it, `omrs.jsonc` sets it and does not lock it, else it follows the Chat address. The file never holds a blank value, because the writer reads blank as "remove the key". So "follows" is visible as the source `default`.

The provider descriptor gives the field `follows="chat_url"`. The card then shows the Chat address as the value in use and the line "Uses the Chat address until you set one." Changing the Chat address while classification follows it moves classification too. That line warns of it, and Edit opens with the current address, so one Save pins it.

*Alternative:* the default `http://localhost:8081/v1`, like the Chat address. Rejected: an install that set only `llamacpp_chat_url` (for example to the Llama app on 9931) would send classification to 8081 after the upgrade.

*Alternative:* a validator that copies the Chat address into the field. Rejected: the copy would look set, hide the source, and stop following a later live change.

### D3. Roles in the llama.cpp builder, and no fallback for an answer role

`core/providers/llm/llamacpp.py` `build()` keeps one signature for the registry:

- `answer_model is None` means classification: `api_base=classification_url(settings)`, `model=llamacpp_chat_model`. LlamaIndex classification keeps passing nothing.
- `answer_model` is a string means an answer role (Chat, judge, Chat test): `api_base=llamacpp_chat_url`, `model=answer_model`. A blank string raises `ValueError` before any request. This is a last guard; the callers below give the user-facing words.

The judge path is the only answer-role caller that passes `None`. `ConnectionDescriptor` gains `default_answer_model: bool = True`: whether the provider has a model setting of its own that an empty judge model may use. llama.cpp sets `False`, because its only model setting is the Text model. When the descriptor says `False` and the judge model is blank, `build_verify_llm` raises `ValueError("Choose a judge model in Settings > Chat.")` and builds nothing. The Engine already turns a judge build error into `verification_skipped` with the redacted text (`engine_answer.build_verifier`), so the skip reason names the missing judge model. OpenRouter and Ollama keep `None` and their documented default (`openrouter_llm_model`, `metadata.ollama_classify_model`).

`build_answer_llm` applies the same test to Chat: with a provider whose descriptor says `False` and a blank `answer.model`, it raises `ValueError("Choose a Chat model in Settings > Chat.")`. It lets a configuration error through on purpose, so the answer call reports it and sends nothing. `GET /v1/settings/chat` gives the reason `no-model` for a blank model, as the judge status already does (`judge_settings._reason`).

*Alternative:* a `role=` keyword on every provider `build()`. Rejected: it changes five providers to fix one.

*Alternative:* always pass `""` for an empty judge model. Rejected: it changes the documented OpenRouter and Ollama default (non-goal).

### D4. Who runs the Chat server is a saved setting

`llamacpp_chat_server` is `external` (default) or `managed`. It is a server setting beside the program, the window and the idle sleep. It is in `PROVIDER_SERVER_FIELDS` and in `LLAMACPP_SERVER_FIELDS`, saved by `PUT /v1/llamacpp/server` with the key `chat_server`, and shown by `GET /v1/llamacpp/server` with its source and lock. `config/rules.py` `ACCEPTED` holds the two names, so the file reader and `Settings` share one rule.

- `external`: OMRS starts nothing. `POST /v1/llamacpp/server/start` and `/restart` return 409 with the reason `external-server`. The card hides the Local server panel and shows the Llama app callout.
- `managed`: the card shows the Local server panel and the OMRS server callout. D5 applies.
- A change to `external` while the owned server is `starting` or `running` returns 409 with the reason `server-running`. The user stops the server first. A save never stops a server (ADR-084 decision 8).
- The change needs the `credentials` scope, the same as the program path. Choosing `managed` lets OMRS launch a program with the Chat model, and that model may have been saved under `manage` only while the choice was `external`.

*Recommendation, and why not derive it from the server state:* the state is `stopped` after every launch of `omrs web`, because nothing starts the server at launch. A derived choice would flip to "external" at each launch, the callouts would flip with it, and the save-time rules of D5 could not apply while the server is stopped. A saved choice is visible, has a source and a lock, and the routes can check it at save. ADR-106's state test in `ModelDownloadDone.tsx` changes to read this setting.

### D5. One Chat model: OMRS's server loads `answer.model`

When the choice is `managed`, the model of the owned server is the Chat model in force: `answer.model` when `answer.provider` is `llamacpp`. `llamacpp_server_model` is retired.

- **Launch.** `compose_llamacpp` builds `LaunchConfig.model` from the Chat choice. When the Chat provider is not `llamacpp`, or the model is blank, Start fails with `not-configured`. The model rule (`llamacpp_rules.model_kind`) runs before every launch, as today, so `qwen3:4b` fails with `model-invalid`. The argument list does not change.
- **Pending restart.** `pending_restart` compares the running model with the Chat model in force, so a Chat save while the server runs shows "Restart to apply".
- **Scope and rule at save.** While the choice is `managed`, a write that sets `answer.provider` to `llamacpp` or sets `answer.model` with that provider needs the `credentials` scope and must pass the model rule. 403 or 400 otherwise. This applies to `PUT /v1/settings/chat` and to `PUT /v1/settings/configuration`. A hand edit of `omrs.jsonc` is not checked at save; the launch check still applies.
- **Status.** `GET /v1/llamacpp/server` drops `saved.model` and gains `chat_model: {provider, model, usable}`, where `usable` means the provider is `llamacpp` and the model passes the rule. `ServerBody` keeps an optional `model` member only to refuse it: a body that holds it gets 400 with the message "Set the Chat model in Settings > Chat." A plain `extra="forbid"` refusal would give a generic validation message.
- **Use this model.** With the choice `managed`, the button after a llama.cpp download sends `PUT /v1/settings/chat` with `provider: "llamacpp"` and the downloaded value, then offers Restart. It needs `credentials`, as before. With `external`, the ADR-106 decision 4 panel stays: the cache folder and Refresh models, no Use this model. With `managed`, the button shows whatever the server state is; Restart stays disabled until the server runs.
- **Retirement.** `LLAMACPP_SERVER_MODEL` joins `_REMOVED_ENV_VARS` in `config/legacy.py`. A process that sees it in the environment or `.env` fails at start-up and names the replacement: `ANSWER__PROVIDER=llamacpp` and `ANSWER__MODEL`, with `LLAMACPP_CHAT_SERVER=managed`. This matches the removal of `OCR_WORKER_COMMAND`. A `llamacpp_server_model` key in `omrs.jsonc` is ignored and listed in the problem list with the replacement `answer.model`, so the server still starts (ADR-087: file problems do not stop the server). The old value is never read as the Chat model. `settings_handover.py` builds its rows from `LLAMACPP_SERVER_FIELDS`, so an old database row for the server model is no longer handed over. That affects only an install that skips every build since ADR-087.

*Why this rule:* the Chat model has one store, so drift cannot happen. The ADR-084 rules hold: the model rule at save and at launch, and the `credentials` scope for any change to what the owned server loads.

*Alternative:* keep both settings and refuse Save and Start when they differ. Rejected: the user types the same value twice, and a hand edit of either key blocks Start with no clear owner.

*Alternative:* keep `llamacpp_server_model` and derive the Chat model from it. Rejected: Settings > Chat is the home of the Chat model (user decision A), and a Chat model then lives in two places by provider.

*Alternative:* start the server with `--alias <answer.model>` so `/v1/models` lists the Chat name. Not needed: with D5 the server loads the Chat model by rule. It also adds a flag to the fixed argument list.

### D6. A shared address under OMRS's server warns and does not refuse

When the choice is `managed` and `classification_url(settings)` equals `llamacpp_chat_url` (compared after a trailing `/` is removed), classification goes to the owned server. That server loads one model and ignores the request name, so classification uses the Chat model. `GET /v1/llamacpp/server` gains `shared_with_classification: bool`. The card shows, in the Classification block and in the Local server panel: "Classification goes to OMRS's own Chat server, which loads only the Chat model. The Text model is not used. Set a Classification address, for example the Llama app, to keep them apart."

*Alternative:* refuse `managed` while the addresses are equal. Rejected: on a small machine one model for both roles can be a valid choice, and a refusal would block the user from it.

### D7. The Chat test checks the llama.cpp model list

`ConnectionDescriptor` gains `test_checks_model_list: bool = False`. llama.cpp sets `True`. When it is `True` and the choice is `external`, `POST /v1/settings/chat/test` first reads the provider's `models_target` (`{llamacpp_chat_url}/models`). When the list is readable and does not hold the model, the result is `ok: false` with the reason `model-not-listed`, and no prompt is sent. When the list cannot be read, the existing reasons apply (`refused`, `timeout`, `http-NNN`). With `managed`, the check is skipped, because the server loads the Chat model by rule.

The Chat form also empties the model name when the provider changes, so a name from another provider is not saved by accident. Save stays disabled until a model is typed or picked, and the field shows "Choose a model for this provider." The judge form uses the same component and gets the same rule.

### D8. The card shows three blocks from descriptor data

`ConnectionField` and `ReadOnlyValue` gain `group: Literal["embeddings", "metadata", "answers"] | None = None`. `ConnectionField` gains `follows: str | None = None` (D2). The llama.cpp descriptor sets:

| Group (title) | Editable fields | Read-only rows |
| --- | --- | --- |
| `embeddings` (Embeddings) | | Embedding address, Embedding model |
| `metadata` (Classification (metadata)) | Classification address (`follows="chat_url"`) | Text model (classification) |
| `answers` (Chat) | Chat address | |

`ProviderCard.tsx` renders the ungrouped fields first, then each group under its title, in the order above. No other provider sets a group, so other cards look as before. `PROVIDER_EXTRAS` maps a provider to `{group, Component}`. llama.cpp maps `answers` to `LlamacppChatBlock`, which shows:

1. The Chat model line from `GET /v1/settings/chat` and the display names in `GET /v1/connections`. With the provider `llamacpp`: a read-only row "Chat model" with `answer.model`. Otherwise: "Chat uses OpenRouter (deepseek/deepseek-v4-flash-0731)", built from the display name and the model. Both end with a link "Change in Settings > Chat" to `#settings-chat`. The card offers no model edit.
2. `ChatServerChoice`: a `Select` (primitive in `components/ui/`) labelled "Who runs the Chat server", with "The Llama app or another server you run" (`external`) and "OMRS's own llama-server" (`managed`), and the callout of the selected option (D9).
3. `LlamacppServerPanel` when the choice is `managed`, without the Model row, with a read-only Chat model row instead, and the D6 warning when it applies.

The Get a model panel stays at the end of the card. Each new or changed component stays under 200 lines; `ProviderCard.tsx` moves the group rendering into `ProviderFieldGroups.tsx`.

### D9. Callout text

The words live in one file, `web/src/settings/chatServerWords.ts`, so tests pin them.

- `external`: "Context size: set ctx-size for this model in the Llama app's models.user.ini, then relaunch the Llama app. The relaunch pauses embeddings and anything else on that port. OMRS does not edit this file or restart the app."
- `managed`: "OMRS's own server needs a program named exactly llama-server. The Llama app's own llama program does not qualify. Install one with Homebrew: brew install llama.cpp. Then set the program path, for example /opt/homebrew/bin/llama-server."

The `managed` callout shows while that option is selected, and again in the panel above the Program path row while the program path is not set or fails the program rule.

### D10. HTTP contract

No new operation, so `FAMILIES` in `tests/unit/test_web_openapi_conformance_support.py` keeps its ids. The schemas change, and the conformance tests must pass:

| Schema | Change |
| --- | --- |
| `ProviderField` | `group` (enum with `null`), `follows` (string or `null`) |
| `ProviderReadOnlyValue` | `group` |
| `ChatSettings.reason` | adds `no-model` |
| Chat test result `reason` pattern | adds `no-model` and `model-not-listed` |
| `LlamacppServerField.kind` | adds `choice` |
| `LlamacppServerStatus` | `saved` drops `model` and gains `chat_server`; adds `chat_model` and `shared_with_classification` |
| `SaveLlamacppServerRequest` | drops `model`, adds `chat_server` (enum `external`, `managed`, or `null` to clear) |
| `startLlamacppServer`, `restartLlamacppServer`, `saveLlamacppServer` | 409 with `reason` enum `external-server`, `server-running` |
| `setChatSettings`, `setSettingsConfiguration` | 403 when the D5 scope rule refuses |

Each 409 reason gets a plain line in a message map in `routes/llamacpp_server.py` and in the front-end words (`transports/api/AGENTS.md` rule 4).

### D11. The Configuration page cannot bypass the scopes

`llamacpp_chat_server` joins `READ_ONLY_KEYS` in `config/settings_file_write.py` with the reason "Set this on the llama.cpp card." `PUT /v1/settings/configuration` applies the D5 rule to `answer.provider` and `answer.model`: while the choice is `managed`, it needs the `credentials` scope and the model rule for a llama.cpp Chat choice.

### D12. Runtime list and readiness

`transports/api/runtime_servers.py` lists a third llama.cpp item, "llama.cpp classification server", only when `classification_url(settings)` differs from `llamacpp_chat_url`. The metadata user (`metadata_llm_provider`) then moves to that item. When the addresses are equal, the Chat item keeps both users, as today. `llamacpp_readiness` includes the classification address. `_test_targets` in `llamacpp.py` adds `{classification_url}/models` and keeps the list free of duplicates.

### D13. ADR-108

`docs/adr/108-local-chat-and-classification-stay-apart.md` records D1 to D9 and D11 with the status Proposed. It amends ADR-084 decision 4 (the four settings: the model setting goes, the Chat server choice comes in) and ADR-106 decision 4 (the saved choice, not the server state, decides who runs the Chat server, and Use this model saves the Chat model). Short "Amended by ADR-108" lines go on both. ADR-084 decision 5 (the program rule, the model rule and the `credentials` scope) stays as it is and now covers the Chat model while the choice is `managed`.

## Risks / Trade-offs

- [Changing the Chat address moves classification while it follows] → The follow line on the field (D2), the upgrade note, and Edit opens with the current address.
- [An install that used OMRS's server loses its saved model at upgrade] → The problem list names the old key and its replacement. The upgrade note gives three steps: choose `managed`, choose llama.cpp in Settings > Chat, paste the old value as the Chat model.
- [`LLAMACPP_SERVER_MODEL` in `.env` stops start-up] → The message names the replacement. This follows the `OCR_WORKER_COMMAND` precedent. The commented line in `.env.example` changes.
- [A user who used OMRS's server only for classification loses that] → A non-goal. The Classification address can point at any server the user runs. ADR-108 records the trade-off.
- [The Llama app router with `--models-max 1` reloads a model when Chat and classification use different models on 9931] → The point of the change is to move Chat to another server. The guide says so.
- [The model-list check fails a single-model server started with `-m <path>` when the user typed a Hugging Face id] → That is the honest result: Chat would get the loaded model, not the typed one. The sentence says to pick the name with List models.
- [A shared address under `managed` makes the Text model unused] → D6 warning in two places.
- [The Configuration page already writes `llamacpp_server_binary` with `manage` only, which skips the ADR-084 `credentials` rule. The program rule still runs at every launch.] → Out of scope. Likelihood 2, impact 2: below 5, so it is a proposed issue, not a fix here.

## Migration Plan

| Before the upgrade | After the upgrade |
| --- | --- |
| `llamacpp_chat_url` set, no classification address | Classification uses the same address and the same Text model. |
| `llamacpp_chat_model` set | Only the label changes. The index identity is the same, so no re-ingest. |
| Chat on llama.cpp with a model, server run by the user | No change. The default choice is `external`. |
| Chat on llama.cpp with a blank `answer.model` | Chat refuses with "Choose a Chat model". Before, the server answered with the model it had loaded. |
| llama.cpp judge with a blank `answer.verify_model` | The claim check is skipped with a reason that names the missing judge model. Before, it used the Text model. |
| `llamacpp_server_model` in `omrs.jsonc` | Ignored and listed in the problem list. The Local server panel hides until the user chooses `managed`. |
| `LLAMACPP_SERVER_MODEL` in the environment or `.env` | Start-up fails and names the replacement. |

The guide gets an "Upgrade notes" entry with these rows. The release commit uses `feat:`, as the `OCR_WORKER_COMMAND` removal did (see Open Questions). Rollback is a revert of the merge commit. The older build ignores `llamacpp_classify_url` and `llamacpp_chat_server` and lists them as unknown keys. It reads `llamacpp_server_model` again if the user kept it.

## Open Questions

- The release type. Removing `LLAMACPP_SERVER_MODEL` can stop start-up, which is breaking in the strict sense. The project released the `OCR_WORKER_COMMAND` removal as `feat:`. The plan follows that precedent; the maintainer can choose `feat!:` at commit time without a change to the plan.
- Whether the live `~/.config/omrs/omrs.jsonc` holds `llamacpp_server_model`. Agents do not read that folder. The answer changes only the user's own upgrade steps.
- The Ollama judge has the same kind of fallback: an empty `answer.verify_model` uses `metadata.ollama_classify_model`. It is out of scope (non-goal: no Ollama change). Proposed issue: likelihood 2 (claim checks are off by default and the default judge is cloud), impact 4 (a small classification model judges claims with no sign), score 8.
