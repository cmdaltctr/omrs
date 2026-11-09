# Spec Delta

## ADDED Requirements

### Requirement: Content detection does not over-allocate ONNX threads

Ingestion's in-process content detector SHALL limit ONNX intra-operation workers to the smaller of the visible CPU count and eight. It SHALL use one inter-operation worker. The limit SHALL apply before the process-wide detector instance is reused.

#### Scenario: Detection on a host with many visible CPUs

- **WHEN** ingestion detects content on a container exposing more than eight CPUs
- **THEN** its ONNX session SHALL use at most eight intra-operation workers
- **AND** it SHALL use one inter-operation worker
- **AND** subsequent detections SHALL reuse the bounded session
