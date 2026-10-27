# Experiment <number>: <title>

- **Folder**: `<number>-<slug>-<YYYY-MM-DD>`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Operator**: <person>, with <agent, if used>
- **Related**: <ADR, TDR, OpenSpec change, earlier experiment>

## 1. Question

<One sentence: the question.>

<One sentence: the decision that depends on the answer.>

## 2. Hypothesis

- **H1**: <change> makes <primary metric> better than <baseline> by at least <amount>.
- **H0 (null)**: the difference is smaller than <amount>, or goes the other way.
- **Decision rule**: If H1 holds and <guardrail> does not get worse by more than <amount>, then <action>. Otherwise <other action>.

Add H2 only if the decision needs it. Mark each hypothesis as primary or secondary.

## 3. What changes, what is measured, what stays fixed

| Changes (one thing) | Primary metric | Guardrail metric | Fixed |
| --- | --- | --- | --- |
| <baseline> vs <candidate> | <metric: plain meaning> | <metric: plain meaning> | <model, corpus, settings> |

## 4. Data

| Item | Value |
| --- | --- |
| Source | <dataset or earlier experiment> |
| Unit | <query, page or document> |
| Size | <count> |
| Groups | <items that share a document or a topic, if any> |
| Labels | <who or what made them, and when> |
| Already seen | <none, or the earlier experiments that used this data> |

## 5. Steps

Run every command from the repository root.

1. Prepare the data: `<command>`
2. Build the index or fixtures: `<command>`
3. Run: `<command> --resume`
4. Summarise: `<command>`

## 6. Analysis

- **Stats level**: <basic | medium | expert>
- **Test for H1**: <for example "paired permutation test on per-query nDCG@10, 10,000 shuffles">
- **Interval**: <for example "95% bootstrap interval on the mean difference">
- **Gates**:

| Gate | Pass when | Why it matters |
| --- | --- | --- |
| G1 | <rule> | <decision it protects> |

- **Stop rule**: <when the run is complete, and when to stop early>
- **What each outcome means**:
  - Pass: <action>
  - Fail: <action>
  - Unclear (interval crosses the threshold): <action>

## 7. Runtime

- **Purpose**: <optimisation | publication> (the `purpose` in `experiment.json`)
- **Runtime under test**: <no | yes: the runtimes compared>
- **Local models**: run each one through llama.cpp with a public GGUF file. Do not use Ollama or MLX.

| Role | Repository | File | SHA-256 | llama.cpp build | Server arguments |
| --- | --- | --- | --- | --- | --- |
| <embedding, language or decision> | <Hugging Face repository> | <file name>.gguf | <64 hex characters> | <build number> | <arguments that change output> |

- **Hosted references**: <none, or provider and model id of each reference arm>
- **Tolerance**: <largest change in each primary metric or per-item score that still counts as the same result>
- **Live check**: the runner calls `verify_llamacpp_runtime` before the first score. A mismatch stops the run.
