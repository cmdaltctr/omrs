# ADR-108: Local Chat and Classification Stay Apart

- **Date:** 2026-10-29
- **Status:** Proposed
- **Deciders:** Maintainer
- **Amends:** [ADR-084](084-context-windows-and-an-owned-llama-server.md) (decision 4, the server settings: the model setting goes and the Chat server choice comes in), [ADR-106](106-app-searches-and-downloads-local-models.md) (decision 4, who runs the Chat server and what Use this model saves)
- **Related:** [ADR-083](083-llm-provider-settings-in-the-web-workspace.md) (provider addresses apply live), [ADR-087](087-settings-live-in-omrg-jsonc.md) (source order), [ADR-095](095-page-writes-every-scalar-setting.md) (the Configuration page writes scalar settings), [ADR-059](059-claim-verification-stage.md) (the claim check judge)
- **Change:** `openspec/changes/separate-local-chat-and-classification/` (design D1 to D13)

## Context

llama.cpp serves two text roles in OMRS. Classification (metadata extraction) uses `llamacpp_chat_model`. Chat uses `answer.model`, which Settings > Chat saves. Both roles send requests to one address, `llamacpp_chat_url`. These facts, checked in the code at `37096f6b`, shape the decision:

- **One address for two roles.** Classification cannot stay on the Llama app (port 9931) while Chat moves to the `llama-server` that OMRS runs (ADR-084).
- **A misleading label.** The llama.cpp card labels the classification model "Chat model". Users think that it answers Chat.
- **A single-model server ignores the request name.** A `llama-server` that loads one model does not read the `model` field of a request (llama.cpp server source, `post_chat_completions`; PR ggml-org/llama.cpp#17668 stopped echoing the name). A wrong or empty name gets an answer from the loaded model, with no sign.
- **Two model settings for one managed server.** The owned server loads `llamacpp_server_model` (ADR-084). Chat sends `answer.model` by name. The two can disagree with no sign. ADR-106 Use this model writes `llamacpp_server_model`.
- **One silent fallback.** A llama.cpp claim check judge with an empty `answer.verify_model` uses `llamacpp_chat_model`, the classification model.
- **Gaps on the Chat path.** An empty `answer.model` with the provider `llamacpp` reaches the server as `model=""`. The Chat form keeps the typed model when the provider changes, so the Ollama default `qwen3:4b` can be saved for llama.cpp.
- **Who runs the server is guessed.** The Get a model panel treats the server as OMRS's when its state is `running` or `starting`. `omrs web` does not start the managed server at launch, so the state is `stopped` after each launch.
- **The Llama app.** It runs a router on `127.0.0.1:9931` that picks a model per request by name. The context size of each model is `ctx-size` in `~/.config/llama/models.user.ini`, read only at app launch. A relaunch stops everything on that port for some seconds. The app ships one program, `~/.llama-app/llama`, which fails the ADR-084 program rule. Homebrew `llama.cpp` gives `/opt/homebrew/bin/llama-server`.

If nothing changes, a user cannot keep classification on the Llama app and move Chat to OMRS's server. Requests can reach the wrong model, and nothing on the page shows it.

## Decision

1. **Keep the old keys, add two, retire one** (D1).

   | Key (env) | Role | Default | Change |
   | --- | --- | --- | --- |
   | `llamacpp_chat_model` (`LLAMACPP_CHAT_MODEL`) | Text model (classification) | `""` | Label only |
   | `llamacpp_chat_url` (`LLAMACPP_CHAT_URL`) | Chat address | `http://localhost:8081/v1` | None |
   | `llamacpp_classify_url` (`LLAMACPP_CLASSIFY_URL`) | Classification address | `""`: use the Chat address | New |
   | `llamacpp_chat_server` (`LLAMACPP_CHAT_SERVER`) | Who runs the Chat server: `external` or `managed` | `external` | New |
   | `llamacpp_server_model` (`LLAMACPP_SERVER_MODEL`) | Model of OMRS's server | | Retired (decision 5) |

   The old keys stay, so there is no legacy entry, no file migration and no change to the index identity. The card labels and the guides carry the meaning of the names.

2. **The classification address follows the Chat address until a source sets it** (D2). `llamacpp_classify_url` is a plain provider address with the default `""`. It joins `PROVIDER_ADDRESS_FIELDS`, so the Engine takes a change at once (ADR-083 decision 3), and the file reader checks it with the other addresses. One pure function, `classification_url(settings)` in `core/providers/llm/llamacpp.py`, returns the field when it is not blank, else `llamacpp_chat_url`. Both classification paths (direct chat completions and the LlamaIndex extractors) and the card call it. Sources follow ADR-087: the environment and `.env` set and lock it, `omrs.jsonc` sets it and does not lock it, else it follows the Chat address. The file never holds a blank value, so "follows" shows as the source `default`. The descriptor marks the field `follows="chat_url"`. The card shows the Chat address as the value in use with the line "Uses the Chat address until you set one."

3. **The llama.cpp builder has two roles, and an answer role never falls back** (D3). `build()` keeps one signature for the registry:
   - `answer_model is None` means classification: the classification address and `llamacpp_chat_model`. LlamaIndex classification keeps passing nothing.
   - A string means an answer role (Chat, judge, Chat test): the Chat address and that model. A blank string raises `ValueError` before any request.

   `ConnectionDescriptor` gains `default_answer_model: bool = True`. It says whether the provider has a model setting of its own that an empty judge model may use. llama.cpp sets `False`, because its only model setting is the Text model. With `False`:
   - A blank judge model makes `build_verify_llm` raise "Choose a judge model in Settings > Chat." The Engine already turns a judge build error into `verification_skipped`, so the skip reason names the missing judge model.
   - A blank Chat model makes `build_answer_llm` raise "Choose a Chat model in Settings > Chat." The answer call reports it and sends nothing. `GET /v1/settings/chat` gives the reason `no-model`.

   OpenRouter and Ollama keep `None` for an empty judge model and their documented defaults.

4. **Who runs the Chat server is a saved setting** (D4). `llamacpp_chat_server` is `external` (the Llama app or another server you run, the default) or `managed` (OMRS's own `llama-server`). It is a server setting beside the program, the window and the idle sleep. `PUT /v1/llamacpp/server` saves it with the key `chat_server`, and `GET /v1/llamacpp/server` shows it with its source and lock.
   - `external`: OMRS starts nothing. Start and Restart return 409 with the reason `external-server`. The card hides the Local server panel.
   - `managed`: the card shows the Local server panel. Decision 5 applies.
   - A change to `external` while the owned server is `starting` or `running` returns 409 with the reason `server-running`. The user stops the server first. A save never stops a server (ADR-084 decision 8).
   - A change needs the `credentials` scope. `managed` lets OMRS launch a program with the Chat model, and that model may have been saved under `manage` only while the choice was `external`.

   The choice is not derived from the server state. The state is `stopped` after every launch of `omrs web`, so a derived choice would flip to "external" at each launch, and the save-time rules of decision 5 could not apply while the server is stopped. A saved choice is visible, has a source and a lock, and the routes can check it at save.

5. **OMRS's server loads the Chat model** (D5). With `managed`, the model of the owned server is the Chat model in force: `answer.model` while `answer.provider` is `llamacpp`. `llamacpp_server_model` is retired.
   - **Launch.** Start fails with `not-configured` when the Chat provider is not `llamacpp` or the model is blank. The model rule (`llamacpp_rules.model_kind`) runs before every launch, so `qwen3:4b` fails with `model-invalid`. The argument list does not change.
   - **Pending restart.** The status compares the running model with the Chat model in force, so a Chat save while the server runs shows "Restart to apply".
   - **Scope and rule at save.** While the choice is `managed`, a write that sets `answer.provider` to `llamacpp`, or sets `answer.model` with that provider, needs the `credentials` scope and must pass the model rule: 403 or 400 otherwise. This applies to `PUT /v1/settings/chat` and `PUT /v1/settings/configuration`. A hand edit of `omrs.jsonc` is not checked at save; the launch check still applies.
   - **Status.** `GET /v1/llamacpp/server` drops `saved.model` and gains `chat_model: {provider, model, usable}` and `shared_with_classification`. A save body that holds `model` gets 400 with "Set the Chat model in Settings > Chat."
   - **Use this model.** With `managed`, the button after a llama.cpp download saves the downloaded value as the Chat model with the provider `llamacpp` (`PUT /v1/settings/chat`, `credentials` scope), then offers Restart. The button shows in every server state; Restart stays disabled until the server runs. With `external`, ADR-106 decision 4 stays: the cache folder and Refresh models, no Use this model.
   - **Retirement.** `LLAMACPP_SERVER_MODEL` in the environment or `.env` stops start-up, and the message names the replacement: `ANSWER__PROVIDER=llamacpp` and `ANSWER__MODEL`, with `LLAMACPP_CHAT_SERVER=managed`. This follows the removal of `OCR_WORKER_COMMAND` (ADR-105). A `llamacpp_server_model` key in `omrs.jsonc` is ignored and listed in the problem list with the replacement `answer.model`, so the server still starts. The old value never becomes the Chat model. The settings handover no longer hands over an old database row for the server model.

   The Chat model has one store, so the server model and the Chat model cannot drift. The ADR-084 rules hold: the model rule at save and at launch, and the `credentials` scope for any change to what the owned server loads.

6. **A shared address under OMRS's server warns and does not refuse** (D6). When the choice is `managed` and `classification_url(settings)` equals `llamacpp_chat_url` (compared after a trailing `/` is removed), classification goes to the owned server. That server loads one model and ignores the request name, so classification uses the Chat model. `shared_with_classification` is then true. The Classification block and the Local server panel show: "Classification goes to OMRS's own Chat server, which loads only the Chat model. The Text model is not used. Set a Classification address, for example the Llama app, to keep them apart." On a small machine, one model for both roles can be a valid choice, so OMRS does not refuse it.

7. **Each Chat server choice shows a fixed callout** (D9). The words live in one front-end file, so tests pin them.
   - `external`: "Context size: set ctx-size for this model in the Llama app's models.user.ini, then relaunch the Llama app. The relaunch pauses embeddings and anything else on that port. OMRS does not edit this file or restart the app."
   - `managed`: "OMRS's own server needs a program named exactly llama-server. The Llama app's own llama program does not qualify. Install one with Homebrew: brew install llama.cpp. Then set the program path, for example /opt/homebrew/bin/llama-server."

   The `managed` callout shows while that option is selected. It shows again in the Local server panel above the Program path row while the program path is not set or fails the program rule.

8. **The Configuration page cannot bypass the scopes** (D11). `llamacpp_chat_server` is read-only on the Configuration page with the reason "Set this on the llama.cpp card." `PUT /v1/settings/configuration` applies the rule of decision 5 to `answer.provider` and `answer.model`: while the choice is `managed`, a llama.cpp Chat choice needs the `credentials` scope and the model rule.

ADR-084 decision 5 (the program rule, the model rule and the `credentials` scope) does not change. It now covers the Chat model while the choice is `managed`.

## Consequences

### Positive

- Classification can stay on the Llama app while Chat runs on OMRS's own `llama-server`, each with its own model and address.
- Each value has one place to set it: the Text model and the classification address on the llama.cpp card or in `omrs.jsonc`, the Chat model in Settings > Chat.
- No llama.cpp path sends one role's request to another role's model without a sign. An empty Chat model or judge model gives a reason that names it.
- The owned server always loads the Chat model, so the server model and the Chat model cannot disagree.
- An existing install keeps working: classification follows the Chat address, the default choice is `external`, and the index identity does not change.

### Negative

- While classification follows the Chat address, a change of the Chat address moves classification too. The follow line on the field and the upgrade note warn of it. Edit opens with the current address, so one Save pins it.
- An install that used OMRS's server loses its saved model at upgrade. The problem list names the old key and its replacement. The upgrade note gives three steps: choose `managed`, choose llama.cpp in Settings > Chat, paste the old value as the Chat model.
- `LLAMACPP_SERVER_MODEL` in `.env` stops start-up. The message names the replacement. This follows the `OCR_WORKER_COMMAND` precedent.
- A user who used OMRS's server only for classification loses that. A managed server for classification is a non-goal. The classification address can point at any server that the user runs.
- The Llama app router with `--models-max 1` reloads a model when Chat and classification use different models on port 9931. The point of this change is to move Chat to another server, and the guide says so.
- The Chat test model-list check (design D7) fails a single-model server started with `-m <path>` when the user typed a Hugging Face id. That is the honest result: Chat would get the loaded model, not the typed one. The line tells the user to pick the name with List models.
- With a shared address under `managed`, the Text model is not used. The warning of decision 6 shows in two places.

### Neutral

- The names `llamacpp_chat_model` and `llamacpp_chat_url` are not ideal. The labels "Text model (classification)" and "Chat address" carry the meaning.
- The Configuration page already writes `llamacpp_server_binary` with `manage` only, which skips the ADR-084 `credentials` rule. The program rule still runs at every launch. Proposed issue, out of scope: likelihood 2, impact 2, score 4.
- The Ollama judge has the same kind of fallback: an empty `answer.verify_model` uses `metadata.ollama_classify_model`. It is out of scope, because this change makes no Ollama change. Proposed issue: likelihood 2 (claim checks are off by default and the default judge is cloud), impact 4 (a small classification model judges claims with no sign), score 8.
- Rollback is a revert of the merge commit. The older build ignores `llamacpp_classify_url` and `llamacpp_chat_server` and lists them as unknown keys. It reads `llamacpp_server_model` again if the user kept it.
- The release type is open. The removal of `LLAMACPP_SERVER_MODEL` can stop start-up. The plan follows the `feat:` precedent of the `OCR_WORKER_COMMAND` removal; the maintainer can choose `feat!:` at commit time.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Rename to `llamacpp_classify_model` and add the old name to `config/legacy.py`** | Every existing install would fail at start-up for a label change. The identity payload would change, so every collection would look stale. |
| **Default the classification address to `http://localhost:8081/v1`** | An install that set only `llamacpp_chat_url`, for example to the Llama app on 9931, would send classification to 8081 after the upgrade. |
| **A validator that copies the Chat address into the classification address** | The copy would look set, hide the source and stop following a later live change. |
| **A `role=` keyword on every provider `build()`** | It changes five providers to fix one. |
| **Always pass `""` for an empty judge model** | It changes the documented OpenRouter and Ollama defaults, which is a non-goal. |
| **Derive who runs the server from its state** | The state is `stopped` after every launch, so the choice and its callouts would flip, and the save-time rules could not apply while the server is stopped. |
| **Keep both model settings and refuse Save and Start when they differ** | The user types the same value twice, and a hand edit of either key blocks Start with no clear owner. |
| **Keep `llamacpp_server_model` and derive the Chat model from it** | Settings > Chat is the home of the Chat model. The Chat model would then live in two places, by provider. |
| **Start the server with `--alias <answer.model>`** | Not needed: the server loads the Chat model by rule. It also adds a flag to the fixed argument list. |
| **Refuse `managed` while the two addresses are equal** | One model for both roles can be a valid choice on a small machine. A refusal would block it. |
| **Do nothing** | Classification and Chat stay on one address, and requests can reach the wrong model with no sign. |

## Verification

Checked on 2026-10-29 on branch `feat/separate-local-chat-and-classification`.

1. **Tests.** Each guard has a test that failed before the code change. A mutation check broke each guard once, and a test failed each time. Local CI passed: 9,511 Python tests, 2,237 Vitest tests, tripwire 5 of 5, strict validation of 90 items. No step printed `SKIPPED`.
2. **Review.** An open-code-review of 44 source files gave 6 findings. One scored 5 or more: the shared-address warning stayed stale after a Classification address save (score 12). It is fixed, test first. The other five are proposed issues in `review.md`.
3. **Live checks.** Classification reached the Llama app on 9931. OMRS's own Homebrew `llama-server` on a scratch port loaded the Chat model and answered Chat, and it got no classification request. The Chat test gave `model-not-listed` for `qwen3:4b` against the Llama app.
4. **Browser check.** Screenshots at 1280 px and 390 px show the three blocks, both callouts, the OpenRouter line and the shared-address warning. Nothing scrolls sideways at 390 px. See TDR-042 for how the check ran without Chrome.
5. **Two additions, at the maintainer's request.** An empty Ollama Chat or judge model is refused too, so `metadata.ollama_classify_model` never answers or judges (design D14). The Configuration page now asks for the `credentials` scope and the program rule for `llamacpp_server_binary` (design D15).
6. **Build findings.** `classification_url` lives in `core/settings.py`, because `core/metadata` may not import `core/providers`. The workspace table's field list stays frozen at ADR-087, so the handover skips the new fields. The `omrs.jsonc` writer has one card-only key, `llamacpp_chat_server`, that only the llama.cpp card route may write.
7. **Release.** `feat:` (minor), as the maintainer chose.

## References

- `openspec/changes/separate-local-chat-and-classification/design.md` (D1 to D13, Risks, Migration Plan), `specs/llamacpp-server/spec.md`, `specs/llm-provider-settings/spec.md`, `specs/metadata-extraction/spec.md`, `specs/grounded-answer-synthesis/spec.md`, `specs/workspace-settings/spec.md`, `specs/model-downloads/spec.md`, `specs/runtime-components/spec.md`
- `src/omrs/core/providers/llm/llamacpp.py` (builder roles, `classification_url`, card groups), `src/omrs/core/providers/llm/connection.py` (descriptor fields)
- `src/omrs/core/metadata/llamacpp.py`, `src/omrs/core/metadata/llamaindex.py` (classification paths)
- `src/omrs/compose_answer.py` (Chat and judge without a default model), `src/omrs/compose_llamacpp.py` (server view and launch model)
- `src/omrs/config/provider_sources.py`, `src/omrs/config/legacy.py`, `src/omrs/config/settings_file_write.py` (settings, retired key, read-only key)
- `src/omrs/transports/api/routes/llamacpp_server.py`, `src/omrs/transports/api/routes/chat_settings.py`, `src/omrs/transports/api/routes/configuration.py`, `src/omrs/transports/api/openapi.yaml`
- `docs/guides/configuration.md` (Upgrade notes), `docs/guides/web-workspace.md`, `docs/guides/providers.md`, `docs/guides/metadata-extraction.md`
- [ADR-084](084-context-windows-and-an-owned-llama-server.md), [ADR-106](106-app-searches-and-downloads-local-models.md), [ADR-105](105-pipeline-steps-own-their-ocr-settings.md) (the `OCR_WORKER_COMMAND` removal precedent)
