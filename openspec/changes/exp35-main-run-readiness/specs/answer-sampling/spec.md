## MODIFIED Requirements

### Requirement: The answer contract declares the new result fields

The `AnswerResponse` schema in `openapi.yaml` SHALL declare `sampling`, `judge_calls`, `usage`, `reasoning`, `rate_limited` and `verification_rate_limited` and SHALL NOT allow other undeclared properties. Both rate-limit records SHALL use one closed schema: `kind` (`rate_limit` or `out_of_credit`), `http_status` (429 or 402) and `retry_after_seconds` (a number or `null`).

#### Scenario: Contract declares the record

- **WHEN** the contract test compares every key a completed answer result can hold with the `AnswerResponse` properties
- **THEN** every key MUST be declared, and `additionalProperties` MUST be false

#### Scenario: Rate-limited results conform

- **WHEN** the contract test validates a rate-limited generation result and a result with a rate-limited judge, each built by the real result builder
- **THEN** both results MUST conform, and a record with an undeclared key or an unknown `kind` MUST be refused
