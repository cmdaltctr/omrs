# Spec Delta

## Purpose

Define how OMRS evaluates a llama.cpp GGUF runtime or an MLX runtime for an OCR engine against the engine's shipped backend. A decision to change an engine's runtime rests on a llama.cpp arm that passes the gates. MLX arms are comparison arms only.

## ADDED Requirements

### Requirement: Each new arm SHALL be compared with its own baseline on the same pages

Each new arm SHALL run the same page list as its engine's shipped baseline, with the same prompt, render size, token cap, decoding rule and post-processing.

#### Scenario: Baseline results come from an earlier experiment
- **WHEN** a baseline arm reuses results from an earlier experiment
- **THEN** the page list SHALL be copied from that experiment and frozen with a SHA-256
- **AND** the report SHALL name the source files of the baseline

#### Scenario: A new arm uses a different page list
- **WHEN** the page list of a new arm differs from its baseline
- **THEN** the comparison SHALL NOT count toward any gate

### Requirement: Only a llama.cpp arm SHALL decide a runtime

A llama.cpp GGUF arm that passes gates C1 to C5 MAY lead to a follow-up change for its engine. An MLX arm SHALL NOT lead to a runtime decision, even when it passes every gate.

#### Scenario: An MLX arm passes and no llama.cpp arm passes
- **WHEN** an MLX arm passes and no llama.cpp arm of the same engine passes
- **THEN** the report SHALL state that no runtime decision follows
- **AND** the engine SHALL keep its shipped backend

#### Scenario: A llama.cpp arm passes
- **WHEN** a llama.cpp arm passes gates C1 to C5
- **THEN** the report SHALL name a follow-up OpenSpec change for that engine as the next step
- **AND** no engine, route or default SHALL change in this change

### Requirement: A quality failure of an 8-bit arm SHALL trigger a 16-bit diagnostic that does not change the verdict

When an 8-bit arm fails gate C3, C4 or C5, the evaluation SHALL run the 16-bit arm of the same runtime and engine on the pages of the failed gate, and score that gate only.

#### Scenario: The 16-bit diagnostic passes the failed gate
- **WHEN** the 16-bit diagnostic passes the gate that its 8-bit arm failed
- **THEN** the report SHALL attribute the failure to the 8-bit quantisation
- **AND** the 8-bit arm SHALL keep its failed verdict

#### Scenario: No 8-bit arm fails a quality gate
- **WHEN** every 8-bit arm passes C3, C4 and C5
- **THEN** no 16-bit diagnostic SHALL run
- **AND** no 16-bit MLX build SHALL be downloaded

### Requirement: llama.cpp arms SHALL pin their runtime and weights

Each llama.cpp arm SHALL record its build, the SHA-256 of each weights file and its server arguments that change output. The `runtime` block of `plan.json` SHALL hold these values before the first score.

#### Scenario: A build or hash differs from the plan
- **WHEN** `verify_llamacpp_runtime` finds a build or a file hash that differs from the plan
- **THEN** the run SHALL stop before the first score

#### Scenario: A conversion or load fails
- **WHEN** a dots.mocr or PaddleOCR-VL conversion or load to llama.cpp fails
- **THEN** the failure SHALL be recorded as a finding
- **AND** only that arm SHALL stop

### Requirement: Timings SHALL be measured on an otherwise idle machine

Each new arm SHALL run alone, one arm at a time, with no other GPU job.

#### Scenario: Another GPU job runs during an arm
- **WHEN** another GPU job runs while an arm is timed
- **THEN** the timings of that arm SHALL be marked as measured under shared load
- **AND** the arm SHALL NOT count toward the speed gate until it is re-run

#### Scenario: The baseline ran under shared load
- **WHEN** the baseline timings came from a run with shared load
- **THEN** the report SHALL state this limit beside every speed comparison
- **AND** the speed comparison SHALL use baseline pages that ran alone, where they exist

### Requirement: Memory SHALL include every process of the runtime

Peak memory for an arm SHALL be the sum of the peak physical footprint of the client process and of any server process.

#### Scenario: The runtime uses a separate server
- **WHEN** an arm calls a local inference server
- **THEN** the reported peak memory SHALL include the server process
- **AND** the report SHALL name the sampling method

### Requirement: Output quality SHALL be measured against the baseline and the references

The evaluation SHALL report the KaTeX 0.16.22 render error rate, token recall on the script and handwriting pages, the operator's verdict on invented text, and the per-page token similarity to the baseline arm.

#### Scenario: A formula differs from the baseline
- **WHEN** a formula in the baseline output is altered or missing in a new arm's output
- **THEN** the report SHALL list it
- **AND** the list SHALL appear even when every gate passes

#### Scenario: A page returns no text
- **WHEN** a page times out or returns empty text
- **THEN** the page SHALL count as scored 0.0 in the recall view that includes all pages
- **AND** the report SHALL also give the view over pages with output

### Requirement: The operator SHALL set the gates before any run

The protocol MAY propose candidate gates. The operator SHALL set or replace them in the plan, and the plan SHALL be frozen before the first run.

#### Scenario: No gate is set
- **WHEN** the plan shows the gates as not set
- **THEN** no OCR run SHALL start

#### Scenario: A gate changes after a run starts
- **WHEN** the operator changes a gate after an arm has started
- **THEN** the change SHALL be recorded as a dated amendment with its reason
- **AND** the report SHALL show the original rule

### Requirement: Installs, downloads, the licence check and runs SHALL need the operator's approval

The plan SHALL hold one approval for installing the runtime tooling, one for downloading model weights, one for the licence check of each converted model, and one for the OCR run budget. Each approval SHALL stay false until the operator sets it.

#### Scenario: An approval is false
- **WHEN** an approval in the plan is false
- **THEN** the work it covers SHALL NOT start
- **AND** no other approval SHALL imply it

#### Scenario: A converted model derives from a model with extra licence terms
- **WHEN** a conversion derives from a model whose agreement covers derivative works
- **THEN** the operator SHALL decide, before download, whether the earlier acceptance covers the conversion
- **AND** the decision SHALL be recorded in the plan

### Requirement: The evaluation SHALL NOT change shipped behaviour

The evaluation SHALL NOT change any engine folder, route, setting default or dependency of OMRS.

#### Scenario: Only one engine's arm passes
- **WHEN** one engine has a passing llama.cpp arm and the other does not
- **THEN** the follow-up SHALL cover only the engine that passed
- **AND** the other engine SHALL stay on its shipped backend
