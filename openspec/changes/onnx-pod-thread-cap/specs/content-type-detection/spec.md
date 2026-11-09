# Spec Delta

## ADDED Requirements

### Requirement: Magika inference uses bounded ONNX worker threads

The in-process Magika detector SHALL initialise its ONNX session with bounded intra-operation and inter-operation worker counts. The intra-operation count SHALL be derived from the CPUs available to the process, with a maximum of eight. The inter-operation count SHALL be one. Content classification and error fallback SHALL remain unchanged.

#### Scenario: More CPUs are visible than the thread ceiling

- **WHEN** the process has more than eight visible CPUs and constructs the detector
- **THEN** the ONNX session SHALL use eight intra-operation workers and one inter-operation worker
- **AND** it SHALL use the same Magika model and prediction mode as before

#### Scenario: Fewer CPUs are visible than the thread ceiling

- **WHEN** the process has fewer than eight visible CPUs and constructs the detector
- **THEN** the intra-operation worker count SHALL equal the visible CPU count
- **AND** the inter-operation worker count SHALL be one

#### Scenario: A capped session preserves detection results

- **WHEN** the capped detector processes the frozen acceptance corpus
- **THEN** its labels, groups and text flags SHALL match the uncapped detector
- **AND** its suffix fallback behaviour SHALL remain unchanged
