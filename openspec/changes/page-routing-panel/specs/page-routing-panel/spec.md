## Purpose

One panel that shows how OMRS routes each PDF page, laid out as the real page flow, so an operator can set the readers, page rules, router, local OCR backends and OCR engines in the order they act. It appears in Settings › Document reading and in the Studio Read document step.

## ADDED Requirements

### Requirement: The Page routing panel shows the page flow in five steps

The panel SHALL show, top to bottom: the OCR fallback switch and the routing unit; step 1 "PDF readers" (`pdf_readers`); step 2 "Pages with no usable text" (Skip blank pages, Maths pages, Non-Latin pages); step 3 "Pages that look fine" (`document_router`); step 4 "Local OCR backends" (`ocr_local_backends` with its cut boxes); step 5 "OCR engines" (`ocr_engines`). Each step SHALL carry its number and title.

#### Scenario: Steps in flow order

- **WHEN** Settings › Document reading renders
- **THEN** the Page routing panel MUST show the steps "PDF readers", "Pages with no usable text", "Pages that look fine", "Local OCR backends" and "OCR engines", numbered 1 to 5 in that order
- **AND** the OCR fallback and routing unit rows MUST show above step 1

#### Scenario: Each key in its step

- **WHEN** the panel renders
- **THEN** step 2 MUST hold the rows `ocr_skip_blank_pages`, `ocr_maths_routing_enabled` and `ocr_non_latin_routing` in that order
- **AND** step 3 MUST hold the `document_router` row
- **AND** step 4 MUST hold the `ocr_local_backends` list and a cut box for each listed backend

#### Scenario: Old blocks gone

- **WHEN** Settings › Document reading renders
- **THEN** no block titled "When to use OCR", "Maths pages", "Local OCR" or "Engines" MUST show

### Requirement: Order-sensitive settings are lists and the others are switches or choices

The readers, the local OCR backends and the OCR engines SHALL be ordered lists with move up, move down, add and remove. Skip blank pages and Maths pages SHALL be switches. Non-Latin pages and the router SHALL be single choices. The page rules SHALL have no move control.

#### Scenario: Rules cannot be reordered

- **WHEN** step 2 renders
- **THEN** it MUST show no move up or move down button
- **AND** it MUST show the line "These checks run in a fixed order. Blank pages are checked first."

#### Scenario: Lists can be reordered

- **WHEN** the user edits step 1, 4 or 5
- **THEN** each list row MUST offer move up, move down and remove, and the list MUST offer an add choice

### Requirement: Each panel row shows a help line and its source

Each row SHALL show a short plain help line. In Settings each row SHALL also show its source (default, `omrs.jsonc`, or locked by the environment or `.env`) and its default, with the restart and lock rules of the other Document reading rows.

#### Scenario: Source shown

- **GIVEN** `omrs.jsonc` holds `"ocr_maths_routing_enabled": false`
- **WHEN** the panel renders in Settings
- **THEN** the Maths pages row MUST show the help line, the source `omrs.jsonc` and the default On

#### Scenario: Locked row

- **GIVEN** `OCR_SKIP_BLANK_PAGES=false` is set in the environment
- **WHEN** the panel renders in Settings
- **THEN** the Skip blank pages row MUST offer no Edit and MUST show "Remove OCR_SKIP_BLANK_PAGES from the environment or .env to edit it here."

### Requirement: The non-Latin choice labels its default

The Non-Latin pages choice SHALL label `off` as the default in Settings. Its help line SHALL say that `detect` sees only text that already exists and does not catch scanned pages, and that `always` suits a collection known to be non-Latin.

#### Scenario: Default labelled

- **WHEN** the user opens the Non-Latin pages choice in Settings
- **THEN** the choices MUST read "off (default)", "detect" and "always"

### Requirement: The panel links to the routing guide and the router definitions

The panel SHALL show a "Learn more" link to the page routing guide. Step 3 SHALL link to the Router section of Settings › Document reading, where routers are defined.

#### Scenario: Guide link

- **WHEN** the panel renders
- **THEN** it MUST show a "Learn more" link whose address ends in `docs/guides/page-routing.md`

#### Scenario: Router link

- **WHEN** step 3 renders and no router is defined
- **THEN** it MUST show "No router" as the only choice and a link "Define routers in the Router section"

### Requirement: The optional pypdfium2 reader is offered in step 1

Step 1 SHALL offer `pypdfium2` in its add choice and SHALL mark it optional. When it is not installed, the choice SHALL say so and SHALL link to Integrations. The step help SHALL say that OMRS also uses pypdfium2 to draw page images, which is not a reading step.

#### Scenario: pypdfium2 not installed

- **GIVEN** the `pdf-pypdfium2` extra is not installed
- **WHEN** the user opens the add choice of step 1
- **THEN** the choice MUST show "pypdfium2 (optional, not installed)" and a link to PDF readers in Integrations

#### Scenario: pypdfium2 installed

- **GIVEN** the `pdf-pypdfium2` extra is installed
- **WHEN** the user adds pypdfium2 and saves
- **THEN** `omrs.jsonc` MUST hold a `pdf_readers` list that contains `pypdfium2`

### Requirement: The panel says when OCR is off

When the OCR fallback is off, the panel SHALL say above step 2 that no page goes to OCR, so steps 2 to 5 have no effect. Every row SHALL stay visible and editable.

#### Scenario: OCR fallback off

- **GIVEN** `ocr_fallback_enabled` is `false`
- **WHEN** the panel renders
- **THEN** it MUST show "OCR fallback is off. No page goes to OCR, so steps 2 to 5 have no effect."
- **AND** every row of steps 2 to 5 MUST stay editable

### Requirement: The Studio Read document step shows the same panel with inherit states

The Studio Read document step SHALL show its OCR read options in the Page routing panel, in the same steps and order. Each row SHALL offer "Inherit" and SHALL name the inherited Settings value and its source. The panel SHALL say that "Inherit" uses the value from Settings › Document reading.

#### Scenario: Inherited switch

- **GIVEN** a user profile whose Read document step does not set `ocr_skip_blank_pages` and Settings holds the default
- **WHEN** the user opens the step in Studio
- **THEN** the Skip blank pages row MUST show "Inherit" selected and "Inherit from Settings: On (default)"

#### Scenario: Step sets its own value

- **WHEN** the user chooses Off for Skip blank pages in the step and saves the pipeline
- **THEN** the step MUST hold `"ocr_skip_blank_pages": false`
- **AND** the Settings value MUST NOT change

#### Scenario: Non-Latin inherit wording

- **WHEN** the user opens the Non-Latin pages choice of a step
- **THEN** the first choice MUST read "Inherit from Settings: off" and no choice MUST carry the word "default"

#### Scenario: Built-in profile

- **WHEN** the user opens the Read document step of a built-in profile
- **THEN** every panel control MUST be read-only

### Requirement: The panel renders at desktop and phone widths

The panel SHALL fit a 1280 px window and a 390 px window with no horizontal page scroll, in Settings and in Studio. At 390 px every list button and cut box SHALL stay reachable and labelled for screen readers.

#### Scenario: Phone width in Settings

- **WHEN** Settings › Document reading renders at 390 px
- **THEN** every step, row, list button and cut box MUST be visible without horizontal scrolling

#### Scenario: Phone width in Studio

- **WHEN** the Studio Read document step renders at 390 px
- **THEN** every step, row and Inherit choice MUST be visible without horizontal scrolling
