# rescue-quality-evaluation Specification

## Purpose

Defines how OMRS evaluates a quality signal on reader-rescue text before any change lets that signal decide whether a rescue zeroes OCR evidence.

## Requirements

### Requirement: Junk rescue text SHALL be defined by the frozen recall labels

The evaluation SHALL score each rescue text against the Experiment 33 frozen reference transcription with the Experiment 33 token rule. It SHALL use the thresholds of the frozen page rule. Text with body token recall below 0.50 is `junk`. Text with recall of 0.80 or more is `healthy`. Text between the two is `grey` and is reported, not scored. Pages whose reference has fewer than 10 body tokens, and pages the frozen labels mark `unrecoverable` or `ambiguous`, SHALL be excluded.

#### Scenario: Handwritten page with a junk text layer

- **WHEN** LiteParse returns text for a page and that text has body token recall 0.24 against the reference
- **THEN** the page is `junk` for that rescue tier

#### Scenario: Labels are verified before use

- **WHEN** the run starts
- **THEN** `freeze.py --check` for Experiment 33 SHALL pass before any label or transcription is read
- **AND** no label SHALL be edited

### Requirement: Adoption margin SHALL be fixed before the run

The protocol SHALL state, before any candidate is scored, the margin by which the model candidate must beat the deterministic candidate, with a reason for the number. A model candidate SHALL be adopted only if it beats the deterministic candidate by that margin and passes every gate.

#### Scenario: Model candidate wins by less than the margin

- **WHEN** Julia 1 junk recall exceeds candidate A by less than the committed margin
- **THEN** candidate A is the recommended signal, if it passes the gates

### Requirement: False-positive cost SHALL be measured at page and document level

The evaluation SHALL report the share of `healthy` pages flagged, and SHALL report every document labelled `usable` that the signal would newly route to OCR. The OCR gate thresholds `0.5` and `0.10` SHALL NOT change.

#### Scenario: Signal flags healthy pages in one document

- **WHEN** flagged healthy pages reach 10% of a `usable` document's pages
- **THEN** the report names that document as newly routed and states the projected OCR cost

### Requirement: Motivating misses SHALL be checked at document level

The evaluation SHALL report whether `rf06` and `rf07` would route to OCR when the candidate's flags count as pages needing OCR.

#### Scenario: Signal catches the handwritten records

- **WHEN** the candidate flags at least 10% of the pages of `rf06` and of `rf07`
- **THEN** both documents count as routed for that candidate

### Requirement: Candidate models SHALL run locally by default and hosted models SHALL need operator approval

Every candidate SHALL run on the operator's machine unless the operator approves a hosted service in the plan before any page text is sent. A hosted candidate SHALL be registered in `plan.json` under a dated amendment that names the provider and the text sent. The evaluation SHALL NOT add PyTorch to the OMRS core dependencies. The optional `torch` extra MAY be used without approval (ADR-073). A model download SHALL wait for operator approval.

#### Scenario: Hosted model proposed

- **WHEN** a candidate needs a hosted service that receives page text
- **THEN** it is excluded until the operator approves it in a dated plan amendment
- **AND** the amendment names the provider and the text sent

#### Scenario: Hosted model approved

- **WHEN** the operator approves a hosted service in a plan amendment
- **THEN** the run sends only the text named in the amendment
- **AND** the report states that page text left the machine

#### Scenario: ONNX route does not match the reference model

- **WHEN** the ONNX parity check fails its preregistered bound
- **THEN** candidate B is not scored, and the operator decides the runtime

### Requirement: Production behaviour SHALL stay unchanged by the experiment

The experiment SHALL NOT change TDR-024 behaviour, the reader chain or any default. A winning signal SHALL need its own proposal and ADR.

#### Scenario: Candidate A passes every gate

- **WHEN** the report recommends candidate A
- **THEN** production still zeroes OCR evidence after a successful rescue until a separate change ships

### Requirement: A router SHALL be confirmed on new documents before any default use

Before any change proposes a router as a default or as a built-in profile setting, an experiment SHALL score it on documents that no earlier rescue experiment used (not Experiments 33, 38, 42, 43 or 44). The threshold SHALL be frozen from Experiment 43 and written to `plan.json` before the new documents are labelled or scored. Labels SHALL be frozen before scoring.

#### Scenario: Threshold frozen first

- **WHEN** the confirmation experiment starts
- **THEN** `plan.json` SHALL hold the threshold, its Experiment 43 source and a hash of that source
- **AND** no router score on a new document SHALL exist before that commit

#### Scenario: Reused document refused

- **WHEN** a candidate document matches a file used in Experiments 33, 38, 42, 43 or 44 by SHA-256
- **THEN** it SHALL be excluded before labelling

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

### Requirement: Hosted arms in the confirmation SHALL need recorded approval

A hosted decision model arm SHALL run only after the operator records approval in `plan.json`, naming the documents whose pages leave the machine. The local arm SHALL be the primary arm.

#### Scenario: No approval

- **GIVEN** no recorded approval
- **WHEN** the experiment runs
- **THEN** no page SHALL be sent to a hosted model
- **AND** the report SHALL mark the hosted arm as not run

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

### Requirement: A hosted image control SHALL run beside the local candidate

An exploratory image-check evaluation SHALL score the same pages, with the same question and threshold rule, with a hosted image model as a control, and the report SHALL show it beside the local candidate. In a router confirmation the hosted arm is an optional reference: it SHALL NOT change the verdict. The hosted arm needs the operator's approval in `plan.json` that names the provider and the documents, recorded before any image is sent.

#### Scenario: Control missing

- **WHEN** the report of an exploratory image-check evaluation is written and the hosted arm has no scores
- **THEN** the report gives no verdict

#### Scenario: Confirmation without the hosted reference

- **WHEN** a router confirmation has no hosted approval
- **THEN** the hosted arm is not run
- **AND** the verdict follows the local arm

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
