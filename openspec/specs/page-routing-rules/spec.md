# page-routing-rules Specification

## Purpose
Run every page-routing decision of the page unit (blank pages, maths pages, non-Latin pages, and later routers) as ordered, registered page rules on one hook, with the same results as the hand-wired code they replace.

## Requirements

### Requirement: Page rules SHALL run in registered order on one hook

The page unit SHALL run every active page rule in ascending `order` on one hook. A rule SHALL receive the file, page evidence, flagged pages, routed pages (flagged pages not dropped earlier), settings, OCR engine availability and, with a router selected, the page judge. A rule SHALL return the pages it drops, sends direct to the OCR engine list or adds to the route, and its own state. The page unit SHALL contain no call to a specific rule.

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

### Requirement: A rule MAY add a post-check reason to local results

A rule MAY supply a post-check. The shared escalation rule SHALL run each post-check on each local result, in rule order, and SHALL add the reason it returns. Reasons SHALL keep their names.

#### Scenario: Non-Latin post-check

- **GIVEN** `ocr_non_latin_routing=detect`, an available OCR engine and the default backend list
- **WHEN** the local tier returns 400 Devanagari letters at confidence 0.95
- **THEN** the page SHALL escalate with the reason `non_latin_output`

### Requirement: A rule MAY degrade its direct pages to the local tier

A rule MAY supply a degrade hook. When the OCR engine list does not read a direct page, the page unit SHALL pass the page to the degrade hook of the first rule that sent it direct, and to no other rule. Pages returned by the hook SHALL be read by the local tier without post-checks.

#### Scenario: Non-Latin degrade

- **GIVEN** `ocr_non_latin_routing=always` and no available OCR engine
- **WHEN** a flagged page is read
- **THEN** the local tier SHALL read it
- **AND** one warning SHALL name the missing engine

#### Scenario: Maths claims first

- **GIVEN** maths routing on, `always`, no available OCR engine, and a flagged maths page
- **WHEN** the PDF is ingested
- **THEN** the non-Latin degrade hook SHALL NOT receive that page

### Requirement: Each rule SHALL stamp its own diagnostics

Each rule MAY stamp a count into the document metadata after the pages are placed. The keys, values and presence rules SHALL equal those before this change: `pages_maths_font` from the maths rule and `pages_non_latin` from the non-Latin rule only when its mode is not `off`.

#### Scenario: Stamps unchanged

- **WHEN** the golden fixture PDF is ingested under each rule combination
- **THEN** every metadata key and value SHALL equal the snapshot taken before this change

### Requirement: A failing rule SHALL fail as before when built in and SHALL be skipped when external

An exception from a built-in rule SHALL reach the caller as before this change. An exception from a discovered rule SHALL skip that rule for the file, log one warning, and mark the rule broken in health. The other rules SHALL still run.

#### Scenario: External rule raises

- **GIVEN** an enabled discovered rule that raises `ValueError` on every file
- **WHEN** a PDF is ingested
- **THEN** the file SHALL be read by the other rules and tiers
- **AND** health SHALL show the rule broken with the error

### Requirement: Rule identity SHALL keep each rule's existing shape

The identity contribution of each built-in rule SHALL come from its descriptor and SHALL keep its shape: the blank-test version inside the `ocr_routing` block, the maths block present for every source, and the non-Latin `parser` entry present only for PDFs when the mode is not `off`. The blank rule's switch SHALL add a `parser` entry `skip_blank_pages: false` only for PDFs and only when the switch is off. A rule with no identity contribution SHALL add nothing.

#### Scenario: Digests unchanged

- **WHEN** the digest pins for the default install, maths off, non-Latin `detect` and non-Latin `always` run
- **THEN** each digest SHALL equal its pinned value

#### Scenario: Skip-blank switch off

- **WHEN** the digest pin for `ocr_skip_blank_pages=false` runs on a PDF source
- **THEN** the `parser` block SHALL hold `skip_blank_pages: false` and the digest SHALL equal its new pinned value
- **AND** a Markdown source under the same settings SHALL keep the default-install digest

### Requirement: A new page rule SHALL need one file, one descriptor and one registration

Adding a page rule SHALL need its own module, one descriptor entry and one `register()` line, plus its tests. It SHALL need no edit to the page unit, the identity builders or the key lists, except the identity builder and the stamp keys of a rule that has its own identity entry or stamp.

#### Scenario: Fake rule added in a test

- **GIVEN** a test that registers a fake rule with order 50 and a descriptor
- **WHEN** a PDF is ingested
- **THEN** the fake rule SHALL run after `document_router`
- **AND** no other module SHALL be patched for it to run

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

### Requirement: Built-in page rules SHALL keep a fixed order that no setting changes

The built-in rules SHALL run in the order of their descriptors: `blank` (10), `maths` (20), `non_latin` (30), `document_router` (40). No setting, part option, Settings control or Read document step option SHALL change that order. A rule that a setting switches off SHALL keep its place and SHALL return an empty outcome.

#### Scenario: No order setting exists

- **WHEN** an operator lists the document-reading keys and the Read document step options
- **THEN** none SHALL name or change the order of the page rules

#### Scenario: A rule switched off keeps its place

- **GIVEN** `ocr_skip_blank_pages` is `false`
- **WHEN** the page rules run on a PDF
- **THEN** the `blank` rule SHALL run first and return no dropped page
- **AND** the `maths` and `non_latin` rules SHALL see every flagged page as routed
