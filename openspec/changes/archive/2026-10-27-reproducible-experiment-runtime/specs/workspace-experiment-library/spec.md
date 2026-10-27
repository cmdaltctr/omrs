## ADDED Requirements

### Requirement: The New experiment form asks for the purpose

The New experiment form SHALL ask for the purpose, `Optimisation` or `Publication`, with `Optimisation` selected first. When `Publication` is chosen, the form SHALL set the size to `Confirmatory` and SHALL say in one line that the plan needs a pinned llama.cpp runtime.

#### Scenario: Create a publication experiment

- **WHEN** the user chooses `Publication` in the New experiment form and creates the experiment
- **THEN** the size is `Confirmatory`
- **AND** the new record holds `"purpose": "publication"`
- **AND** the library shows the experiment as `Publication`

### Requirement: The library shows the purpose

The library list and the experiment page SHALL show the purpose of each experiment. A record without the field SHALL show as `Optimisation`.

#### Scenario: Old record in the list

- **WHEN** the library lists a record that has no `purpose` field
- **THEN** it shows the experiment as `Optimisation`

### Requirement: The create request carries a valid purpose

The create request SHALL carry the purpose, and the server SHALL pass it to the folder creator. A request without a purpose SHALL create an `optimisation` experiment. A request with another value SHALL be refused and SHALL write nothing.

#### Scenario: Unknown purpose in the request

- **WHEN** a create request carries the purpose `paper`
- **THEN** the request is refused with a message that names the allowed values
- **AND** no folder is created
