## MODIFIED Requirements

### Requirement: The answer contract declares the new result fields

The `AnswerResponse` schema in `openapi.yaml` SHALL declare `sampling`, `judge_calls`, `usage`, `reasoning`, `rate_limited` and `verification_rate_limited` and SHALL NOT allow other undeclared properties. Both rate-limit records SHALL use one closed schema: `kind` (`rate_limit` or `out_of_credit`), `http_status` (429 or 402) and `retry_after_seconds` (a number or `null`).

#### Scenario: Contract declares the record

- **WHEN** the contract test compares every key a completed answer result can hold with the `AnswerResponse` properties
- **THEN** every key MUST be declared, and `additionalProperties` MUST be false

#### Scenario: Rate-limited results conform

- **WHEN** the contract test validates a rate-limited generation result and a result with a rate-limited judge, each built by the real result builder
- **THEN** both results MUST conform, and a record with an undeclared key or an unknown `kind` MUST be refused

### Requirement: A set host list pins OpenRouter calls to hosts that take the values

When a list is set on OpenRouter, every request for that role SHALL be limited to the listed hosts, with no fallback to another host, and to hosts that take every value the request sets. Before the first call of that role in a process, OMRS SHALL read the model's endpoint list. When no listed host supports every set value, OMRS SHALL make no call and SHALL refuse with a message that names the model, the hosts and the missing values.

#### Scenario: Host that drops the seed

- **WHEN** `answer.seed` is `20261101`, `answer.allowed_hosts` is `Relace` and the endpoint list shows `Relace` without `seed`
- **THEN** OMRS MUST make no request and MUST return an error that names the model, `Relace` and `seed`

#### Scenario: Listed host takes the values

- **WHEN** `answer.allowed_hosts` is `Fireworks` and the endpoint list shows `Fireworks` with `temperature` and `seed`
- **THEN** the request MUST carry `provider.only` of `Fireworks`, `allow_fallbacks` false, `require_parameters` true, `zdr` true and `data_collection` `deny`, and MUST carry the temperature and seed

#### Scenario: Judge list is separate

- **WHEN** `answer.verify_claims` is true, `answer.allowed_hosts` is `Fireworks` and `answer.verify_allowed_hosts` is empty
- **THEN** judge requests MUST NOT carry a host limit, and Chat requests MUST carry it

#### Scenario: Reply names a host outside the list

- **WHEN** the reply names a host that is not in the list
- **THEN** the `sampling` record MUST hold that host and the answer MUST report the mismatch (`host_in_list` false)
