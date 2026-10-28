## Purpose

Checks that the full OMRS pipeline runs end to end with every local model on llama.cpp, on a small fixed set, before a publication benchmark starts. It also times local embedding so that the benchmark can choose local or cloud hardware.

## ADDED Requirements

### Requirement: The sweep SHALL use a fixed set frozen before the first run

The sweep SHALL name its documents and questions in the protocol before the first run, with the SHA-256 of each document and of the question file. The set SHALL hold the 6 Experiment 3 documents, the 17 questions of Experiment 2's ground truth, and 5 FinanceBench PDFs with their open-sample questions. The set SHALL NOT change after the first run.

#### Scenario: Set recorded before the run

- **WHEN** the first run starts
- **THEN** the protocol lists every document and question file with its SHA-256

#### Scenario: A document changes after the first run

- **WHEN** a document hash differs from the hash in the protocol
- **THEN** the run stops before it ingests anything
- **AND** the message names the file and both hashes

### Requirement: Every local language and embedding model SHALL run through llama.cpp

The sweep SHALL run every local language and embedding model through llama.cpp with a public GGUF file pinned in the plan. It SHALL NOT call Ollama. Models that llama.cpp cannot run, such as the ONNX reranker and the OCR engines, SHALL be listed in the runtime manifest with their own identity.

#### Scenario: An Ollama call during the sweep

- **WHEN** any stage of the sweep sends a request to an Ollama server
- **THEN** the run does not meet this requirement and its result is not used

#### Scenario: Reranker stage

- **WHEN** the hybrid-with-reranker search runs
- **THEN** the runtime manifest names the reranker model and its runtime

### Requirement: The sweep SHALL run every pipeline stage

One sweep run SHALL ingest the fixed set (reader, OCR routing, normalisation), chunk it, embed it with the baseline embedding model, and write it to LanceDB. It SHALL then search each question in dense, hybrid and hybrid-with-reranker mode, and answer each question without and with claim checking. It SHALL record each stage's status and error count.

#### Scenario: All stages recorded

- **WHEN** a sweep run finishes
- **THEN** its output holds one status line for each stage and each search and answer mode

#### Scenario: A stage fails

- **WHEN** a stage raises an error
- **THEN** the output records the stage, the item and the error message
- **AND** the sweep verdict is `FAIL`

#### Scenario: Token-aware chunking falls back to the legacy splitter

- **WHEN** the configured tokenizer is not cached and chunking resolves to the legacy splitter
- **THEN** the run stops before the first document is embedded
- **AND** the output names the tokenizer model and revision

### Requirement: The sweep SHALL compare scores with earlier Ollama numbers where they exist

The report SHALL give Hit@1 and MRR on the 17 questions for dense search beside the Experiment 2 Ollama numbers, and Hit@1 with the reranker beside Experiment 3. The plan SHALL state the allowed difference before the first run. For a stage or set with no earlier comparable number, the report SHALL say that no comparison exists.

#### Scenario: Comparable number exists

- **WHEN** dense search on the 17 questions gives Hit@1 and MRR
- **THEN** the report shows them beside the Experiment 2 values and the allowed difference from the plan

#### Scenario: No earlier number

- **WHEN** the report gives a score for the FinanceBench questions
- **THEN** it states that no earlier Ollama number exists for that set

### Requirement: The sweep SHALL check retrieval determinism

After the scored run, the sweep SHALL repeat retrieval once for every question and mode on the same index. The repeat SHALL return the same chunk identifiers in the same order. Any difference SHALL fail the determinism check, and the report SHALL list each question that differed.

#### Scenario: Identical repeat

- **WHEN** the repeat returns the same ranked chunk identifiers for every question and mode
- **THEN** the determinism check passes

#### Scenario: One ranking differs

- **WHEN** one question returns a different order in the repeat
- **THEN** the determinism check fails
- **AND** the report names the question, the mode and both rankings

### Requirement: The sweep SHALL time local embedding on a fixed slice of each corpus

The sweep SHALL embed a fixed slice of each benchmark corpus with each of Qwen3-Embedding 0.6B, 4B and 8B GGUF on the measurement Mac, one model at a time. The slices are 200 FreshStack documents, 200 BioASQ abstracts and the 5 FinanceBench PDFs of the fixed set. For each model and slice it SHALL record wall time, input tokens and peak server memory.

#### Scenario: Timing row for each model

- **WHEN** the timing part finishes
- **THEN** the output holds one row per model and slice with wall time, tokens, tokens per second and peak memory

### Requirement: The sweep SHALL extrapolate embedding time to the benchmark corpora

The report SHALL estimate the embedding wall time of each model on the FinanceBench PDFs, the FreshStack corpus (10,024 documents) and the BioASQ corpus (40.2K abstracts). The estimate SHALL use the tokens per second measured on that corpus's slice and a token count of the corpus. The report SHALL state the method and the count source.

#### Scenario: Estimate table

- **WHEN** the report is written
- **THEN** it shows one estimated wall time per model and corpus
- **AND** it names the output file that each count and rate came from

### Requirement: The sweep SHALL compare fast mode with exact mode

The sweep SHALL embed the same slices with the 4B model in exact mode (one slot, one request at a time) and in fast mode (several slots and concurrent requests). It SHALL report the lowest cosine between vector pairs, any top-10 ranking change and the speed of each mode. Fast mode SHALL be allowed for Experiment 35 only when the lowest cosine is at least 0.9999 and no top-10 ranking changes.

#### Scenario: Fast mode drifts too far

- **WHEN** a vector pair has cosine below 0.9999, or a top-10 ranking changes
- **THEN** the report recommends exact mode for Experiment 35
- **AND** it gives the measured drift and the speed gain

### Requirement: The sweep SHALL pin every server argument

The plan SHALL write out every llama.cpp server argument that can change speed or output, including values that default to auto. The chat preset SHALL turn off speculative decoding and the prompt cache. The run SHALL record a `/props` snapshot and that no `LLAMA_ARG_*` environment variable is set.

#### Scenario: Default parallel slots

- **WHEN** the plan does not name `parallel` for a model
- **THEN** the plan does not pass the protocol check, because build 11671 defaults to 4 slots

### Requirement: Production behaviour SHALL stay unchanged by the sweep

The sweep SHALL NOT change production defaults, profiles, the live app or its data. It SHALL write only inside its experiment folder and scratch locations it names.

#### Scenario: Sweep finishes

- **WHEN** the sweep finishes
- **THEN** `src/omrs/config/defaults.yaml` and the profile files are unchanged
- **AND** nothing under `~/.omrs` was written
