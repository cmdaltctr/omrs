## ADDED Requirements

### Requirement: Providers shows a Decision models card

Settings › Providers SHALL show a Decision models card. It SHALL list each entry with its name, kind, model, image flag, local or hosted, and its key state (set, missing or not needed) without the key. The user SHALL be able to add, edit, test and remove an entry. A managed local entry SHALL show its model file, projector file and runtime state.

#### Scenario: Add a local entry

- **WHEN** the user adds a `llamacpp` entry with a Q8_0 model file and a projector file and saves
- **THEN** `omrs.jsonc` SHALL hold the entry under `decision_models`
- **AND** the card SHALL show "Not tested" until the user presses Test

#### Scenario: Remove an entry in use

- **GIVEN** router `handwriting` names entry `clef-local`
- **WHEN** the user removes `clef-local`
- **THEN** the removal SHALL be refused and the message SHALL name the router

### Requirement: Document reading has a Router section

Settings › Document reading SHALL have a Router section. It SHALL show the host router choice (a router name or "None"), and one row per router with its decision model, question, threshold, image flag. The user SHALL be able to create a router from blank or from the Experiment 43 template, edit, rename and delete it.

#### Scenario: Choose the host router

- **WHEN** the user picks `handwriting` as the host router and saves
- **THEN** `omrs.jsonc` SHALL hold `"document_router": "handwriting"`
- **AND** the row SHALL show "Restart to apply"

#### Scenario: Locked by the environment

- **GIVEN** `DOCUMENT_ROUTER` is set in the environment
- **WHEN** the section renders
- **THEN** the host choice SHALL be read-only and SHALL name the variable

### Requirement: Hosted routers carry a visible warning and an opt-in

A router on a hosted decision model SHALL show, on its row and in its form, that page text, and page images when the image flag is on, go to the named third party. Its form SHALL have a "send pages off this machine" checkbox that is off by default. The row SHALL say "Will not run" while the checkbox is off.

#### Scenario: Opt-in off

- **GIVEN** a new router on the hosted `jev` entry
- **WHEN** the user saves without ticking the checkbox
- **THEN** the row SHALL show the warning and "Will not run"

### Requirement: Router controls render at desktop and phone widths

The Decision models card and the Router section SHALL fit a 1280 px window and a 390 px window with no horizontal page scroll. The question text SHALL wrap.

#### Scenario: Phone width

- **WHEN** the Router section renders at 390 px
- **THEN** every row, warning and button SHALL be visible without horizontal scrolling
