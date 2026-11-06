## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Rule identity SHALL keep each rule's existing shape

The identity contribution of each built-in rule SHALL come from its descriptor and SHALL keep its shape: the blank-test version inside the `ocr_routing` block, the maths block present for every source, and the non-Latin `parser` entry present only for PDFs when the mode is not `off`. The blank rule's switch SHALL add a `parser` entry `skip_blank_pages: false` only for PDFs and only when the switch is off. A rule with no identity contribution SHALL add nothing.

#### Scenario: Digests unchanged

- **WHEN** the digest pins for the default install, maths off, non-Latin `detect` and non-Latin `always` run
- **THEN** each digest SHALL equal its pinned value

#### Scenario: Skip-blank switch off

- **WHEN** the digest pin for `ocr_skip_blank_pages=false` runs on a PDF source
- **THEN** the `parser` block SHALL hold `skip_blank_pages: false` and the digest SHALL equal its new pinned value
- **AND** a Markdown source under the same settings SHALL keep the default-install digest
