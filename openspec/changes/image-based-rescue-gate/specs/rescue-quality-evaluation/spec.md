## ADDED Requirements

### Requirement: An image-based candidate SHALL ask whether the text matches the page

A candidate that reads the page image SHALL receive the page image and the rescued page text. It SHALL answer one question: does this text match the text on the page. The question SHALL NOT ask whether the text is readable or natural. The protocol SHALL state the question wording and the image settings before any page is scored.

#### Scenario: Faithful copy of a non-prose page

- **WHEN** the rescued text is an accurate copy of a page that holds chart numbers, formulas or verse
- **THEN** the page is not flagged for being non-prose

#### Scenario: Question fixed before the run

- **WHEN** the first page is scored
- **THEN** `protocol.md` and `plan.json` already hold the question wording and the image settings

### Requirement: A model that reads images SHALL run with its projector file and a checked build

A local candidate that takes page images SHALL run on `llama-server` with its model file and its projector file. Before any page is scored, the run SHALL check the build and the SHA-256 value of both files against `plan.json`. The server SHALL bind to `127.0.0.1`. The model file SHALL be 8-bit or higher.

#### Scenario: Projector file missing

- **WHEN** the server starts without the projector file
- **THEN** the run stops before any page is scored

#### Scenario: A file hash differs from the plan

- **WHEN** the SHA-256 value of a model file differs from `plan.json`
- **THEN** the run stops before any page is scored

#### Scenario: A smoke request proves the image is read

- **WHEN** the server is up and before the first scored page
- **THEN** one request with the right text and one with a wrong text on the same page image give different answers in the expected direction, or the run stops

### Requirement: Page images SHALL stay on the machine unless the operator approves a hosted service

A hosted candidate that receives page images SHALL need the operator's approval in `plan.json` that names the provider and the documents. The model id that the service returns SHALL be recorded for every page, and the run SHALL stop if it changes. The service key SHALL be read from the environment and SHALL NOT be written to any output. Rendered page images SHALL go to a gitignored folder.

#### Scenario: Hosted image candidate not approved

- **WHEN** a candidate would send page images to a hosted service and `plan.json` holds no approval
- **THEN** the candidate is not run

#### Scenario: Hosted model id changes during the run

- **WHEN** the returned model id differs from the first one recorded
- **THEN** the run stops

### Requirement: Results SHALL be reported at page level and at document level

The report SHALL state, for each arm, the junk pages caught and the healthy pages flagged, and the documents that would route to OCR at the 10% page share and at one flagged page. It SHALL name each usable document that a rule would route, with its OCR cost in pages.

#### Scenario: One false flag on a short document

- **WHEN** a usable document of 6 pages has one healthy page flagged
- **THEN** the report shows it as routed under the one-page rule and gives the cost in pages
