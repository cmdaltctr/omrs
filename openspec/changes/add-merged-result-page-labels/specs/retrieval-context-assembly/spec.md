## ADDED Requirements

### Requirement: A merged row reports every page it spans

A merged row SHALL expose `page_labels`: the page label of each constituent chunk, in ascending chunk order, each label once. A constituent without a page label SHALL add nothing to the list. A merged row whose constituents carry no page label, and a row that was not merged, SHALL NOT expose `page_labels`. The row's `page_label` SHALL stay the page label of its lowest-index constituent.

#### Scenario: A merged row spans two pages

- **GIVEN** adjacent chunks at indices i and i+1 of one source version, on pages "5" and "6"
- **WHEN** assembly merges them
- **THEN** the merged row's `page_labels` SHALL be `["5", "6"]`
- **AND** its `page_label` SHALL be "5"

#### Scenario: Chunks on one page

- **GIVEN** three adjacent merged chunks, all on page "12"
- **WHEN** assembly merges them
- **THEN** the merged row's `page_labels` SHALL be `["12"]`

#### Scenario: Chunks without page labels

- **GIVEN** adjacent merged chunks from a Markdown file, with no page labels
- **WHEN** assembly merges them
- **THEN** the merged row SHALL NOT expose `page_labels`

#### Scenario: A row that was not merged

- **GIVEN** a single chunk on page "3" with no adjacent result
- **WHEN** assembly runs
- **THEN** the row SHALL NOT expose `page_labels`
- **AND** its `page_label` SHALL be "3"
