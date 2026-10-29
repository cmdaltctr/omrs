## MODIFIED Requirements

### Requirement: Declared floors form an installable, tested contract

The lowest versions permitted by `[project.dependencies]` and
`[project.optional-dependencies]` SHALL resolve to a working installation.
Continuous integration SHALL install at those floors and run the fast test
suite against them. A floor that resolves but fails the suite SHALL fail the
build.

The base install SHALL be checked at its floors on every push and every pull
request. Each optional extra that declares at least one package SHALL be
checked at its floors on every push to an integration branch, on the nightly
scheduled run, on a manual run, and on every pull request that changes
`pyproject.toml`, `uv.lock` or the CI workflow file. An extra that declares no
packages installs nothing beyond the base, so it SHALL NOT have its own floor
entry. The `torch` extra keeps its own dedicated job and SHALL NOT enter the
floor matrix.

#### Scenario: Floor resolution is exercised in CI

- **WHEN** the CI pipeline runs on a push or pull request
- **THEN** a job MUST resolve dependencies with the lowest declared direct
  versions rather than the lockfile
- **AND** that job MUST run the fast test suite and report its result without
  suppression

#### Scenario: Pull request without dependency changes

- **WHEN** a pull request changes none of `pyproject.toml`, `uv.lock` and the
  CI workflow file, compared with the merge base of its base and head commits
- **THEN** the base floor entry MUST run
- **AND** the optional-extra floor entries MUST NOT run

#### Scenario: Pull request with dependency changes

- **WHEN** a pull request changes `pyproject.toml`, `uv.lock` or the CI
  workflow file, compared with the merge base of its base and head commits
- **THEN** the base floor entry and one floor entry for each optional extra
  that declares packages, except `torch`, MUST run

#### Scenario: Push, nightly and manual runs check every extra

- **WHEN** CI runs because of a push to an integration branch, the nightly
  schedule, or a manual dispatch
- **THEN** the base floor entry and one floor entry for each optional extra
  that declares packages, except `torch`, MUST run

#### Scenario: An empty extra has no floor entry

- **WHEN** an optional extra declares no packages
- **THEN** the floor matrix MUST NOT hold an entry for it

#### Scenario: An unsatisfiable floor set fails the build

- **WHEN** a floor is raised to a version that cannot co-resolve with the
  other declared floors
- **THEN** the floor job MUST fail at the resolution step
- **AND** the failure output MUST name the conflicting requirement

#### Scenario: A floor that installs but breaks fails the build

- **WHEN** the floor set resolves but a permitted old version omits an API the
  project calls
- **THEN** the floor job MUST fail on the test that exercises that API

### Requirement: Base and Chroma-extra dependency contracts SHALL be tested separately

The built base package and a fresh base installation SHALL exclude both Chroma
distributions. The optional `chroma` group SHALL retain supported floors and run
in a separate complete CI job. That job is the coverage job: it installs the
`chroma` extra from the lockfile, runs the full fast suite, and fails when any
test skips with the "chroma extra not installed" reason.

#### Scenario: Built base wheel excludes Chroma

- **WHEN** base wheel metadata is inspected
- **THEN** neither Chroma package MUST be an unconditional `Requires-Dist`
- **AND** the Chroma extra markers MUST be represented accurately

#### Scenario: Fresh base installation excludes Chroma

- **WHEN** the base wheel is installed without extras in a fresh environment
- **THEN** both Chroma distributions MUST be absent from import metadata and installed-distribution inventory
- **AND** the full LanceDB-default fast suite and base import-lint contracts MUST pass

#### Scenario: Chroma cases run in the coverage job

- **WHEN** the coverage job runs with the `chroma` extra installed
- **THEN** no test MUST skip with the "chroma extra not installed" reason
- **AND** a skip with that reason MUST fail the job and name the reason

#### Scenario: Chroma extra resolves at floors

- **WHEN** the `chroma` group is resolved at lowest direct versions
- **THEN** every Chroma-skipped base case MUST run in the `chroma` floor entry
- **AND** a skip with the "chroma extra not installed" reason MUST fail that entry
- **AND** contract, local, hybrid and cloud suites MUST pass
- **AND** floor drift checks MUST cover both packages
