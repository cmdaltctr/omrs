# claim-judge-strategies Specification

## Purpose

Let the operator choose how OMRS checks each cited claim against its evidence, through a small registry of claim-judge strategies, and keep a record of what produced every verdict.

## Requirements

### Requirement: Claim-judge strategies come from a registry

The claim check SHALL take its judge from a registry of strategies in `core/answer/judges/`. A strategy SHALL be one file plus one `register()` line. The code that picks a strategy SHALL NOT import a strategy module at module level and SHALL NOT branch on strategy names. This change SHALL register `chat`, `clef_flash` and `granite_guardian`. An unknown name SHALL be refused at startup with a message that names the registered strategies.

#### Scenario: Unknown strategy

- **WHEN** `answer.verify_judge` is `foo`
- **THEN** startup MUST fail with a message that names `chat`, `clef_flash` and `granite_guardian`

#### Scenario: Adding a strategy

- **WHEN** a test registers a fourth strategy in a scratch registry
- **THEN** the claim check MUST run it with no change to the dispatch code

### Requirement: The setting defaults to today's judge

The setting `answer.verify_judge` SHALL default to `chat`. With `chat` selected, the claim check SHALL send the same prompt, read the reply the same way and give the same verdicts as before this change. The setting SHALL resolve through the normal source order (ADR-087) with `ANSWER__VERIFY_JUDGE` as its environment name, SHALL be shown on the Judge panel with its lock state, and SHALL follow the profile overlay of the other `verify_*` values.

#### Scenario: Default unchanged

- **WHEN** `answer.verify_judge` is empty and a claim check runs
- **THEN** the judge prompt, the reply parsing and the verdicts MUST equal those of the previous release for the same replies

### Requirement: Clef-Flash judges a claim through the decision interface

The `clef_flash` strategy SHALL send one yes/no (`noul`) question per claim to `/v1/systemone` through the decision adapter, with the claim and its cited evidence as the state, and SHALL read P(yes) (probability of true). A P(yes) of 0.5 or more SHALL give `supported`. A lower value SHALL give `unsupported`. A reply without a usable P(yes) SHALL give `unparseable`. The strategy SHALL run only on a model that passes the 8-bit check of root gotcha 16, and SHALL NOT use the chat interface.

#### Scenario: Supported claim

- **WHEN** the model returns P(yes) 0.92 for a claim
- **THEN** the verdict MUST be `supported` and the call record MUST hold 0.92

#### Scenario: Unsupported claim

- **WHEN** the model returns P(yes) 0.12
- **THEN** the verdict MUST be `unsupported`

#### Scenario: Malformed reply

- **WHEN** the reply lacks the answer
- **THEN** the verdict MUST be `unparseable`, and the claim MUST count as not supported

#### Scenario: Model below 8-bit

- **WHEN** the named model file is a 4-bit build
- **THEN** no claim request MUST be sent and the answer MUST report `verification_skipped` with the fixed reason of the check

### Requirement: Granite Guardian judges a claim by groundedness

The `granite_guardian` strategy SHALL send the guardian prompt with the criterion `groundedness`, the cited evidence as the template's documents and the claim as the only message (role `assistant`), with thinking off. It SHALL render the prompt as the model's chat template does and send it to the router's `/v1/completions` (design D10). It SHALL read the last `<score>` tag. A `yes` (risk present) SHALL give `unsupported`, a `no` SHALL give `supported`, and neither SHALL give `unparseable`.

#### Scenario: Prompt from the model's template

- **WHEN** the strategy judges one claim with two evidence texts
- **THEN** the request MUST go to `/v1/completions` with two `document` turns, the claim as the `assistant` turn, the groundedness criterion and the `judge{no_think}` turn

#### Scenario: Risk present

- **WHEN** the guardian replies `yes` for a claim
- **THEN** the verdict MUST be `unsupported`

#### Scenario: No risk

- **WHEN** the guardian replies `no`
- **THEN** the verdict MUST be `supported`

#### Scenario: Unreadable reply

- **WHEN** the reply holds neither word
- **THEN** the verdict MUST be `unparseable`

### Requirement: Every judge call records what produced the verdict

The answer result SHALL hold a `judge_calls` list with one entry per judged claim. Each entry SHALL hold the strategy, the model id, the host for a hosted call or the SHA-256 of the GGUF file for a local call, the prompt-format version, the settings of the call (temperature, seed, reasoning, threshold and, for Granite, the think flag), P(yes) for a decision model, and a fixed `error` reason when the request for that claim failed.

#### Scenario: Local call

- **WHEN** `clef_flash` judges a claim on a router model whose file hash is known
- **THEN** the entry MUST hold strategy `clef_flash`, the model id, that SHA-256, version `clef-flash-claim/1` and P(yes)

#### Scenario: Hosted call

- **WHEN** the `chat` strategy judges a claim on OpenRouter and the reply names host `Z.AI`
- **THEN** the entry MUST hold strategy `chat`, the model id, host `Z.AI`, version `chat-oneword/1` and the temperature and seed of the call

### Requirement: The judge record holds no claim text and versions its prompt

A `judge_calls` entry MUST NOT hold the claim text, the evidence text or a key. The prompt-format version SHALL change whenever a strategy changes its prompt or its reading of the reply.

#### Scenario: No claim text in the record

- **WHEN** a result holding `judge_calls` is serialised
- **THEN** no entry MUST contain the claim text or any evidence text

### Requirement: A judge that cannot run degrades the answer check only

A judge that cannot start, fails its model check, or raises SHALL give `verification_skipped` with a fixed reason. The answer SHALL still be returned. An `unparseable` verdict SHALL NOT count as a pass.

#### Scenario: Router not reachable

- **WHEN** `answer.verify_judge` is `clef_flash` and the router does not start
- **THEN** the answer MUST be returned with `verification_skipped` naming a fixed reason and no claim text

### Requirement: A profile can choose its judge in Studio

Studio SHALL offer `answer.verify_judge` as a profile lever beside Check claims. The options SHALL come from the judge registry. A save SHALL be refused, with a plain message, when the name is unknown or the strategy's model is not set up on this host.

#### Scenario: Profile picks Clef-Flash

- **WHEN** a user profile sets `answer.verify_judge` to `clef_flash` and the router lists the Clef-Flash model
- **THEN** Studio saves the override and claim checks for collections on that profile use `clef_flash`
- **AND** other profiles keep their own judge

#### Scenario: Strategy not ready on this host

- **WHEN** a user picks `granite_guardian` and no Granite model is set up
- **THEN** Studio shows the option as not ready
- **AND** the save is refused with a message that names the missing model setting
