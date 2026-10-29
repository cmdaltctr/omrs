## MODIFIED Requirements

### Requirement: A citation popover shows the evidence and its metadata

The citation popover SHALL show the citation ordinal, the source name, the score with its kind when present, and the evidence text sent to the model. It SHALL show a Lineage section with the source id, the source version, the chunk position ("Chunk i of n"), the page label when present, and every chunk id the citation spans when it covers more than one chunk. When the citation spans more than one page, the Lineage section SHALL show the page range ("Pages 5–6") instead of the single page label. It SHALL show a Metadata section that lists every other stored metadata key of the chunk with its value, read from the stored index.

#### Scenario: Popover content

- **WHEN** the user presses citation chip `[2]` of an answer whose citation 2 spans two chunks of `paper.pdf`
- **THEN** the popover MUST show the source `paper.pdf`, the evidence text, the chunk position, both chunk ids and the stored metadata keys with their values

#### Scenario: A citation that spans pages

- **WHEN** the user presses a citation chip whose citation carries `page_labels` `["5", "6"]`
- **THEN** the Lineage section MUST show "Pages 5–6"
