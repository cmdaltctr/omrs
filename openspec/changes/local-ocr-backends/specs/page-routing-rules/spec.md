## Purpose

Run every page-routing decision of the page unit (blank pages, maths pages, non-Latin pages, and later routers) as ordered, registered page rules on one hook, with the same results as the hand-wired code they replace.

## ADDED Requirements

### Requirement: Page rules SHALL run in registered order on one hook

The page unit SHALL run every active page rule in ascending `order` on one hook. A rule SHALL receive the file, the page evidence, the flagged pages, the routed pages (flagged pages that earlier rules did not drop), the injected settings and the OCR engine availability. A rule SHALL return the pages it drops, the pages it sends direct to the OCR engine list, and its own state. The page unit SHALL contain no call to a specific rule.

#### Scenario: Built-in order

- **WHEN** the rule registry is read
- **THEN** the built-in rules SHALL be `blank` (10), `maths` (20) and `non_latin` (30), in that order

#### Scenario: No hand-wired rule

- **WHEN** the import check reads `ocr_routing.py`
- **THEN** it SHALL find no import of a rule module

### Requirement: Rule results SHALL combine by fixed semantics

A page dropped by a rule SHALL leave the routed set of every later rule. A rule's direct set SHALL lose the pages earlier rules dropped. The direct pages SHALL be the union of every rule's direct set. The local tier SHALL read the routed pages that are not direct. A page in more than one direct set SHALL be sent once.

#### Scenario: Blank maths page

- **GIVEN** maths routing on and a flagged page that is blank and has a maths font
- **WHEN** the PDF is ingested
- **THEN** the page SHALL count blank
- **AND** it SHALL go to neither the local tier nor the OCR engine list

#### Scenario: Maths and non-Latin page

- **GIVEN** maths routing on, `ocr_non_latin_routing=always`, and a flagged page with a maths font
- **WHEN** the PDF is ingested
- **THEN** the page SHALL appear once in the page-listed request

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

The identity contribution of each built-in rule SHALL come from its descriptor and SHALL keep its shape: the blank-test version inside the `ocr_routing` block, the maths block present for every source, and the non-Latin `parser` entry present only for PDFs when the mode is not `off`. A rule with no identity contribution SHALL add nothing.

#### Scenario: Digests unchanged

- **WHEN** the digest pins for the default install, maths off, non-Latin `detect` and non-Latin `always` run
- **THEN** each digest SHALL equal its pinned value

### Requirement: A new page rule SHALL need one file, one descriptor and one registration

Adding a page rule SHALL need its own module, one descriptor entry and one `register()` line, plus its tests. It SHALL need no edit to the page unit, the identity builders or the key lists.

#### Scenario: Fake rule added in a test

- **GIVEN** a test that registers a fake rule with order 40 and a descriptor
- **WHEN** a PDF is ingested
- **THEN** the fake rule SHALL run after `non_latin`
- **AND** no other module SHALL be patched for it to run
