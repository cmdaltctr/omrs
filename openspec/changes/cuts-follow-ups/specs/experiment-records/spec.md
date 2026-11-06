## ADDED Requirements

### Requirement: A new experiment names its operator

`omrs experiments new` SHALL accept `--operator TEXT` and SHALL write that text into the Operator line of each template file it creates. Without the option the placeholder SHALL stay. The checker SHALL report a warning `operator-placeholder` for each `report.md` or `protocol.md` whose Operator line still holds a placeholder in angle brackets.

#### Scenario: Operator given

- **WHEN** a Quick experiment is created with `--operator "OMRS maintainer, with a coding agent"`
- **THEN** the Operator line of `report.md` MUST read `OMRS maintainer, with a coding agent`

#### Scenario: Placeholder left

- **GIVEN** a record whose `report.md` Operator line reads `<person>, with <agent, if used>`
- **WHEN** the checker runs
- **THEN** it MUST report the warning `operator-placeholder` for that file
- **AND** it MUST report no error for it
