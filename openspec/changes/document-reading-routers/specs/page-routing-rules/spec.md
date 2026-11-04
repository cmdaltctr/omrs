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

A page dropped by a rule SHALL leave the routed set of every later rule. A rule's direct set SHALL lose the pages earlier rules dropped. The direct pages SHALL be the union of every rule's direct set and added pages, minus every page that any rule dropped. The local tier SHALL read the routed pages that are not direct. A page in more than one direct or added set SHALL be sent once.

#### Scenario: Blank maths page

- **GIVEN** maths routing on and a flagged page that is blank and has a maths font
- **WHEN** the PDF is ingested
- **THEN** the page SHALL count blank
- **AND** it SHALL go to neither the local tier nor the OCR engine list

#### Scenario: Maths and non-Latin page

- **GIVEN** maths routing on, `ocr_non_latin_routing=always`, and a flagged page with a maths font
- **WHEN** the PDF is ingested
- **THEN** the page SHALL appear once in the page-listed request

#### Scenario: A later drop removes an added page

- **GIVEN** a rule at order 40 that adds page 7 and a rule at order 50 that drops page 7
- **WHEN** the PDF is ingested
- **THEN** page 7 SHALL go to neither the OCR engine list nor the local tier

### Requirement: A new page rule SHALL need one file, one descriptor and one registration

Adding a page rule SHALL need its own module, one descriptor entry and one `register()` line, plus its tests. It SHALL need no edit to the page unit, the identity builders or the key lists, except the identity builder and the stamp keys of a rule that has its own identity entry or stamp.

#### Scenario: Fake rule added in a test

- **GIVEN** a test that registers a fake rule with order 50 and a descriptor
- **WHEN** a PDF is ingested
- **THEN** the fake rule SHALL run after `document_router`
- **AND** no other module SHALL be patched for it to run

## ADDED Requirements

### Requirement: A rule MAY add pages to the OCR route when it declares it

A rule that declares `adds_pages` MAY return pages in `add`. An added page SHALL go to the OCR engine list once, in the one page-listed request, like a direct page. The local tier SHALL NOT read it first. A page that no engine reads SHALL go to the rule's degrade hook, and a page that no tier reads SHALL keep its native text and count unresolved. `pages_needing_ocr` SHALL stay the count of flagged pages.

#### Scenario: Added page goes to the engine

- **GIVEN** a 20-page PDF with no flagged page, an available OCR engine and a rule that adds page 7
- **WHEN** the PDF is ingested
- **THEN** page 7 SHALL be sent to the OCR engine list in the page-listed request
- **AND** the local tier SHALL read no page
- **AND** the 19 other pages SHALL keep native text

#### Scenario: No engine reads the added page

- **GIVEN** a rule that adds page 7 with a degrade hook and no available OCR engine
- **WHEN** the PDF is ingested
- **THEN** the local tier SHALL read page 7
- **AND** one warning SHALL name the missing engine

#### Scenario: The same page named twice

- **GIVEN** two rules that both add page 7
- **WHEN** the PDF is ingested
- **THEN** page 7 SHALL appear once in the page-listed request

### Requirement: A bad add outcome SHALL fail a built-in rule and skip a discovered rule

A rule that does not declare `adds_pages` and returns a non-empty `add` SHALL have returned a bad outcome. A valid added page SHALL be in the page scan, SHALL have non-blank text, SHALL NOT be flagged and SHALL NOT be claimed (dropped, sent direct or added) by an earlier rule. Any other page in `add` SHALL be a bad outcome. A built-in rule that returns a bad outcome SHALL fail the file. A discovered rule SHALL be skipped for the file, with one warning, and marked broken in health.

#### Scenario: A rule without the fact returns add

- **GIVEN** a rule whose descriptor does not declare `adds_pages` and that returns `add` of page 7
- **WHEN** the rule runs
- **THEN** a built-in rule SHALL fail the file
- **AND** a discovered rule SHALL be skipped for the file with one warning

#### Scenario: Stray added page

- **GIVEN** a rule with `adds_pages` that adds a flagged page, a page with no text, or a page that an earlier rule dropped
- **WHEN** the rule runs
- **THEN** the outcome SHALL be a bad outcome

### Requirement: A rule SHALL see the pages that earlier rules claimed

A rule SHALL receive `claimed`: the pages that earlier rules dropped, sent direct or added. The router SHALL skip them.

#### Scenario: Claimed page skipped

- **GIVEN** a page that an earlier rule added
- **WHEN** the router runs
- **THEN** the router SHALL NOT judge that page

#### Scenario: Declared fact matches registration

- **WHEN** the pin test compares the `document_router` descriptor and its `register()` line
- **THEN** both SHALL declare `adds_pages` and `has_degrade`
