## ADDED Requirements

### Requirement: An image-based candidate SHALL ask whether the text matches the page

A candidate that reads the page image SHALL receive the page image and the rescued page text. It SHALL answer one question: does this text match the text on the page. The question SHALL NOT ask whether the text is readable, natural or prose. The protocol SHALL state the exact question wording, and the image render settings, before any page is scored.

#### Scenario: Faithful copy of a non-prose page

- **WHEN** the rescued text is an accurate copy of a page that holds chart numbers, formulas or verse
- **THEN** the question is answered for the match with the page, not for the style of the text
- **AND** the page is not flagged for being non-prose

#### Scenario: Question wording is fixed before the run

- **WHEN** the first page is scored
- **THEN** `protocol.md` and `plan.json` already hold the question wording and the render settings
- **AND** a change to either needs a dated amendment

### Requirement: A model that reads images SHALL run with its projector file and a checked build

A local candidate that takes page images SHALL run on `llama-server` with both its model file and its projector (`mmproj`) file. Before any page is scored, the run SHALL check the llama.cpp build against the build named in `plan.json`, and the SHA-256 value of both files against the values recorded in `plan.json`. The server SHALL bind to `127.0.0.1` and take one request at a time. The model file SHALL be 8-bit or higher.

#### Scenario: Projector file missing

- **WHEN** the server starts without the projector file
- **THEN** the run stops before any page is scored
- **AND** the report does not use text-only scores as image scores

#### Scenario: A file hash differs from the plan

- **WHEN** the SHA-256 value of the model file or the projector file differs from `plan.json`
- **THEN** the run stops before any page is scored

#### Scenario: A smoke request proves the image is read

- **WHEN** the server is up and before the first scored page
- **THEN** the run sends one page image with a text that is known to be wrong for it, and one with the right text
- **AND** the two answers differ in the expected direction, or the run stops

### Requirement: Development and confirmation SHALL use separate documents

The evaluation SHALL use already-scored documents (the Experiment 38 and Experiment 42 documents) only to fit the threshold and to settle render settings. It SHALL then freeze the threshold and the settings in `plan.json`. The confirmation stage SHALL use documents that appear in no earlier experiment, and SHALL NOT refit anything.

#### Scenario: Threshold fitted on seen documents

- **WHEN** the development stage ends
- **THEN** the threshold, question wording and render settings are written to `plan.json` under a dated amendment
- **AND** no confirmation page is scored before that amendment is committed

#### Scenario: A confirmation document was seen before

- **WHEN** a candidate confirmation document matches a document of Experiment 33, 38 or 42
- **THEN** it is excluded from the confirmation stage

### Requirement: A handwritten or ambiguous page needs two agreeing references

A page that the Experiment 33 reference rule labels `ambiguous`, and every page of a document that the protocol lists as handwritten, SHALL be labelled from two transcriptions: the Experiment 33 reference, and a second one by a different engine on the operator's machine. Equal classes give the label. Different classes give `ambiguous`, and the page is excluded. Other pages keep the Experiment 33 label.

#### Scenario: References disagree on a handwritten page

- **WHEN** the two transcriptions give different classes for a page of a handwritten document
- **THEN** the page is `ambiguous`
- **AND** the report counts it in the exclusions

#### Scenario: A page the first reference could not label

- **WHEN** the Experiment 33 rule labels a page `ambiguous` and the second transcription gives a class that the rule accepts
- **THEN** the page takes that class only if the first reference does not contradict it
- **AND** the report counts the page as relabelled

#### Scenario: Handwriting is not silently dropped

- **WHEN** a stage excludes more than 30% of the pages of a document class
- **THEN** the report names the class and the share
- **AND** the report states that the result does not cover that class

### Requirement: The operator SHALL check a stratified sample of labels against the page images

Before the confirmation stage is scored, the operator SHALL check a stratified sample of labelled pages by eye against the page images, including handwriting pages and pages labelled `junk` and `healthy`. The sample list and the outcome SHALL be committed. A label error rate above the bound in `plan.json` SHALL stop the run.

#### Scenario: Labels pass the check

- **WHEN** the operator reviews the sample and the error rate is within the bound
- **THEN** the outcome is committed before the confirmation stage is scored

#### Scenario: Labels fail the check

- **WHEN** the error rate exceeds the bound
- **THEN** the confirmation stage is not scored
- **AND** the labels are redone under a dated amendment

### Requirement: Page images SHALL stay on the machine unless the operator approves a hosted service

A hosted candidate that receives page images SHALL need the operator's approval in a dated amendment that names the provider, the images sent and the documents they come from. Documents that hold personal records SHALL NOT be sent without that approval. Rendered page images SHALL be stored in a gitignored folder.

#### Scenario: Hosted image candidate proposed

- **WHEN** a candidate would send page images to a hosted service
- **THEN** it is excluded until the operator approves it in a dated plan amendment

#### Scenario: Page renders in the repository

- **WHEN** the run writes page renders
- **THEN** they go to a gitignored folder
- **AND** no render is committed

### Requirement: Results SHALL be reported at page level and at document level

The report SHALL state, for each arm, the junk pages caught and the healthy pages flagged, and the documents that would route to OCR at the 10% page share and at one or more flagged pages. It SHALL name each usable document that a rule would route, with the pages of OCR that this would cost. The report SHALL NOT recommend a routing unit; that choice belongs to the page versus document routing experiment.

#### Scenario: One false flag on a short document

- **WHEN** a usable document of 6 pages has one healthy page flagged
- **THEN** the report shows the document as routed under the 10% share rule
- **AND** shows the cost as 1 page under a page-level rule and 6 pages under a document-level rule

#### Scenario: Routing unit not chosen here

- **WHEN** the report is written
- **THEN** it states the result for both units
- **AND** it leaves the choice of unit to the page versus document routing experiment
