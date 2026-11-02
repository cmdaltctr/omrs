## ADDED Requirements

### Requirement: Document reading edits the reader list in order

Settings › Document reading › PDF reading SHALL show the reader list as ordered rows. The user SHALL be able to add a registered reader, remove a reader, and move a reader up or down. Each row SHALL say what its position does: the first installed reader reads, a later reader retries when the readers before it returned no text. A reader that is not installed SHALL show "Not installed" and a link to Integrations › PDF readers. The page SHALL refuse to save an empty list.

#### Scenario: Move a reader up

- **GIVEN** the list `pdf_inspector, liteparse, pypdf`
- **WHEN** the user moves pypdf above LiteParse and saves
- **THEN** `omrs.jsonc` SHALL hold `"pdf_readers": ["pdf_inspector", "pypdf", "liteparse"]`
- **AND** the row SHALL show "Restart to apply"

#### Scenario: Empty list refused

- **WHEN** the user removes every reader and saves
- **THEN** the page SHALL show the reason and write nothing

### Requirement: Document reading edits the OCR engine list in order

The Engines block SHALL show the OCR engine list as ordered rows with add, remove, move up and move down. Each row SHALL say that a later engine runs only when the engines before it are unavailable before dispatch. An engine that is not provisioned SHALL show "Not provisioned". A list of one engine SHALL be allowed, so the user can turn the fallback off on the page.

#### Scenario: Remove the fallback engine

- **GIVEN** the list `dots-mocr, paddleocr-vl`
- **WHEN** the user removes PaddleOCR-VL and saves
- **THEN** `omrs.jsonc` SHALL hold `"ocr_engines": ["dots-mocr"]`
- **AND** no fallback engine SHALL run after the restart

#### Scenario: Locked by the environment

- **GIVEN** `OCR_ENGINES` or `OCR_ENGINE_PRIMARY` is set in the environment
- **WHEN** the Engines block renders
- **THEN** the list SHALL be read-only and SHALL name the variable to remove

### Requirement: Document reading lists render at desktop and phone widths

The two list controls SHALL fit a 1280 px window and a 390 px window with no horizontal page scroll. At 390 px the move and remove buttons SHALL stay reachable and labelled for screen readers.

#### Scenario: Phone width

- **WHEN** the page renders at 390 px
- **THEN** every list row and its buttons SHALL be visible without horizontal scrolling
