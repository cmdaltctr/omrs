## MODIFIED Requirements

### Requirement: Page rules SHALL run in registered order on one hook

The page unit SHALL run every active page rule in ascending `order` on one hook. A rule SHALL receive the file, the page evidence, the flagged pages, the routed pages (flagged pages that earlier rules did not drop), the injected settings, the OCR engine availability and, when a router is selected, the page judge. A rule SHALL return the pages it drops, the pages it sends direct to the OCR engine list, the pages it adds to the route, and its own state. The page unit SHALL contain no call to a specific rule.

#### Scenario: Built-in order

- **WHEN** the rule registry is read
- **THEN** the built-in rules SHALL be `blank` (10), `maths` (20), `non_latin` (30) and `document_router` (40), in that order

#### Scenario: No hand-wired rule

- **WHEN** the import check reads `ocr_routing.py`
- **THEN** it SHALL find no import of a rule module

### Requirement: Rule results SHALL combine by fixed semantics

A page dropped by a rule SHALL leave the routed set of every later rule. A rule's direct set SHALL lose the pages earlier rules dropped. The direct pages SHALL be the union of every rule's direct set. The local tier SHALL read the routed pages that are not direct, and the pages that rules added. A page in more than one direct set SHALL be sent once. A page that a rule adds SHALL have native text, SHALL NOT be flagged and SHALL NOT be dropped or direct. An added page SHALL be read once, whatever the number of rules that add it.

#### Scenario: Blank maths page

- **GIVEN** maths routing on and a flagged page that is blank and has a maths font
- **WHEN** the PDF is ingested
- **THEN** the page SHALL count blank
- **AND** it SHALL go to neither the local tier nor the OCR engine list

#### Scenario: Maths and non-Latin page

- **GIVEN** maths routing on, `ocr_non_latin_routing=always`, and a flagged page with a maths font
- **WHEN** the PDF is ingested
- **THEN** the page SHALL appear once in the page-listed request

#### Scenario: An added page goes to the local tier

- **GIVEN** a 20-page PDF with no flagged page and a rule that adds page 7
- **WHEN** the PDF is ingested
- **THEN** the local tier SHALL read page 7 only
- **AND** the other 19 pages SHALL keep native text

#### Scenario: A stray added page is refused

- **GIVEN** a flagged page and a rule that adds it
- **WHEN** the rule runs
- **THEN** a built-in rule SHALL fail the file as for a stray `drop`
- **AND** a discovered rule SHALL be skipped for the file with one warning

### Requirement: A new page rule SHALL need one file, one descriptor and one registration

Adding a page rule SHALL need its own module, one descriptor entry and one `register()` line, plus its tests. It SHALL need no edit to the page unit, the identity builders or the key lists, except the identity builder and the stamp keys of a rule that has its own identity entry or stamp.

#### Scenario: Fake rule added in a test

- **GIVEN** a test that registers a fake rule with order 50 and a descriptor
- **WHEN** a PDF is ingested
- **THEN** the fake rule SHALL run after `document_router`
- **AND** no other module SHALL be patched for it to run

## ADDED Requirements

### Requirement: A rule MAY add pages to the route

A rule MAY return pages in `add`. The page unit SHALL treat an added page as a flagged page for reading: the local tier reads it with the backend list and post-checks, a page the local tier does not keep goes to the OCR engine list in the one page-listed request, and a page that no tier reads keeps its native text and counts unresolved. `pages_needing_ocr` SHALL stay the count of flagged pages. A rule that adds pages SHALL declare it with `adds_pages` on its descriptor and its `register()` line.

#### Scenario: Added page escalates

- **GIVEN** a rule that adds page 7 and a local result below the backend cut
- **WHEN** the PDF is ingested
- **THEN** page 7 SHALL be sent to the OCR engine list in the page-listed request
- **AND** `pages_needing_ocr` SHALL NOT count page 7

#### Scenario: Declared fact matches registration

- **WHEN** the pin test compares the `document_router` descriptor and its `register()` line
- **THEN** both SHALL declare `adds_pages`
