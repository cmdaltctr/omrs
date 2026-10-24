# Spec Delta

## ADDED Requirements

### Requirement: Test settings disable LLM metadata extraction by default

Settings that the shared test factory builds SHALL disable LLM metadata extraction and SHALL allow one classification attempt, unless the test overrides these fields. A test that passes its own metadata block SHALL keep that block exactly as given.

#### Scenario: Factory settings with no metadata override

- **WHEN** a test builds settings through the shared factory with no metadata override
- **THEN** the metadata extraction mode is `disabled`
- **AND** the maximum classification attempts is 1

#### Scenario: Factory settings with one metadata field overridden

- **WHEN** a test builds settings through the shared factory and overrides one metadata field
- **THEN** that field has the given value
- **AND** the other metadata fields keep the test defaults

#### Scenario: Factory settings with a whole metadata block

- **WHEN** a test passes a complete metadata block to the shared factory
- **THEN** the settings use that block without change

### Requirement: Fast tests make no unplanned LLM metadata calls

A fast test SHALL fail when ingestion dispatches an LLM-backed metadata strategy (any strategy other than `disabled` and `keyword`), unless the test is explicitly marked as one that exercises LLM metadata strategies. The failure message SHALL name the strategy and tell the author how to disable extraction or mark the test.

#### Scenario: Unmarked test ingests with LLM extraction enabled

- **WHEN** an unmarked fast test ingests a document with settings that select the `llamaindex` extraction mode
- **THEN** the test fails before any network call is made
- **AND** the failure names the `llamaindex` strategy

#### Scenario: Marked test exercises an LLM strategy with a mock

- **WHEN** a test carries the LLM metadata marker and dispatches a mocked LLM strategy
- **THEN** the guard does not interfere and the test result depends only on its own assertions

#### Scenario: Unmarked test uses keyword or disabled extraction

- **WHEN** an unmarked fast test ingests with the `keyword` or `disabled` extraction mode
- **THEN** the guard does not interfere

### Requirement: Timeout tests finish near their configured timeout

A fast test that checks a timeout SHALL configure every value that sets the effective wait, so that the test finishes within a few seconds of the timeout it means to test. The OCR post-dispatch timeout test SHALL finish in under 10 seconds.

#### Scenario: OCR worker hangs after dispatch

- **WHEN** the OCR post-dispatch timeout test runs against a hanging worker with a 1-second request timeout
- **THEN** the file fails with a structured timeout error that names a 1-second wait
- **AND** the test finishes in under 10 seconds

### Requirement: The clean-base tripwire reuses the fast-suite result

When it is given the path of a JUnit report from the fast-suite run in the same environment, the clean-base tripwire SHALL take the executed count from that report and SHALL NOT run the fast suite again. When no report path is given, the tripwire SHALL run the fast suite itself. The executed and deselected pins SHALL keep their meaning.

#### Scenario: Report from a passing fast-suite run

- **WHEN** the fast suite passes, writes a JUnit report, and the tripwire runs with that report path
- **THEN** the tripwire compares the report's passed count with the pinned executed count
- **AND** it does not start a second fast-suite run

#### Scenario: Report with failures or errors

- **WHEN** the given report records at least one failure or error
- **THEN** the tripwire fails and says that the fast suite did not pass

#### Scenario: Report older than the code

- **WHEN** a file under `src/` or `tests/` is newer than the given report
- **THEN** the tripwire fails and says that the report is stale

#### Scenario: Report path names a missing file

- **WHEN** the report path is set but no file exists there
- **THEN** the tripwire fails and names the missing path

#### Scenario: No report path given

- **WHEN** the tripwire runs with no report path
- **THEN** it runs the fast suite itself and checks the same pinned counts as before this change

#### Scenario: Local CI and CI jobs share the report

- **WHEN** `scripts/local_ci.sh`, the CI `test` job or the base entry of the CI `floors` job runs
- **THEN** the fast-suite step writes the report and the tripwire step reads it
