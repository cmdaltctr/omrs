## ADDED Requirements

### Requirement: A citation names every page its evidence spans

An evidence row built from a search row with `page_labels` SHALL carry them. A citation of a merged evidence row SHALL carry that row's `page_labels`. A citation of a row without `page_labels` SHALL NOT carry them.

#### Scenario: A citation spans two pages

- **GIVEN** an answer citing source N, where evidence row N is a merged row with `page_labels` `["5", "6"]`
- **WHEN** the answer is returned
- **THEN** citation N SHALL carry `page_labels` `["5", "6"]`

#### Scenario: A citation of a single chunk

- **GIVEN** an answer citing a row that was not merged
- **WHEN** the answer is returned
- **THEN** the citation SHALL NOT carry `page_labels`
