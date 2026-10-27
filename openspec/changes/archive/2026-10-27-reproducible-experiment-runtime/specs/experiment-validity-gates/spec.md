## ADDED Requirements

### Requirement: Local models run through llama.cpp with a public GGUF file

An experiment planned after this change SHALL run every local language, embedding and decision model through llama.cpp with a GGUF file that anyone can download. It SHALL NOT use Ollama, MLX or another runtime for that model. A hosted model MAY run as a reference arm, and the plan SHALL name its provider and model id.

#### Scenario: Plan names an Ollama model

- **WHEN** a plan planned after this change runs a local model through an Ollama tag and the runtime is not the manipulated variable
- **THEN** the plan does not meet this requirement

### Requirement: The plan pins each local model

`plan.json` SHALL hold a `runtime` block. For each local model it SHALL record the role, the Hugging Face repository, the file name, the file's SHA-256, the runtime `llama.cpp`, the llama.cpp build number, and each server argument that can change output.

#### Scenario: Plan with a pinned embedding model

- **WHEN** a plan uses `Qwen/Qwen3-Embedding-0.6B-GGUF` file `Qwen3-Embedding-0.6B-Q8_0.gguf`
- **THEN** its `runtime` block records that repository and file, the SHA-256 `06507c7b…`, the runtime `llama.cpp`, the build number and the pooling argument

### Requirement: The plan states a reproduction tolerance

The `runtime` block SHALL record a tolerance: the largest change in each primary metric, or in each per-item score, that still counts as the same result on other hardware.

#### Scenario: Tolerance for the primary metric

- **WHEN** a plan has the primary metric `recall_at_10`
- **THEN** its `runtime` block gives a largest allowed change for `recall_at_10`

### Requirement: Runtime comparisons may run other runtimes

When the runtime is the manipulated variable of the experiment, the plan SHALL say so, and it MAY run the runtimes it compares. Each such arm SHALL record the runtime name and version and a SHA-256 for each weights file.

#### Scenario: Runtime comparison

- **WHEN** an experiment compares MLX and llama.cpp builds of one model and the plan says the runtime is the manipulated variable
- **THEN** the MLX arm is allowed
- **AND** the plan records the MLX runtime version and the SHA-256 of each weights file

### Requirement: A run checks the live server against the plan

Before a run scores its first item, it SHALL read the build number from the llama.cpp server and the SHA-256 of each model file the server loads. It SHALL compare both with the `runtime` block. A difference SHALL stop the run before any score is written, with a message that names the expected and the found value. The run record SHALL hold the build number and the SHA-256 values it found. A run on a different build SHALL first add an amendment to the plan that names the new build.

#### Scenario: Matching server

- **WHEN** the server reports build `b11671` and the model file has the SHA-256 in the plan
- **THEN** the run starts
- **AND** the run record holds `b11671` and the SHA-256

#### Scenario: Wrong build

- **WHEN** the plan records build 11671 and the server reports build 11510
- **THEN** the run stops before it writes a score
- **AND** the message names 11671 and 11510

#### Scenario: Different model file

- **WHEN** the model file the server loads has a SHA-256 that is not in the plan
- **THEN** the run stops before it writes a score
- **AND** the message names the file and both SHA-256 values
