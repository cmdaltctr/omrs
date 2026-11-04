## Purpose

Let the operator define named routers that ask a decision model, page by page, whether a page's text can be kept, and send each rejected page alone to OCR through the page rule hook, under explicit privacy rules.

## ADDED Requirements

### Requirement: A router is a named recipe

A router SHALL have a name, a decision model entry name, a question, a threshold between 0 and 1, a "sees the page image" flag and the maximum number of page characters sent. A "yes" answer SHALL keep the page text. A "no" answer SHALL send that page to OCR. A page is "no" when P(yes) is below the threshold.

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

### Requirement: The router is a page rule at order 40

The router SHALL be a built-in page rule named `document_router` with order 40, registered through one descriptor entry and one `register()` line. It SHALL run after the blank, maths and non-Latin rules. The page unit SHALL contain no call to it. With no router selected, the rule SHALL return an empty outcome without reading a page or calling a decision model, and SHALL stamp nothing.

#### Scenario: No router, nothing judged

- **GIVEN** no router is selected for the source
- **WHEN** a PDF is read
- **THEN** no page SHALL be judged
- **AND** every metadata key and every digest SHALL equal its value before this change

#### Scenario: Registered like any page rule

- **WHEN** the registry and the descriptor table are read
- **THEN** `document_router` SHALL appear in both with order 40 and `adds_pages` true
- **AND** its name SHALL appear in production code only in its own module, its descriptor entry and its `register()` line, plus the settings that name it

### Requirement: A router judges the unflagged pages that have text

With a router selected, the rule SHALL judge each page that has non-blank native text, that the scan did not flag, and that no earlier rule claimed (dropped, sent direct or added). It SHALL NOT judge a flagged page, because a flagged page already goes to OCR. It SHALL NOT judge OCR output. A page is "no" when P(yes) is below the threshold.

#### Scenario: Junk native page rejected

- **GIVEN** a selected router and an unflagged page whose native text does not match its image
- **WHEN** the PDF is read
- **THEN** that page SHALL be sent to OCR
- **AND** the unflagged pages that the router accepts SHALL keep their native text

#### Scenario: Flagged pages are not judged

- **GIVEN** a selected router and a PDF with 3 flagged pages and 10 unflagged pages with text
- **WHEN** the PDF is read
- **THEN** the router SHALL judge the 10 unflagged pages only

#### Scenario: Pages of earlier rules are not judged

- **GIVEN** a selected router and two pages that are in the claimed set of earlier rules
- **WHEN** the PDF is read
- **THEN** neither page SHALL be judged

### Requirement: A rejected page goes to OCR on its own

Each "no" page SHALL be returned in the rule's `add` set and SHALL go to the OCR engine list once, in the page-listed request, like a direct page. When no engine reads it, the local tier SHALL read it. "No" pages SHALL NOT send any other page of the document to OCR.

#### Scenario: One junk page in a long document

- **GIVEN** a 1,000-page PDF with no flagged page where the router rejects 1 page
- **WHEN** the PDF is read
- **THEN** exactly 1 page SHALL go to OCR
- **AND** the other 999 pages SHALL keep their text

#### Scenario: Several junk pages stay page by page

- **GIVEN** a 20-page PDF and 5 rejected pages
- **WHEN** the PDF is read
- **THEN** exactly those 5 pages SHALL go to OCR

### Requirement: The router help text states the cost

The router's help text and `docs/guides/reading-parts.md` SHALL state that the router judges every unflagged text page that no earlier rule claimed, at about 3.6 s per judged page with the local model, and that Experiment 43 sent about 2.7% of healthy pages to OCR. No setting SHALL change which pages are judged.

#### Scenario: Cost visible

- **WHEN** the Router form renders
- **THEN** its help text SHALL show the per-page time and the share of healthy pages sent to OCR

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

When a router cannot run for a file (entry unknown, unreachable, a model check failed, the smoke test failed, the opt-in missing, no page renderer for an image router), the reader SHALL behave as with no router and SHALL record the reason once per file in `router_status`. A single failed page request SHALL keep that page's text and count it as unjudged. No file SHALL fail because of a router.

#### Scenario: Server down

- **GIVEN** a router whose local server is not running
- **WHEN** a PDF with unflagged text pages is read
- **THEN** reading SHALL behave as before this change
- **AND** the diagnostics SHALL give the reason `unreachable`

### Requirement: A router enters the source index identity only when selected

With a router selected, the `parser` block of a PDF source SHALL hold an entry `document_router` with the router's question, threshold, image flag, character limit, the decision model's kind and model identity, and the rule version. It SHALL NOT hold the router name, the address, the key or the opt-in. With no router, or for a source that is not a PDF, the entry SHALL be absent, so existing digests do not change.

#### Scenario: Renaming does not reindex

- **WHEN** the user renames a router in use
- **THEN** source digests SHALL NOT change

#### Scenario: Threshold change reindexes PDF sources

- **WHEN** the threshold of the selected router changes
- **THEN** PDF sources SHALL be processed again on the next explicit ingest

### Requirement: Router diagnostics SHALL be honest

A document read with a router SHALL carry the scalar counts `router_pages_judged`, `router_pages_accepted`, `router_pages_rejected` and `router_pages_unjudged`, and `router_status`. These keys SHALL be in the central embedding exclusion set and SHALL stay out of the index identity key list, so a default install keeps every digest. With no router, the keys SHALL be absent. Diagnostics SHALL NOT claim OCR read a page that OCR did not read.

#### Scenario: Counts stamped

- **GIVEN** 44 judged pages, 40 rejected, 4 accepted
- **WHEN** the document is emitted
- **THEN** the counts SHALL be 44 judged, 4 accepted, 40 rejected, 0 unjudged
- **AND** none SHALL appear in the embedded text
