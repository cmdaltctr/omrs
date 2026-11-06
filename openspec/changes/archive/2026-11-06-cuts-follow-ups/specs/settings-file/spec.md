## ADDED Requirements

### Requirement: A removed retired key takes its own comment

When a save removes a retired key from `omrs.jsonc`, the comment lines directly above that key SHALL go with it. The removal SHALL stop at a blank line, at a line that holds code, or at a commented-out key line. Every other removal SHALL keep all comments.

#### Scenario: Comment above the retired key goes

- **GIVEN** `omrs.jsonc` holds a comment line directly above `"ocr_local_min_confidence": 0.9`
- **WHEN** a save of `ocr_local_cuts` removes the retired key
- **THEN** the file MUST hold neither the key nor that comment line
- **AND** every other comment MUST stay

#### Scenario: A commented-out key above stays

- **GIVEN** a commented-out key line, then a description comment, then the retired key, with no blank line between them
- **WHEN** the save removes the retired key
- **THEN** the description comment MUST go
- **AND** the commented-out key line MUST stay

#### Scenario: A plain clear keeps comments

- **WHEN** the user returns a setting with a comment above it to the default
- **THEN** the member MUST go and the comment MUST stay
