## ADDED Requirements

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

The pass rule SHALL be fixed in the protocol before scoring. It SHALL judge pages, not the 10% document share: junk-page recall at least 0.90 with the lower 95% interval bound at least 0.80, and the healthy-page flag rate at most 0.02 with the upper 95% interval bound at most 0.05. The report SHALL also give, per document, the pages that would go to OCR and their cost.

#### Scenario: Recall passes but false flags fail

- **GIVEN** junk-page recall 0.95 and a healthy-page flag rate of 0.04
- **WHEN** the verdict is computed
- **THEN** the verdict SHALL be FAIL

### Requirement: Hosted arms in the confirmation SHALL need recorded approval

A hosted decision model arm SHALL run only after the operator records approval in `plan.json`, naming the documents whose pages leave the machine. The local arm SHALL be the primary arm.

#### Scenario: No approval

- **GIVEN** no recorded approval
- **WHEN** the experiment runs
- **THEN** no page SHALL be sent to a hosted model
- **AND** the report SHALL mark the hosted arm as not run
