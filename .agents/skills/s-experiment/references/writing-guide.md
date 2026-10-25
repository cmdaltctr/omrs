# Writing guide for protocol.md and report.md

The templates give the structure. This guide gives the writing rules for `report.md` and the optional extra sections for `protocol.md`.

## Report: writing rules

1. Start with the Answer box. Put nothing above it except the title and the header list.
2. Open each section with one plain sentence, before any table.
3. Explain each term in the sentence where it first appears, for example "nDCG@10 (how well the top 10 results are ordered, from 0 to 1)".
4. Give every number its unit and direction, for example "+9 points recall" or "P95 latency 340 ms, 1.4 times the baseline".
5. Put gate IDs, amendment codes and cell names in tables and code spans. Keep them out of the opening sentences.
6. Write plain British English, with sentences of 20 words or fewer.
7. Use one idea per sentence. Do not hedge.
8. Discussion answers "why". Conclusion answers "so what". The conclusion adds no new data.
9. Keep negative and unclear results.
10. Aim for one screen of prose plus tables. Move extra detail to `analysis.py` or an appendix file.
11. Write the header as a bullet list, one `- **Field**: value` per line. Without the bullets, Markdown joins the lines into one paragraph.

## Report: two layers, exact data and plain explanation

The **data layer** stays exact: labels, gate IDs, exit codes, model names, env vars, timings and counts. They go in tables or code spans, and you never paraphrase them. A reader must be able to search the report against `output/*.json`.

The **explanation layer** is plain English: what the data means and why it matters.

| Do not write | Why it fails | Write instead |
| --- | --- | --- |
| "All 19 still named PDF, which is correct" | The label is paraphrased away, so nobody can search for it | "`document/pdf` x19" in the results table |
| "content-true labels were preserved" | Two ideas are hidden in one piece of jargon | "Magika kept the content label (`code/python`, `document/markdown`)" |
| "exit 1 by design" | Too compressed to follow | "exit 1, the mismatch flag. Every mismatch was the suffix map being wrong" |
| "H2 fails (p = 0.180, A9)" in the first paragraph | Codes before meaning | "The gain was too small to rule out chance (see Hypotheses table)" |
| Verdict below Context and Method | The reader wants the answer first | Answer box at the top |

The model: exact data with its reference, then one plain sentence saying what it means.

> All 19 PDFs renamed to `.py`, `.md` or `.txt` kept the `document/pdf` label (gate G3, exit 1, 0.24 s). Exit 1 is the mismatch flag. The suffix map disagreed on all 19, and every time the suffix map was wrong.

## Protocol: optional extra detail

Add these only when the experiment needs them. Put them after section 6, under `## Extra detail`.

| Section | Add when |
| --- | --- |
| Arms table | There are more than two arms, or one arm is a control |
| Cell matrix | You sweep more than one value |
| Environment | Hardware, model builds or runtimes affect the result |
| Frozen thresholds | A threshold is fitted on earlier data and must not move |
| Privacy and cloud | Data leaves the machine, or there is a spend cap |
| Cleanup | The run leaves large indexes or temporary files |
| Amendments | Record changes after the plan is fixed: date, reason, whether you had seen results |
