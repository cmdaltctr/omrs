## Purpose

Let the operator name decision models that answer yes/no questions about document pages, local or hosted, with keys held by reference and model checks that enforce the 8-bit and vision projector rules.

## ADDED Requirements

### Requirement: Decision models are named entries of a registered kind

The system SHALL hold zero or more named decision model entries. Each entry SHALL have a kind, an address, a model name and an "accepts images" flag. Each kind SHALL come from a decision model registry, so a new kind is one file plus one `register()` line. This change SHALL register `llamacpp`, `typesafe`, `cloudflare` and `ollama`.

#### Scenario: Two entries

- **GIVEN** an entry `clef-local` of kind `llamacpp` and an entry `jev` of kind `typesafe`
- **WHEN** the Providers page loads
- **THEN** the Decision models card SHALL list both with their kind, model and image flag

#### Scenario: Unknown kind

- **WHEN** an entry names kind `foo`
- **THEN** the entry SHALL be ignored and listed as a problem naming the registered kinds

### Requirement: Every kind asks the same question shape

A decision model client SHALL send one yes/no question with the options `no` and `yes`, the page text as state and, when the router sees images, one page image. It SHALL return P(yes) between 0 and 1. A reply outside that range or without the answer SHALL count as a failed request.

#### Scenario: Local answer

- **GIVEN** a reachable `llamacpp` entry
- **WHEN** a router asks about one page
- **THEN** the client SHALL return one P(yes) value

#### Scenario: Malformed reply

- **WHEN** the reply lacks the answer
- **THEN** the request SHALL count as failed with a fixed reason and no reply text in logs

### Requirement: A hosted entry holds its key by reference only

An entry whose address is not a loopback address SHALL count as hosted. A hosted entry SHALL hold its key as `env://NAME`, `file://` inside the secrets folder, or `keychain://<provider>`. A literal key SHALL be refused on save and ignored in the file. The key SHALL never be returned by the API or written to a log.

#### Scenario: Literal key refused

- **WHEN** the user saves a hosted entry with a literal key
- **THEN** the save SHALL fail with a reason and write nothing

#### Scenario: Loopback is local

- **GIVEN** an entry at `http://127.0.0.1:9931`
- **WHEN** the entry is read
- **THEN** it SHALL count as local and need no key

### Requirement: A local decision model must be 8-bit or higher

For a managed `llamacpp` entry the system SHALL read the quantisation type from the GGUF model file header before start. It SHALL accept Q8_0, F16, BF16 and F32 and SHALL refuse any other type, naming the type and the rule. For an external entry it SHALL check the model name the server reports. When the type cannot be read, the entry SHALL show "Quantisation not checked" and the router test SHALL repeat that line.

#### Scenario: Q4_K_M refused

- **GIVEN** a managed entry whose model file is Q4_K_M
- **WHEN** the runtime would start
- **THEN** it SHALL NOT start
- **AND** the reason SHALL say decision models run at 8-bit or higher

#### Scenario: Q8_0 accepted

- **GIVEN** a managed entry whose model file is Q8_0
- **WHEN** the runtime starts
- **THEN** the quantisation check SHALL pass

### Requirement: An image entry must prove its vision projector is loaded

An entry with "accepts images" on SHALL pass a smoke test before any router uses it with images, once per process and on the Test button. The test SHALL send one bundled page image twice, with its right text and with wrong text. It SHALL pass only when P(yes) for the right text exceeds P(yes) for the wrong text by the fixed margin. A managed entry SHALL also declare a projector file, or it SHALL NOT start.

#### Scenario: Projector missing

- **GIVEN** an external server started without a projector
- **WHEN** the smoke test runs
- **THEN** it SHALL fail with the reason `projector-not-loaded`
- **AND** no image router SHALL use the entry

#### Scenario: Smoke test passes

- **GIVEN** a server with the projector loaded
- **WHEN** the smoke test runs
- **THEN** the right-text answer SHALL be higher than the wrong-text answer by the margin

### Requirement: The decision model test runs only on request

The Providers card SHALL offer Test for each entry. Test SHALL run the quantisation check, a one-question text request and, for an image entry, the smoke test. It SHALL return a fixed reason for each failure. Nothing SHALL contact a decision model at start-up or on page load.

#### Scenario: Test unreachable server

- **GIVEN** an entry whose server is not running
- **WHEN** the user presses Test
- **THEN** the result SHALL be `unreachable`

#### Scenario: Page load contacts nothing

- **WHEN** the Providers page loads
- **THEN** no request SHALL go to any decision model

### Requirement: A kind without a recorded live request is labelled

A kind SHALL be labelled "Not yet tested" in Settings until one live request of that kind has passed the smoke test and been recorded. An entry of such a kind SHALL still be usable. A hosted kind SHALL still need the router opt-in.

#### Scenario: Cloudflare entry before its live check

- **GIVEN** an entry of kind `cloudflare` and no recorded live request
- **WHEN** the Providers page loads
- **THEN** the entry SHALL show "Not yet tested"
- **AND** a router that uses it SHALL still need the "send pages off this machine" tick

#### Scenario: Label removed after the live check

- **WHEN** a live request of kind `ollama` passes the smoke test and the result is recorded
- **THEN** the "Not yet tested" label SHALL no longer show for kind `ollama`
