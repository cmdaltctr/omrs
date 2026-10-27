# experiment-validity-gates Specification

## Purpose
Sets the validity bar for experiments under ``experiments/``:
machine-checkable plans, runtime manifests recording what actually ran,
manipulated variables that are observed rather than assumed, paired
comparisons by default, execution controls for time and hardware
confounds, and pre-registered practical gates on primary effects.
Calibration decisions cite these gates; without them a PASS is an
opinion.

## Requirements

### Requirement: Experiment plans are machine-checkable

Every calibration experiment that can influence a production default or ADR SHALL define its manipulated factors, controlled variables, expected cell matrix, primary metric, practical-effect gate, and required runtime-manifest assertions in machine-readable form adjacent to the human protocol.

#### Scenario: Runner omits a declared cell
- **GIVEN** a protocol declares a cell in its machine-readable plan
- **AND** the runner's generated cell matrix omits that cell
- **WHEN** experiment contract tests run
- **THEN** the test MUST fail before any expensive model or corpus work begins

#### Scenario: Runner adds an undeclared cell
- **GIVEN** a runner generates a treatment combination not present in the plan
- **WHEN** contract tests run
- **THEN** the test MUST fail or the protocol MUST be amended before execution

### Requirement: Runtime manifests record effective execution

Every measured experiment SHALL emit a secret-free runtime manifest describing what actually executed, not only requested configuration.

#### Scenario: ONNX provider fallback
- **GIVEN** a performance cell declares CoreML as the manipulated execution provider
- **WHEN** the runtime uses CPUExecutionProvider instead
- **THEN** preflight MUST abort the cell
- **AND** no CoreML latency result may be reported

#### Scenario: Secret-bearing configuration
- **WHEN** a runtime manifest is serialised
- **THEN** API keys, tokens and credential material MUST NOT be present

### Requirement: The runtime manifest lists the effective components of each cell

The manifest SHALL include repository/dependency provenance, corpus/query/qrel/index identity, effective embedding provider/model, vector-store backend/mode/score kind, sparse backend/cache namespace, reranker backend/model/device/execution provider/variant when observable, effective chunker/document reader including fallback state, and effective retrieval knobs relevant to the cell.

#### Scenario: Torch requested but CPU/MPS device differs
- **GIVEN** a cell manipulates the reranker execution device
- **WHEN** preflight observes the effective device
- **THEN** the manifest MUST record the effective device
- **AND** the cell MUST abort if it does not equal the declared treatment

### Requirement: Manipulated variables must be observed, not assumed

Before a measured cell begins, the experiment SHALL assert that every manipulated variable is effective and every controlled variable remains fixed at its declared value. A production fallback that changes a manipulated factor SHALL invalidate/abort the experimental cell even if that fallback is acceptable during ordinary operation.

#### Scenario: Parser experiment silently bypasses parser
- **GIVEN** parser backend is the manipulated variable
- **WHEN** the runner constructs an index without invoking the declared parser
- **THEN** preflight MUST fail before embeddings are computed

#### Scenario: Technical threshold experiment forces rerank
- **GIVEN** `HARD_TECHNICAL_THRESHOLD` is the manipulated variable
- **WHEN** the runner would call retrieval with explicit `rerank=True` or `rerank=False` instead of policy mode
- **THEN** preflight MUST fail because the policy factor is bypassed

### Requirement: Quality comparisons are paired by default

Unless the manipulated variable necessarily changes the corpus or query set, comparison cells SHALL use the same immutable corpus, exact query set, qrels and query ordering. Workload classes SHALL be blocked/stratified before treatment assignment; a new random query sample SHALL NOT be drawn independently for every treatment level.

#### Scenario: Threshold sweep uses fixed blocked samples
- **GIVEN** thresholds `{0.1, 0.2, 0.3, 0.5, 0.7}` are evaluated
- **WHEN** the experiment constructs technical/semantic workload blocks
- **THEN** every threshold MUST receive the same query membership within each block

### Requirement: Cell execution controls time and hardware confounds

Measured performance experiments SHALL separate warm-up from measured repetitions, record raw repetitions, and randomise or counterbalance cell order when multiple cells share a machine. Interrupted or hung cells SHALL be recorded as incomplete/invalid and SHALL NOT be converted into a numeric latency or quality failure.

#### Scenario: Interrupted cell
- **GIVEN** a cell stops before its declared measured repetitions finish
- **WHEN** results are summarised
- **THEN** the cell MUST be marked incomplete/invalid
- **AND** no imputed latency value may be used in treatment comparisons

### Requirement: Primary effects have pre-registered practical gates

A protocol SHALL name its primary metric and practical-effect threshold before execution. Where per-query paired samples exist, the result SHALL include a paired confidence interval or an explicitly justified equivalence/non-inferiority analysis. A default SHALL NOT be promoted solely from an unbounded point estimate whose uncertainty includes no effect unless the protocol pre-registers a different decision rule.

#### Scenario: Hybrid promotion point estimate without confidence
- **GIVEN** hybrid shows a positive mean Coverage@20 delta
- **BUT** the paired confidence interval includes zero
- **WHEN** the promotion rule requires statistical confidence
- **THEN** the experiment MUST NOT recommend default promotion

### Requirement: Evidence provenance is immutable enough to reproduce

Every expensive experiment SHALL record repository commit SHA, dependency-lock hash, protocol version, corpus identity, query-set identity, qrels identity and index identity. Changing any index-shaping input such as parser, chunking configuration, embedding provider/model or source corpus SHALL produce a distinct index identity.

#### Scenario: Parser changes
- **GIVEN** two cells differ only by PDF parser
- **WHEN** indexes are built
- **THEN** the two index identities MUST differ
- **AND** retrieval-only repetitions within one parser cell MAY reuse that immutable index read-only

### Requirement: Verdicts require complete identified observations

An experiment summariser SHALL check each measured cell against its declared observation set before evaluating gates. Each expected observation SHALL occur exactly once. Comparisons SHALL join observations by identity and validate their declared workload classes. Missing observations SHALL produce INCOMPLETE; duplicate, unexpected or incompatible observations SHALL produce INVALID. Neither status SHALL produce a promotion recommendation.

#### Scenario: A smoke run would pass the numeric gates
- **WHEN** a runner records only a permitted smoke subset of the full declared query set
- **THEN** the summariser SHALL report INCOMPLETE
- **AND** it SHALL NOT report PASS or recommend promotion even if the subset clears every numeric threshold

#### Scenario: Equal counts hide different query membership
- **WHEN** two cells have equal row counts but different query identities or workload labels
- **THEN** the summariser SHALL report INVALID before evaluating a paired effect

#### Scenario: Complete historical cells remain valid
- **WHEN** all declared observations occur exactly once with matching provenance
- **THEN** summarisation SHALL reproduce the applicable frozen-gate verdict
- **AND** the original raw records SHALL remain unchanged

### Requirement: Checkpoint reuse requires matching measurement identity

Resuming an experiment SHALL validate its corpus, observation identifiers, plan, effective treatments and relevant code and dependency provenance before skipping work. A changed population or routing policy SHALL require a distinct run or an explicit compatible migration. Local document mappings SHALL remain stable across resume. A checkpoint without sufficient provenance SHALL remain usable as labelled historical evidence and SHALL NOT silently authorise new work or a mixed-provenance run.

#### Scenario: A document is added to the selected collection
- **WHEN** the collection identity differs from the saved checkpoint
- **THEN** the runner SHALL refuse resume before replacing its saved mapping or recording measurements
- **AND** it SHALL explain how to start a separate run

#### Scenario: The routing policy changes
- **WHEN** saved classifications contain decisions from another routing-policy revision
- **THEN** the runner SHALL NOT treat those decisions as measurements of the current revision
- **AND** a replay SHALL identify both the source evidence and the evaluated policy

### Requirement: Paid rebuilds require current estimates and approval

An experiment rebuild SHALL preserve existing indexes and require an offline estimate of the actual prepared embedding requests. The estimate SHALL cover the declared corpus and effective configuration, report token counts and an explicit pricing basis, and distinguish estimated cost from billing. Paid execution SHALL require operator approval tied to that estimate, destination and spending limit.

#### Scenario: Offline accounting encounters a fallback
- **WHEN** preparation cannot reproduce the declared tokenizer or request-text contract
- **THEN** the estimate SHALL be invalid
- **AND** it SHALL NOT authorise a paid build

#### Scenario: A rebuild is approved
- **WHEN** a valid estimate and explicit approval match the requested build
- **THEN** the builder SHALL use a separate approved output location
- **AND** it SHALL leave the preserved historical index unchanged

### Requirement: Missing or stale estimates block paid rebuilds

Missing, invalid or stale estimates SHALL block spending. A force option SHALL NOT bypass the estimate, approval or destination checks.

#### Scenario: A forced rebuild has no approved estimate
- **WHEN** the operator requests a forced rebuild without a valid approved estimate
- **THEN** the builder SHALL stop before any paid request
- **AND** it SHALL explain the missing approval or estimate

#### Scenario: The approved inputs change
- **WHEN** corpus, tokenizer, embedding configuration, request preparation or destination differs from the approved estimate
- **THEN** the builder SHALL refuse to use that approval

### Requirement: A frozen acceptance threshold judges only the measured result

A frozen acceptance threshold SHALL evaluate the measured result only; exceeding it SHALL NOT invalidate an otherwise valid estimate or block an approved build.

#### Scenario: The estimate exceeds a frozen acceptance threshold
- **WHEN** a valid estimate exceeds the pre-registered token-increase threshold
- **THEN** the builder SHALL display the estimated token increase and approximate cost and request spending approval
- **AND** it SHALL permit the build when valid approval matches the estimate, destination and spending limit
- **AND** the frozen threshold SHALL remain unchanged for evaluating the measured experiment result

### Requirement: Reports distinguish measurements from explanations and decisions

Reports SHALL distinguish measured results, projections, exploratory interpretations and approved operator decisions. A statistical calculation SHALL NOT be presented as the source of an operator-selected practical threshold. Historical gates and raw evidence SHALL be preserved when explanations are corrected. A machine verdict SHALL NOT be recorded as operator acceptance without explicit approval.

#### Scenario: Runtime is extrapolated from fixtures
- **WHEN** a report estimates corpus runtime from fixture timings
- **THEN** it SHALL label the runtime and derived slowdown as projections
- **AND** it SHALL state assumptions including whole-request timeout behaviour

#### Scenario: A metric matches while rankings differ
- **WHEN** repeated retrieval measurements have equal recall but different returned rankings
- **THEN** the report SHALL describe the measured agreement and differences
- **AND** it SHALL NOT claim that metric equality proves deterministic execution

#### Scenario: The operator has not decided whether to promote OCR
- **WHEN** the experiment has a verdict but operator approval remains outstanding
- **THEN** the decision record and promotion task SHALL remain pending
- **AND** packaged defaults SHALL remain unchanged

#### Scenario: A repeated combined experiment has no approved purpose
- **WHEN** the operator has not confirmed that the combined treatment is still a desired candidate
- **THEN** the workflow SHALL retain the historical result and defer new paid measurement
- **AND** the decision to rerun or close the repeat request SHALL be recorded explicitly

### Requirement: PDF routing evaluations use approved cohorts and independent labels

A PDF routing evaluation SHALL record the operator-approved inclusion rule and selected documents before measurement. Ground-truth labels SHALL include an independent assessment of relevant page content, distinct from the classifier's output and aggregate character counts. Ambiguous cases SHALL be recorded explicitly. The protocol SHALL define how missing pages and whole-document routing are judged.

#### Scenario: The operator selects papers and a long book
- **WHEN** the approved collection includes selected papers and a book as a stress case
- **THEN** discovery SHALL be limited to that selection
- **AND** reporting SHALL identify the collection composition without claiming it represents paper-only prevalence

#### Scenario: A long document has some unreadable pages
- **WHEN** aggregate character counts are high but relevant pages lack usable text
- **THEN** the evaluation SHALL retain the independently assessed missing-page evidence
- **AND** it SHALL apply the agreed routing judgement rather than infer correctness from the aggregate alone

### Requirement: Development documents are not held-out validation

Documents used to develop a candidate SHALL NOT count as independent held-out validation of that candidate.

#### Scenario: A known failure motivates a new rule
- **WHEN** a candidate was designed after examining a document
- **THEN** a successful replay on that document SHALL be labelled a development regression check
- **AND** independent validation SHALL use other approved documents whose outcomes were withheld during candidate design

### Requirement: Public experiment failures preserve document privacy

Public experiment records SHALL exclude private document names, paths and extracted text, including failure cases. Public error information SHALL use approved codes or classes. Detailed private diagnostics and identity mappings SHALL remain in ignored local storage. Privacy checks SHALL inspect serialised outputs rather than rely only on declarations of intended behaviour.

#### Scenario: An exception includes a document path
- **WHEN** document processing raises an exception containing private text or a path
- **THEN** the public checkpoint SHALL contain only approved diagnostic fields
- **AND** the private exception message SHALL NOT appear in public reports

### Requirement: Repeat-study protocols freeze before held-out measurement

A repeat routing study SHALL record the approved candidate, labels, development/held-out split and acceptance criteria in a committed artefact before any held-out scoring. Held-out outcomes SHALL NOT guide candidate design. The comparison SHALL evaluate the approved candidate against the historical policy pinned at its original revision; the current working tree SHALL NOT serve as an unnamed baseline. Negative results SHALL be retained and reported.

#### Scenario: Candidate designed on development evidence
- **WHEN** a candidate rule is developed using the approved book and development documents
- **THEN** the frozen protocol commit SHALL precede the first held-out measurement
- **AND** held-out documents SHALL be disjoint from every document examined during design

#### Scenario: Working tree differs from the historical policy
- **WHEN** the comparison runs
- **THEN** the baseline SHALL be the committed historical policy at its pinned revision
- **AND** uncommitted local changes SHALL NOT silently become the baseline

### Requirement: Real OCR measurement requires separate authorisation

A routing classification and replay evaluation SHALL NOT perform real OCR requests without a separate recorded authorisation naming the selected documents, a timeout and a runtime budget. A classification-only run SHALL report OCR cost as a projection and extraction-recovery quality as unmeasured. Fixture-derived runtime estimates SHALL be labelled as projections with their assumptions stated.

#### Scenario: Classification-only run
- **WHEN** the authorised scope covers classification and routing replay only
- **THEN** the report SHALL label any OCR runtime and slowdown figures as projections
- **AND** it SHALL record recovery quality as unmeasured rather than inferred

#### Scenario: OCR authorised for selected documents
- **WHEN** the operator authorises real OCR for a named document subset with a timeout and runtime budget
- **THEN** the measurement SHALL record elapsed classification time, timeout and failure behaviour and extraction outcomes
- **AND** it SHALL stop before exceeding the authorised budget

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
