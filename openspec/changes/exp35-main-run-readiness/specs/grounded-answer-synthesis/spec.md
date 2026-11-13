## ADDED Requirements

### Requirement: A rate-limited generation is a typed error

When a generation call still fails with HTTP 429 or HTTP 402 after every retry, the result SHALL be a generation error that keeps the evidence. It SHALL carry a `rate_limited` record with `kind`, `http_status` and `retry_after_seconds` (a number or `null`), and a fixed, actionable `error`. `kind` SHALL be `rate_limit` for HTTP 429 and for HTTP 402 with a `Retry-After`. Other failures SHALL NOT carry `rate_limited`. The operation SHALL NOT raise.

#### Scenario: Rate limit after the client retries

- **WHEN** the answer model's provider still replies HTTP 429 with `Retry-After: 7` after the client library's own retries
- **THEN** the result MUST have status `error`, `failure_stage` `generation`, `answer` `null` and the retrieved evidence
- **AND** the result MUST carry `rate_limited` with `kind` `rate_limit`, `http_status` 429 and `retry_after_seconds` 7

#### Scenario: Other failures keep their shape

- **WHEN** generation fails with an error that is not HTTP 429 or HTTP 402
- **THEN** the result MUST NOT carry `rate_limited`, and `error` MUST name the failure as before this change

#### Scenario: Both answering paths

- **WHEN** generation is rate-limited on the standard path and on the user-profile path
- **THEN** both results MUST carry the same `rate_limited` record

#### Scenario: Error turns are not saved as answers

- **WHEN** the web chat receives a result that carries `rate_limited`
- **THEN** it MUST show a line for that `kind` and offer Retry, and it MUST NOT save the result as a chat turn

#### Scenario: MCP tool returns the record

- **WHEN** an MCP client calls `answer_documents` and generation is rate-limited
- **THEN** the tool MUST return the error result with its `rate_limited` record and MUST NOT raise

### Requirement: An exhausted provider credit is its own kind

An HTTP 402 without a `Retry-After` SHALL mean that the provider account is out of credit. The operation SHALL NOT send the call again. The `rate_limited` record SHALL have `kind` `out_of_credit`, `http_status` 402 and `retry_after_seconds` `null`. `error` SHALL say that the provider account is out of credit and SHALL tell the user to top it up, then ask again.

#### Scenario: Out of credit

- **WHEN** a generation call replies HTTP 402 with no `Retry-After`
- **THEN** the operation MUST make no further attempt for that call
- **AND** the result MUST carry `rate_limited` with `kind` `out_of_credit`, and `error` MUST tell the user to top up the provider account

#### Scenario: Web chat names the top-up

- **WHEN** the web chat receives a result whose `rate_limited` kind is `out_of_credit`
- **THEN** it MUST tell the user to top up the provider account, not to wait

### Requirement: Only a short spend-limit wait is retried in OMRS

The answering operation SHALL send an HTTP 402 call again when the reply carries a `Retry-After` of 30 seconds or less. It SHALL wait that time first, and SHALL make at most 2 further attempts per call. It SHALL NOT add retries for HTTP 429, because the provider client libraries already retry it. The same rule SHALL apply to a claim judge that is a completion seam.

#### Scenario: Short spend-limit wait

- **WHEN** a generation call replies HTTP 402 with `Retry-After: 5`, and the next attempt succeeds
- **THEN** the operation MUST wait 5 seconds, send the call again and return the answer, without a `rate_limited` record

#### Scenario: Long wait time

- **WHEN** a generation call replies HTTP 402 with `Retry-After: 120`
- **THEN** the operation MUST NOT send the call again, and the result MUST carry `rate_limited` with `kind` `rate_limit`, `http_status` 402 and `retry_after_seconds` 120

#### Scenario: No extra layer for HTTP 429

- **WHEN** the client library raises its rate-limit error for HTTP 429 after its own retries
- **THEN** the operation MUST NOT send the call again and MUST return the typed error

### Requirement: A rate-limited claim judge is typed

When claim verification stops because the judge's provider replied HTTP 429 or HTTP 402, the answer SHALL keep its text, citations, evidence and status, as for any judge failure. The result SHALL carry `verification_skipped` with a fixed reason and a `verification_rate_limited` record with the same shape and kind rules as `rate_limited`. A judge failure that is not a rate limit SHALL NOT carry the record. Both answering paths SHALL give the same record.

#### Scenario: Judge rate-limited

- **WHEN** claim verification runs and a judge call still fails with HTTP 429 and `Retry-After: 30` after its retries
- **THEN** the answer MUST be returned with `verification_skipped` set
- **AND** the result MUST carry `verification_rate_limited` with `kind` `rate_limit`, `http_status` 429 and `retry_after_seconds` 30

#### Scenario: Judge out of credit

- **WHEN** a judge call replies HTTP 402 with no `Retry-After`
- **THEN** the result MUST carry `verification_rate_limited` with `kind` `out_of_credit`, and `verification_skipped` MUST tell the user to top up the judge provider account

#### Scenario: Other judge failure

- **WHEN** a judge call fails with an error that is not HTTP 429 or HTTP 402
- **THEN** the result MUST NOT carry `verification_rate_limited`, and `verification_skipped` MUST name the failure as before this change
