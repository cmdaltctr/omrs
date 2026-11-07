## ADDED Requirements

### Requirement: Document reading edits Skip blank pages

Step 2 of the Page routing panel SHALL show a Skip blank pages switch for `ocr_skip_blank_pages`, default On. Its help line SHALL say that a blank flagged page keeps its native text and costs no OCR, and that Off sends blank pages to OCR like any flagged page. A save SHALL follow the restart, lock and identity rules of the other Document reading rows.

#### Scenario: Default shown

- **GIVEN** no source sets `ocr_skip_blank_pages`
- **WHEN** step 2 renders
- **THEN** the Skip blank pages row MUST show On, the source default and the default On

#### Scenario: Turn it off

- **WHEN** the user turns Skip blank pages off and presses Save
- **THEN** `omrs.jsonc` MUST hold `"ocr_skip_blank_pages": false`
- **AND** the row MUST show "Restart to apply"

#### Scenario: Use default

- **GIVEN** `omrs.jsonc` holds `"ocr_skip_blank_pages": false`
- **WHEN** the user presses "Use default"
- **THEN** `omrs.jsonc` MUST no longer hold `ocr_skip_blank_pages`

### Requirement: Document reading routes carry the skip-blank switch

`GET /v1/settings/document-reading` SHALL return an `ocr_skip_blank_pages` entry with the value in force, the saved value, the source, the lock state and the default `true`. `PUT` SHALL accept `true`, `false` or `null` for it and SHALL answer 400 for any other value, with no submitted value in the message.

#### Scenario: Read the switch

- **WHEN** a session with the read scope sends `GET /v1/settings/document-reading`
- **THEN** the answer MUST hold an `ocr_skip_blank_pages` entry with the default `true`

#### Scenario: Text refused

- **WHEN** a `PUT` sets `ocr_skip_blank_pages` to the text `"no"`
- **THEN** the server MUST answer 400 with "ocr_skip_blank_pages: The value must be true or false."
- **AND** the file MUST NOT change

## MODIFIED Requirements

### Requirement: Document reading shows the reading settings and their state

The Document reading section SHALL show one row for each of `pdf_readers`, `ocr_fallback_enabled`, `ocr_routing_unit`, `ocr_engines`, `ocr_skip_blank_pages`, `ocr_maths_routing_enabled`, `ocr_non_latin_routing`, `document_router` and `ocr_local_backends`, inside the Page routing panel. Each row SHALL show the value in force since launch, its source and the default. When the saved file value differs from the value in force, the row SHALL show the saved value and "Restart to apply".

#### Scenario: Value saved but not yet in force

- **WHEN** the server launched with `pdf_readers` `["pdf_inspector", "liteparse", "pypdf"]` and `omrs.jsonc` now holds `"pdf_readers": ["liteparse"]`
- **THEN** the PDF readers row MUST show `pdf_inspector, liteparse, pypdf` in force, `liteparse` saved and "Restart to apply"

#### Scenario: Rows inside the panel

- **WHEN** the section renders
- **THEN** every row named above MUST show inside the Page routing panel
- **AND** no PDF reading card and no OCR card MUST show

### Requirement: Document reading shows non-Latin routing

Settings › Document reading SHALL show `ocr_non_latin_routing` in step 2 "Pages with no usable text" of the Page routing panel as a choice of `off`, `detect` and `always`, with `off` labelled as the default. The row SHALL say that `detect` sees only text that already exists and does not catch scanned pages, and that `always` suits a collection known to be non-Latin. It SHALL follow the restart, lock and identity rules of the other Document reading rows.

#### Scenario: Row explains what detect cannot see

- **WHEN** the row renders
- **THEN** it SHALL say that `detect` does not catch scanned pages and SHALL name `always` for a known non-Latin collection

#### Scenario: Save always

- **WHEN** the user chooses `always` and saves
- **THEN** `omrs.jsonc` SHALL hold `"ocr_non_latin_routing": "always"`
- **AND** the row SHALL show "Restart to apply"

### Requirement: Document reading has a Router section

Settings › Document reading SHALL have a Router section. It SHALL show one row per router with its decision model, question, threshold, image flag. The user SHALL be able to create a router from blank or from the Experiment 43 template, edit, rename and delete it. The host router choice (a router name or "No router") SHALL show in step 3 "Pages that look fine" of the Page routing panel, not in the Router section.

#### Scenario: Choose the host router

- **WHEN** the user picks `handwriting` as the host router in step 3 and saves
- **THEN** `omrs.jsonc` SHALL hold `"document_router": "handwriting"`
- **AND** the row SHALL show "Restart to apply"

#### Scenario: Locked by the environment

- **GIVEN** `DOCUMENT_ROUTER` is set in the environment
- **WHEN** the section renders
- **THEN** the host choice in step 3 SHALL be read-only and SHALL name the variable

#### Scenario: Router section keeps the definitions only

- **WHEN** the Router section renders
- **THEN** it SHALL list the routers and offer create, edit, rename and delete
- **AND** it SHALL NOT show the host router choice

### Requirement: Document reading lists render at desktop and phone widths

The three list controls of the Page routing panel SHALL fit a 1280 px window and a 390 px window with no horizontal page scroll. At 390 px the move and remove buttons SHALL stay reachable and labelled for screen readers.

#### Scenario: Phone width

- **WHEN** the page renders at 390 px
- **THEN** every list row and its buttons SHALL be visible without horizontal scrolling

### Requirement: Document reading marks readers and engines that cannot run

The reader choice in step 1 of the Page routing panel SHALL mark each reader that is not installed and SHALL NOT let the user add it to the list until it is installed. The engine choices SHALL list the engines the server reports and SHALL mark each engine that is not provisioned, with the reason.

#### Scenario: Reader not installed

- **WHEN** the server reports `pypdfium2` as not installed
- **THEN** the reader choice in step 1 MUST show `pypdfium2` as not available with the reason and MUST NOT allow it to be added

#### Scenario: Engine not provisioned

- **WHEN** the server reports `dots-mocr` as not provisioned
- **THEN** the engine choices MUST mark `dots-mocr` as not available and MUST show the reason with its provision command

### Requirement: Document reading edits the reader list in order

Step 1 of the Page routing panel in Settings › Document reading SHALL show the reader list as ordered rows. The user SHALL be able to add a registered reader, remove a reader, and move a reader up or down. Each row SHALL say what its position does: the first installed reader reads, a later reader retries when the readers before it returned no text. A reader that is not installed SHALL show "Not installed" and a link to Integrations › PDF readers, and SHALL show an "Install" button when the app can install its extra. The page SHALL refuse to save an empty list.

#### Scenario: Move a reader up

- **GIVEN** the list `pdf_inspector, liteparse, pypdf`
- **WHEN** the user moves pypdf above LiteParse and saves
- **THEN** `omrs.jsonc` SHALL hold `"pdf_readers": ["pdf_inspector", "pypdf", "liteparse"]`
- **AND** the row SHALL show "Restart to apply"

#### Scenario: Empty list refused

- **WHEN** the user removes every reader and saves
- **THEN** the page SHALL show the reason and write nothing

### Requirement: Document reading edits the confidence cut of each local OCR backend

Settings › Document reading › Page routing, step 4 "Local OCR backends" SHALL give each listed backend row a "Confidence cut" number input from 0 to 1. An empty input SHALL show the backend's default cut and SHALL mean "use the default". A save SHALL write `ocr_local_cuts` with one entry for each filled input and SHALL keep the entries of backends that are not listed. A save with no entries SHALL remove the key.

#### Scenario: Default shown when unset

- **GIVEN** the list `pp-ocrv6-small` and no `ocr_local_cuts` in any source
- **WHEN** page routing step 4 renders
- **THEN** the PP-OCRv6 small row MUST show an empty "Confidence cut" input with the default 0.92 shown in it

#### Scenario: Set a cut and save

- **GIVEN** the list `pp-ocrv6-small, indra`
- **WHEN** the user types 0.95 in the Indra row and presses Save
- **THEN** `omrs.jsonc` MUST hold `"ocr_local_cuts": {"indra": 0.95}`
- **AND** step 4 MUST show "Restart to apply"

#### Scenario: Clear the last cut

- **GIVEN** `omrs.jsonc` holds `"ocr_local_cuts": {"indra": 0.95}` and the list `pp-ocrv6-small, indra`
- **WHEN** the user empties the Indra input and presses Save
- **THEN** `omrs.jsonc` MUST no longer hold `ocr_local_cuts`

#### Scenario: Value out of range

- **WHEN** the user types 1.5 in a cut input
- **THEN** the page MUST show "The cut must be a number from 0 to 1." beside the input
- **AND** Save MUST send nothing

#### Scenario: Locked by the environment

- **GIVEN** `OCR_LOCAL_CUTS` is set in the environment
- **WHEN** page routing step 4 renders
- **THEN** every cut input MUST be read-only and step 4 MUST show "Remove OCR_LOCAL_CUTS from the environment or .env to edit it here."

#### Scenario: Phone width

- **WHEN** the page renders at 390 px
- **THEN** every backend row, its cut input and its buttons MUST be visible without horizontal scrolling
- **AND** each cut input MUST have a label that names its backend
