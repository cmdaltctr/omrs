## ADDED Requirements

### Requirement: A router confirmation SHALL run the shipped router code path

A router confirmation SHALL decide each page with the shipped code: the page scan, the page-rule pipeline, the `document_router` rule, the shipped page judge, its adapter and the shipped page renderer, with injected settings. The harness SHALL NOT re-implement the question, the text head, the page render, the request or the threshold comparison. It MAY wrap the judge to record each answer without changing it. The router recipe in the plan SHALL equal the template the Settings page offers.

#### Scenario: Recorded answer

- **WHEN** the shipped judge returns P(yes) for a page
- **THEN** the harness records that value unchanged
- **AND** the page counts as rejected only when the shipped rule adds it to the OCR pages

#### Scenario: Plan recipe differs from the shipped template

- **WHEN** the plan question, image flag, character limit or threshold differs from the shipped template
- **THEN** the run stops before any request

### Requirement: Router confirmation labels SHALL be made on the machine and frozen before scoring

Page labels SHALL come from a local reference transcription and the Experiment 33 token rule, imported by path with a pinned SHA-256, scored on the text the router reads. No page text or image SHALL leave the machine for labelling. The labels, the label review and the set check SHALL be committed before any router score exists.

#### Scenario: A router score exists

- **WHEN** a router score file exists
- **THEN** the labelling steps refuse to run

#### Scenario: Labels not frozen

- **WHEN** the labels, the review or the set check is missing, not committed or incomplete
- **THEN** no page is scored

### Requirement: A confirmation runner SHALL refuse to score without its preconditions

Every scoring run SHALL check, before any request, that every required decision has a dated approval, that each arm threshold equals its frozen value, that `plan.json` is committed, and that a runtime check record passed for the same plan, inputs, labels, model and runner. For a local image model that record SHALL include a passing check without the projector file. A hosted arm SHALL also need its dated approval, checked before any request.

#### Scenario: Threshold differs from the frozen value

- **WHEN** a scoring run starts with a threshold that is not the frozen value
- **THEN** the run stops and no request is sent

#### Scenario: No passing runtime check

- **WHEN** the runtime check record is missing, failed or made for another identity
- **THEN** the run stops and no request is sent

### Requirement: A confirmation runner SHALL enforce its stop rules in code

The time, cost and failure stop rules in `plan.json` SHALL be checked by the runner, not only stated in the protocol. A projected hosted cost over the limit SHALL stop the run before its first request. A memory reading the runner cannot parse SHALL stop the run.

#### Scenario: Projected time over the limit

- **WHEN** the projected time for the pages left passes the limit
- **THEN** the run stops after the current answer is saved

#### Scenario: Memory tool prints no percentage

- **WHEN** `memory_pressure` prints no free percentage
- **THEN** the run stops

### Requirement: A confirmation runner SHALL check each page against the prepared inputs

Before the router reads a document, the runner SHALL compare the PDF SHA-256 and each page text hash with the committed inputs. After each answer it SHALL compare the text head and the page image hash with the inputs. A difference SHALL stop the run.

#### Scenario: Page text changed

- **WHEN** the scan gives a page text whose hash differs from the committed inputs
- **THEN** the run stops before any page of that document is judged

### Requirement: A confirmation runner SHALL lock, record and clean up around its requests

The runner SHALL take an exclusive lock before it reads its checkpoint. It SHALL append the run record before its first decision request. A child server that does not become ready SHALL be stopped before the runner exits.

#### Scenario: A second runner starts

- **WHEN** another runner holds the checkpoint lock
- **THEN** the second runner stops before it reads the checkpoint

#### Scenario: First hosted request

- **WHEN** the first request goes to a hosted model
- **THEN** the run record for that run already exists

#### Scenario: Server startup fails

- **WHEN** the readiness check raises an error or the deadline passes
- **THEN** the child server process is stopped

### Requirement: A confirmation verdict SHALL be withheld when a population is incomplete

The analysis SHALL give no verdict when a scored population is empty, when an expected page has no score, or when a page failed. It SHALL name each gap.

#### Scenario: One page has no score

- **WHEN** one unflagged junk page has no score
- **THEN** the verdict is empty and the note names the population and the count

### Requirement: Confirmation inputs SHALL reproduce from a clean checkout

Input preparation SHALL read only committed files and the documented gitignored corpus folder. A resume SHALL trust a document only when its private files exist and match the committed hashes. A document read again SHALL give the committed hashes, or the run SHALL stop.

#### Scenario: Fresh clone

- **WHEN** a fresh clone holds the committed inputs file but no private files
- **THEN** a resume reads each document again and rebuilds the private files with the same hashes

#### Scenario: Stop during preparation

- **WHEN** preparation stops after some documents
- **THEN** a resume completes the others without reading the finished ones again

### Requirement: The protocol SHALL state a cleanup procedure for private files

The protocol SHALL list each folder that holds page text, page images, references, logs or locks, and the steps to copy, check and delete them after the report is final.

#### Scenario: A private folder is not listed

- **WHEN** the runner writes to a private folder that the cleanup section does not name
- **THEN** the experiment tests fail

## MODIFIED Requirements

### Requirement: The confirmation pass rule SHALL be stricter and page based

The pass rule SHALL be fixed in the protocol and approved by the operator before scoring. It SHALL judge pages, not the share of a document, on pages the scan did not flag. The operator SHALL choose option A or option B and record it in `plan.json` `decision_register`. The report SHALL also give, per document, the pages that would go to OCR and their cost.

#### Scenario: Option A is the strict rule

- **WHEN** the operator records option A
- **THEN** a pass SHALL need junk-page recall at least 0.90 with the lower 95% interval bound at least 0.80
- **AND** a healthy-page flag rate at most 0.02 with the upper 95% interval bound at most 0.05

#### Scenario: Option B is the stated-cost rule

- **WHEN** the operator records option B
- **THEN** a pass SHALL need junk-page recall at least 0.70 and a healthy-page false-reject rate at most 0.05

#### Scenario: Recall passes but false flags fail

- **GIVEN** option A, junk-page recall 0.95 and a healthy-page flag rate of 0.04
- **WHEN** the verdict is computed
- **THEN** the verdict SHALL be FAIL

#### Scenario: Stated cost exceeded

- **GIVEN** option B, junk-page recall 0.80 and a healthy-page false-reject rate of 0.06
- **WHEN** the verdict is computed
- **THEN** the verdict SHALL be FAIL

#### Scenario: No option chosen

- **WHEN** `plan.json` holds no dated operator choice of option
- **THEN** no page is scored

### Requirement: A hosted image control SHALL run beside the local candidate

An exploratory image-check evaluation SHALL score the same pages, with the same question and threshold rule, with a hosted image model as a control, and the report SHALL show it beside the local candidate. In a router confirmation the hosted arm is an optional reference: it SHALL NOT change the verdict. The hosted arm needs the operator's approval in `plan.json` that names the provider and the documents, recorded before any image is sent.

#### Scenario: Control missing

- **WHEN** the report of an exploratory image-check evaluation is written and the hosted arm has no scores
- **THEN** the report gives no verdict

#### Scenario: Confirmation without the hosted reference

- **WHEN** a router confirmation has no hosted approval
- **THEN** the hosted arm is not run
- **AND** the verdict follows the local arm
