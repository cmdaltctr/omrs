## Purpose

Let the operator define named routers that ask a decision model, page by page, whether a page's text can be kept, and send each rejected page alone to OCR, under explicit privacy rules.

## ADDED Requirements

### Requirement: A router is a named recipe

A router SHALL have a name, a decision model entry name, a question, a threshold between 0 and 1, a "sees the page image" flag, a page scope (`rescued` or `all-text`) and the maximum number of page characters sent. A "yes" answer SHALL keep the page text. A "no" answer SHALL send that page to OCR. A page is "no" when P(yes) is below the threshold.

#### Scenario: Router from the Experiment 43 template

- **WHEN** the user creates a router from the "Text matches the page image" template
- **THEN** the question SHALL be "Does the text match the text written or printed on the page image?"
- **AND** the image flag SHALL be on and the character limit SHALL be 2,000
- **AND** the threshold field SHALL show the Experiment 43 value with the note "fitted on Experiment 33 documents, not confirmed"

#### Scenario: Below the threshold

- **GIVEN** a router with threshold 0.17
- **WHEN** a page gets P(yes) 0.05
- **THEN** that page SHALL be sent to OCR

### Requirement: Several routers can exist and are picked by name

The operator SHALL be able to create, rename and delete routers. The host default `document_router` (env `DOCUMENT_ROUTER`) SHALL name one router or be empty. Empty SHALL mean no router, and SHALL be the default. A Read document step SHALL be able to pick a router by name or turn routing off for that step.

#### Scenario: No router by default

- **WHEN** no source sets `document_router`
- **THEN** no page SHALL be judged
- **AND** reading SHALL behave exactly as before this change

#### Scenario: Delete a router in use

- **GIVEN** a saved profile's Read document step names router `handwriting`
- **WHEN** the user deletes `handwriting`
- **THEN** the delete SHALL be refused and the message SHALL name the profile

### Requirement: A router judges rescued pages after the rescue

With a router selected and scope `rescued` or `all-text`, every page that the rescue tiers return SHALL be judged before routing. The flagged count SHALL then equal the number of "no" pages, not zero. The count before the rescue SHALL stay under its diagnostic key. A page that page routing already sends to OCR SHALL NOT be judged.

#### Scenario: Junk page rejected

- **GIVEN** a router and a rescued handwritten page whose text does not match its image
- **WHEN** the PDF is read
- **THEN** that page SHALL be sent to OCR
- **AND** the rescued pages that the router accepts SHALL keep their text

### Requirement: A router can judge native page text

With scope `all-text`, the router SHALL also judge each page that pdf-inspector read with native text and did not flag. A "no" page SHALL be sent to OCR in the same way as a rescued page.

#### Scenario: Native page rejected

- **GIVEN** scope `all-text` and a native page whose text does not match its image
- **WHEN** the PDF is read
- **THEN** that page SHALL be sent to OCR

### Requirement: A rejected page goes to OCR on its own

Each "no" page SHALL go through the page path: the local OCR tier, then the OCR engine list for pages it escalates. This SHALL hold under both routing units. "No" pages SHALL NOT count toward the document-unit page fraction or confidence rules, and SHALL NOT send any other page of the document to OCR.

#### Scenario: One junk page in a long document

- **GIVEN** the `document` unit and a 1,000-page PDF where the router rejects 1 page
- **WHEN** the PDF is read
- **THEN** exactly 1 page SHALL go to OCR
- **AND** the other 999 pages SHALL keep their text

#### Scenario: Many junk pages do not trigger the whole-document rule

- **GIVEN** the `document` unit, a 20-page PDF and 5 rejected pages
- **WHEN** the PDF is read
- **THEN** exactly those 5 pages SHALL go to OCR

### Requirement: A hosted router needs an explicit opt-in

A router whose decision model is hosted SHALL run only when its "send pages off this machine" opt-in is on. Without the opt-in the router SHALL NOT send any request and SHALL degrade. The Settings row of every hosted router SHALL warn that page text, and page images when the image flag is on, go to the named third party.

#### Scenario: Opt-in missing

- **GIVEN** a router on the hosted `jev` entry with the opt-in off
- **WHEN** a PDF is read
- **THEN** no request SHALL leave the machine
- **AND** the document diagnostics SHALL give the reason `needs-opt-in`

#### Scenario: Hosted image router marked experimental

- **GIVEN** a hosted router with the image flag on
- **WHEN** the Router section renders
- **THEN** the row SHALL show the off-machine warning and an "experimental" label

### Requirement: A router that cannot run leaves the page as today

When a router cannot run for a file (entry unknown, unreachable, a model check failed, the smoke test failed, the opt-in missing), the reader SHALL behave as with no router and SHALL record the reason once per file. A single failed page request SHALL keep that page's text and count it as unjudged. No file SHALL fail because of a router.

#### Scenario: Server down

- **GIVEN** a router whose local server is not running
- **WHEN** a PDF with rescued pages is read
- **THEN** the rescue SHALL behave as before this change
- **AND** the diagnostics SHALL give the reason `unreachable`

### Requirement: A router enters the source index identity only when selected

With a router selected, the identity SHALL hold the router's question, threshold, image flag, scope, character limit and the decision model's kind and model identity. It SHALL NOT hold the router name, the address or the key. With no router, the block SHALL be absent, so existing digests do not change.

#### Scenario: Renaming does not reindex

- **WHEN** the user renames a router in use
- **THEN** source digests SHALL NOT change

#### Scenario: Threshold change reindexes PDF sources

- **WHEN** the threshold of the selected router changes
- **THEN** PDF sources SHALL be processed again on the next explicit ingest

### Requirement: Router diagnostics SHALL be honest

A document read with a router SHALL carry scalar counts of pages judged, accepted, rejected and unjudged, and the router status. These keys SHALL be in the central embedding exclusion set. Diagnostics SHALL NOT claim OCR read a page that OCR did not read.

#### Scenario: Counts stamped

- **GIVEN** 44 rescued pages, 40 rejected, 4 accepted
- **WHEN** the document is emitted
- **THEN** the counts SHALL be 44 judged, 4 accepted, 40 rejected, 0 unjudged
- **AND** none SHALL appear in the embedded text
