# answer-sampling Specification

## Purpose

Let the operator fix the temperature, seed and OpenRouter hosts that OMRS uses for the Chat model and the claim judge, so answers can repeat, and record what each request carried and which host served it.

## Requirements

### Requirement: Temperature and seed are settings for each role

The `answer` settings block SHALL hold `temperature` and `seed` for the Chat model, and `verify_temperature` and `verify_seed` for the claim judge. Each SHALL be empty or a value: a temperature from 0 to 2, a seed a whole number from 0 to 2^31 - 1. The settings SHALL resolve through the normal source order (ADR-087), with `ANSWER__TEMPERATURE`, `ANSWER__SEED`, `ANSWER__VERIFY_TEMPERATURE` and `ANSWER__VERIFY_SEED` as their environment names.

#### Scenario: Values read from omrs.jsonc

- **WHEN** `omrs.jsonc` sets `answer.temperature` to `0` and `answer.seed` to `20261101`
- **THEN** the effective settings MUST hold temperature 0 and seed 20261101 for the Chat role, and the judge values MUST stay empty

#### Scenario: Out-of-range value refused

- **WHEN** a save sets `answer.temperature` to `3` or `answer.seed` to `-1`
- **THEN** the server MUST refuse the save with 400 and MUST NOT change the setting

### Requirement: An empty value leaves the request unchanged

An empty temperature or seed SHALL leave the request exactly as OMRS built it before this change. No new field SHALL be added and no library default SHALL be removed.

#### Scenario: Empty settings keep the current request

- **WHEN** all four values are empty and an answer runs on OpenRouter
- **THEN** the request MUST carry the same temperature as before this change and MUST NOT carry a `seed` field

### Requirement: A set value goes on every request for its role

A set temperature or seed SHALL go to the provider on every completion request for its role, through the provider registry. The provider SHALL map it to its own request field. The Chat values SHALL NOT reach judge requests, and the judge values SHALL NOT reach Chat requests.

#### Scenario: Chat values sent on every round

- **WHEN** `answer.temperature` is `0`, `answer.seed` is `20261101`, and an answer on llama.cpp takes two synthesis rounds
- **THEN** both completion requests MUST carry `temperature: 0` and `seed: 20261101`

#### Scenario: Judge values are separate

- **WHEN** `answer.verify_claims` is true, `answer.seed` is `7` and `answer.verify_seed` is empty
- **THEN** claim-judge requests MUST NOT carry the seed 7, and Chat requests MUST carry it

### Requirement: A provider that cannot take a value says so

A provider with no mapping for temperature or seed SHALL send nothing for that value, and the Chat and Judge settings reads SHALL report which values the provider ignores. The Settings page SHALL show that note beside the value.

#### Scenario: Provider without a seed

- **WHEN** the Chat provider is `anthropic` and `answer.seed` is `20261101`
- **THEN** the request MUST NOT carry a seed or a temperature, and `GET /v1/settings/chat` MUST report that the provider ignores both

### Requirement: Settings shows and saves the values

The Chat panel SHALL show and save `answer.temperature`, `answer.seed` and `answer.allowed_hosts`. The Judge panel SHALL show and save `answer.verify_temperature`, `answer.verify_seed` and `answer.verify_allowed_hosts`. Saves SHALL write `omrs.jsonc` with the revision check, as the other Chat and Judge values do. A value locked by `env` or `dotenv` SHALL show as locked and SHALL NOT be saved.

#### Scenario: Save from the Chat panel

- **WHEN** the operator sets temperature 0 and seed 20261101 on the Chat panel and saves
- **THEN** `omrs.jsonc` MUST hold `answer.temperature: 0` and `answer.seed: 20261101`, and the next answer MUST send them

#### Scenario: Locked value

- **WHEN** `ANSWER__SEED` is set in the process environment
- **THEN** the Chat panel MUST show the seed as locked and a save of the seed MUST be refused with 409

### Requirement: Each answer records what its requests carried

Each answer result SHALL hold a `sampling` record that gives, for the Chat role and for the claim judge when it ran, the temperature and seed the requests carried, or that none was sent. A temperature added by a library default SHALL be recorded as that value. The record SHALL also give the host that served the request and that host's published support for each value the request set. A provider that does not report its host SHALL record host and support as unknown.

#### Scenario: Library default recorded

- **WHEN** `answer.temperature` is empty and an answer runs on OpenRouter
- **THEN** the answer result MUST record the temperature the request carried (0.1 with the current library) and MUST record that no seed was sent

#### Scenario: Set values recorded

- **WHEN** `answer.temperature` is `0` and `answer.seed` is `20261101`
- **THEN** the answer result MUST record temperature 0 and seed 20261101 for the Chat role

#### Scenario: Client-sampled answer has no Chat record

- **WHEN** the MCP client writes the answer through client sampling
- **THEN** the answer result MUST NOT hold a Chat `sampling` record, because OMRS sees no Chat request

#### Scenario: Host and support recorded

- **WHEN** an answer runs on OpenRouter and the reply names host `Fireworks`, and the endpoint list shows that host takes `temperature` and `seed`
- **THEN** the answer result MUST record host `Fireworks` and `accepted` true for both values

### Requirement: The answer contract declares the new result fields

The `AnswerResponse` schema in `openapi.yaml` SHALL declare `sampling`, `judge_calls`, `usage` and `reasoning` and SHALL NOT allow other undeclared properties.

#### Scenario: Contract declares the record

- **WHEN** the contract test compares every key a completed answer result can hold with the `AnswerResponse` properties
- **THEN** every key MUST be declared, and `additionalProperties` MUST be false

### Requirement: Allowed hosts are settings for each role

`answer.allowed_hosts` (Chat) and `answer.verify_allowed_hosts` (judge) SHALL each hold OpenRouter host names separated by commas, or be empty. A list SHALL resolve through the normal source order (ADR-087), with `ANSWER__ALLOWED_HOSTS` and `ANSWER__VERIFY_ALLOWED_HOSTS` as the environment names. An empty list SHALL leave the request as it was. A provider other than OpenRouter SHALL send nothing for the list and the settings read SHALL report that it ignores it.

#### Scenario: Empty list keeps the request

- **WHEN** both lists are empty and an answer runs on OpenRouter
- **THEN** the request MUST carry no `provider` routing field

#### Scenario: Provider without host routing

- **WHEN** the Chat provider is `llamacpp` and `answer.allowed_hosts` is `Fireworks`
- **THEN** the request MUST carry no host field, and `GET /v1/settings/chat` MUST report that the provider ignores the list

#### Scenario: Locked list

- **WHEN** `ANSWER__ALLOWED_HOSTS` is set in the process environment
- **THEN** the Chat panel MUST show the list as locked and a save of it MUST be refused with 409

### Requirement: A set host list pins OpenRouter calls to hosts that take the values

When a list is set on OpenRouter, every request for that role SHALL be limited to the listed hosts, with no fallback to another host, and to hosts that take every value the request sets. Before the first call of that role in a process, OMRS SHALL read the model's endpoint list. When no listed host supports every set value, OMRS SHALL make no call and SHALL refuse with a message that names the model, the hosts and the missing values.

#### Scenario: Host that drops the seed

- **WHEN** `answer.seed` is `20261101`, `answer.allowed_hosts` is `Relace` and the endpoint list shows `Relace` without `seed`
- **THEN** OMRS MUST make no request and MUST return an error that names the model, `Relace` and `seed`

#### Scenario: Listed host takes the values

- **WHEN** `answer.allowed_hosts` is `Fireworks` and the endpoint list shows `Fireworks` with `temperature` and `seed`
- **THEN** the request MUST carry `provider.only` of `Fireworks`, `allow_fallbacks` false and `require_parameters` true, and MUST carry the temperature and seed

#### Scenario: Judge list is separate

- **WHEN** `answer.verify_claims` is true, `answer.allowed_hosts` is `Fireworks` and `answer.verify_allowed_hosts` is empty
- **THEN** judge requests MUST NOT carry a host limit, and Chat requests MUST carry it

#### Scenario: Reply names a host outside the list

- **WHEN** the reply names a host that is not in the list
- **THEN** the `sampling` record MUST hold that host and the answer MUST report the mismatch (`host_in_list` false)
