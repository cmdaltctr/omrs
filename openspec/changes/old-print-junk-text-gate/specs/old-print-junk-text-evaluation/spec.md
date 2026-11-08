## Purpose

How OMRS evaluates a signal that sends garbled old-print text layers to OCR, before any default changes.

## ADDED Requirements

### Requirement: Thresholds are fitted and confirmed on separate documents

The evaluation SHALL fit every threshold and cut on a fit set and SHALL judge the gates only on a held-out set of documents not used in the fit step or in Experiments 43 and 47. The held-out set SHALL be frozen with file hashes before any held-out score is read.

#### Scenario: Held-out document seen before

- **WHEN** a held-out document's hash matches a fit-set or Experiment 43 or 47 document
- **THEN** the run MUST stop before scoring and name the document

### Requirement: Pages are labelled before any arm runs

Each page SHALL be labelled from its image as junk text layer or healthy before any arm scores it. Pages that the page scan already sends to OCR SHALL be left out of every denominator.

#### Scenario: Labels committed first

- **WHEN** the first arm runs on the held-out set
- **THEN** the labels file MUST already be committed, and its commit MUST come before the first score file

### Requirement: A signal passes only on both primary gates

A treatment arm SHALL pass only when, on the held-out set, junk-page recall is at least 0.70 and the healthy-page false-reject rate is at most 0.05. The report SHALL give Wilson intervals for both.

#### Scenario: High recall with too many false rejects

- **WHEN** an arm catches 45 of 54 junk pages and rejects 4 of 54 healthy pages
- **THEN** the arm MUST be reported as FAIL on G2

### Requirement: No production default changes from this evaluation

The evaluation SHALL NOT change any production default or setting. A passing arm SHALL lead to a separate change.

#### Scenario: Passing arm

- **WHEN** an arm passes both primary gates
- **THEN** the router and page rules MUST stay off by default until a separate change merges
