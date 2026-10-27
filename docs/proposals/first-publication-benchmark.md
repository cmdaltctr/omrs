# First publication: a reproducible local RAG benchmark of OMRS

Draft 1, 27 October 2026. Plan only. Nothing here is built or run yet.

This is the first paper of the fellowship programme. The manṭiq work in `v4` (authority-aware retrieval and reasoning gates) comes after it. This paper does not wait for that work.

Related records:

- `openspec/changes/archive/2026-10-27-reproducible-experiment-runtime/carry-forward.md`: which past experiments go forward.
- `openspec/changes/experiment-35-full-document-rag-benchmark/`: the existing Experiment 35 plan (0 of 42 tasks done). This proposal updates it.
- ADR-103: local models in experiments run through llama.cpp with a public GGUF file.

## Summary

OMRS is a local-first, modular RAG framework. The paper reports one Confirmatory benchmark of the full pipeline on three public datasets from three domains: finance, software and biomedicine. Every local model runs through llama.cpp with a pinned GGUF file and build, so another group can repeat the run on another machine. The paper also reports which pipeline choices help, using ablations: we switch one component on or off and measure the change.

The claim is modest and testable: on these public benchmarks, with these pinned models, OMRS reaches these scores, and these choices change them by these amounts.

## Why now

- Past experiments (1 to 43) were optimisation runs. Many used Ollama, small question sets (for example 17 queries) or remain unfinished. They cannot be cited as they are.
- ADR-103 now gives a reproducible runtime and a `publication` purpose that the checker enforces.
- A systems paper with honest, pinned results is achievable in this fellowship period. It also gives the manṭiq papers a tested base to build on.

## Work in two steps

### Step 1: pipeline sweep (optimisation, Standard)

One end-to-end run on llama.cpp only, on a small fixed set, before the main run. It checks each stage after the move off Ollama:

1. Ingest PDFs and text (reader, OCR routing, normalisation).
2. Chunk, embed, and write to LanceDB.
3. Search: dense, hybrid, and hybrid with the reranker.
4. Answer, with and without claim checking.
5. Write run records with the found runtime (live-server check).

Base: Experiment 3 (end-to-end smoke test). Exit rule: every stage runs without error, and the scores are close to the earlier Ollama numbers where those exist. Any failure is fixed before Step 2.

### Step 2: Experiment 35 as a `publication` experiment (Confirmatory)

| Dataset | Domain | Questions | Corpus | Gold labels | Licence |
|---|---|---|---|---|---|
| FinanceBench (open sample) | Finance, real PDFs | 150 | 10-K and similar filings | Gold document and page | CC BY-NC 4.0 |
| FreshStack, LangChain slice | Software | 223 | 10,024 documents | Gold documents | CC BY-SA 4.0 |
| BioASQ (`enelpol/rag-mini-bioasq`, test split) | Biomedicine | 707 | 40.2K PubMed abstracts | Gold passages and reference answers | CC BY 2.5 |

RepoProbe (code answers judged by an LLM) moves to a later paper. It has no retrieval labels.

Fallback for the medical arm: NFCorpus (retrieval scores only). Check its academic-use terms first.

Gap: no open medical dataset has real PDFs with page-level gold evidence. FinanceBench is the PDF arm.

#### Arms

| Arm | What changes | Past evidence it carries forward |
|---|---|---|
| Baseline | `documents` profile defaults, with Qwen3-Embedding-4B (local GGUF) | Experiment 3; Experiment 22 used 4B through OpenRouter |
| Embedding size | 0.6B in place of the 4B baseline | Experiments 2 and 22 |
| Embedding size, upper | 8B in place of the 4B baseline | Experiment 2 (0.6B and 8B tied on an easy 17-query set) |
| Reranker | Off against on | Experiments 10b and 15 (the reranker hurt technical retrieval) |
| Chunking | Token-aware chunking off against on | Experiment 25 |

Each ablation changes one component against the baseline. All arms run on the same questions.

#### Metrics

Primary (gold labels, no judge):

- Recall@10, MRR@10, nDCG@10.
- Hit@page (FinanceBench only): a retrieved chunk comes from the gold page of the gold document.

Secondary (LLM judge): Ragas 0.4.3, with faithfulness, answer relevancy, context precision and context recall. Ragas never replaces the primary metrics.

- Pin the Ragas version, the judge model and its settings, temperature 0.
- Run the judge through llama.cpp when possible, so it can be repeated.
- Check about 50 judged items by hand and report the agreement.

Latency: median (p50) and 95th percentile (p95) per query, without warm-up.

#### Repetitions

Each arm runs 3 times.

- Retrieval with a fixed index and a deterministic embedder gives the same result each run. Run 1 is scored. Runs 2 and 3 must match it exactly. This is the determinism check, and the paper reports it.
- The 3 runs measure the stages that can change between runs: the generated answer, the Ragas judge, index-build order and latency. Report the run-to-run standard deviation for these.
- Statistical tests compare arms question by question. Average the 3 runs for each question first.

#### Statistics (basic set)

For each dataset and arm:

1. Mean, with a 95% confidence interval. Use a bootstrap over questions for scores, and a Wilson interval for hit rates.
2. Difference from the baseline, with a paired 95% confidence interval. This is the main number.
3. One paired test for each comparison:
   - a permutation test for scores;
   - McNemar's exact test for hit or miss.
4. Holm correction across the arms of one dataset.
5. Wins, losses and ties per question, as a plain effect size.
6. The minimum detectable effect, stated before the run. About 4 points at 150 to 223 questions, and about 2 points at 707.

All of these exist in `.agents/skills/s-experiment/references/stats.py` and `experiments/_lib/stats.py`. Plain nDCG@10 and hit@page are new.

One table for each dataset:

| Arm | n | Recall@10 [CI] | MRR@10 [CI] | nDCG@10 [CI] | Hit@page % [CI] | Δ nDCG@10 [paired CI] | p (Holm) | W/L/T | Faithfulness ± run SD | Answer relevancy ± SD | Context P / R ± SD | Latency p50 / p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

#### Runtime and models

Embedding model: Qwen3-Embedding-4B is the baseline, from the public `Qwen/Qwen3-Embedding-4B-GGUF` file. The 0.6B model is the ablation arm. Reasons:

- The evidence that 0.6B matches 8B (Experiment 2, ADR-009) comes from 17 queries on 6 documents. Both models scored 100% Hit@1, so that test could not separate them.
- No experiment yet compares 0.6B and 4B under the same conditions. Experiment 22 (4B) and Experiment 9a (0.6B) differ in model, width, store and chunking.
- No experiment compares 4B with 8B. An 8B arm on all three datasets measures that gap, so the three sizes are compared on equal terms. The paper claims only what this arm shows.
- Task 1.4 of Experiment 35 still times local 4B on the measurement Mac. If local 4B does not fit the time budget, OpenRouter `qwen/qwen3-embedding-4b` becomes the reference arm, named as hosted (ADR-103).


- All local models through llama.cpp. Pin the repository, file, SHA-256, build and server arguments in the `runtime` block of `plan.json`.
- The live-server check runs before the first score of each run.
- Hosted models only as named reference arms.

## Publication rules

Sources: Taylor & Francis "streamlining how we describe research outputs", and the Edinburgh Napier open access guide and policy (v3.0).

Article type: Software Tool Article. It must give:

- the reason the tool was built;
- details of the code;
- example input data;
- example output, and how to read it.

The alternative is a Research Article. F1000Research is in the Napier Taylor & Francis deal. Ask repository@napier.ac.uk to confirm that the deal covers a Software Tool Article.

Before submission:

1. Confirm that the journal is in a Napier deal. Check it in DOAJ and with Think. Check. Submit.
2. Tell co-authors that the Napier open access policy applies to them.

At submission:

3. Be the corresponding author with the Napier affiliation and Napier email.
4. Add the rights retention sentence to the funding acknowledgement and the cover letter: "For the purpose of open access, the author has applied a Creative Commons Attribution (CC BY) 4.0 license to any Author Accepted Manuscript version arising from this submission."

On acceptance:

5. Deposit the accepted manuscript in Worktribe within 3 months.
6. Put the data and code DOI (Zenodo) in Worktribe.

After publication:

7. Record the dataset and the code in Worktribe as their own outputs, linked to the paper.

The journal's own author guide covers ORCID, CRediT, the funding wording, conflicts of interest, AI-tool disclosure and preprints. The Napier pages do not.

## What the publication rules change in the experiment

1. Build a small example set that we may share, with its expected output and a short guide to reading it. The Software Tool Article needs it.
2. Separate shareable outputs from restricted ones in `output/`.
3. Respect the dataset licences:
   - FinanceBench is CC BY-NC. Do not release its text or derived files under CC BY.
   - FreshStack is CC BY-SA. Release derived files under CC BY-SA.
   - BioASQ is CC BY 2.5.
   - Publish scores, question IDs and scripts that rebuild the data. Do not publish the corpus text.
4. Archive code and outputs on Zenodo with a DOI. Keep each dataset's derived files in their own archive with their own licence.
5. Before the repository or a release goes public, remove names and home-folder paths.

## Risks

| Risk | Response |
|---|---|
| A small difference between llama.cpp back ends (Metal, CUDA, CPU) | The plan states a tolerance per metric (ADR-103) |
| The Ragas judge disagrees with people | Report hand-check agreement. Keep Ragas secondary. |
| Index building on 40K abstracts takes too long on the Mac | Time the pipeline sweep first. Subset BioASQ by question type if needed, and freeze the subset before scoring. |
| The reranker result changes on llama.cpp | Report it as found. A negative result is still a result. |
| The journal deal does not cover the article type | Ask the library before writing. Research Article is the fallback. |

## Next steps

1. Propose the pipeline sweep as an OpenSpec change (optimisation, Standard).
2. Update `experiment-35-full-document-rag-benchmark` with `/opsx:update`:
   - `publication` purpose and BioASQ;
   - the ablation arms and the 3-run policy;
   - the statistics set and the data-sharing split;
   - RepoProbe moved out.
3. Ask the Napier library to confirm the article type and the deal.
4. Run Step 1, then freeze the Step 2 protocol and plan before the first measured run.

## Sources checked on 27 October 2026

- FinanceBench, arXiv 2311.11944.
- FreshStack, arXiv 2504.13128.
- MedRAG and MIRAGE, arXiv 2402.13178.
- BEIR, arXiv 2104.08663.
- Ragas, arXiv 2309.15217. Version 0.4.3 on PyPI is dated 13 January 2026.
- Miller 2024, "Adding Error Bars to Evals", arXiv 2411.00640.
- Smucker, Allan and Carterette 2007, CIKM, doi:10.1145/1321440.1321528.
- RAGPerf, arXiv 2603.10765.
- BERGEN, arXiv 2407.01102. Its DOI did not resolve in CrossRef, so check it before citing.
- Hugging Face cards: `enelpol/rag-mini-bioasq`, `BeIR/nfcorpus`, `patronus-ai/financebench`, `freshstack/corpus-oct-2024`.
- Taylor & Francis: <https://editorresources.taylorandfrancis.com/welcome-to-tf/policies-guidelines/streamlining-how-we-describe-research-outputs/>.
- Edinburgh Napier: <https://libguides.napier.ac.uk/c.php?g=685910&p=5352291>, the linked open access policy pages, and Open Access Policy v3.0.
