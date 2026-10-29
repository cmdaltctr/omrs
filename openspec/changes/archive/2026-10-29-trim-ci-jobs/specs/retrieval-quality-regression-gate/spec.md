## MODIFIED Requirements

### Requirement: Quality CI jobs fail loudly and preserve existing fast paths

`.github/workflows/ci.yml` SHALL define dedicated retrieval-quality execution.
Tier 1 SHALL run in its own pull-request job. Tier 2 SHALL run in its own
nightly and manually dispatched job.

Both jobs SHALL set `continue-on-error` to false and SHALL NOT suppress command
failures. Scheduled execution SHALL NOT cause unrelated existing CI jobs to run
unless their existing trigger contract already requires it. The floor
resolution job and its matrix-scope job run on the schedule, because the
`dependency-floor-integrity` capability requires a nightly floor check.

#### Scenario: A quality assertion fails

- **WHEN** either quality test command exits non-zero
- **THEN** its CI job fails
- **AND** no shell fallback or workflow setting converts the failure into success

#### Scenario: The nightly schedule fires

- **WHEN** the CI workflow starts from its nightly schedule
- **THEN** Tier 2 runs
- **AND** the floor resolution job runs with the base entry and every
  optional-extra entry
- **AND** unrelated fast, optional-backend, lint, and coverage jobs do not run
  solely because of that schedule
