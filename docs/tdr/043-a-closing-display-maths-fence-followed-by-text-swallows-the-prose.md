# TDR-043: A closing display-maths fence followed by text swallows the prose

- **Date:** 2026-11-03
- **Status:** Accepted (2026-11-03)
- **Deciders:** Maintainer
- **Tags:** retrieval | context-assembly | maths | chunk-merge

## Context

The browser check of [ADR-111](../adr/111-the-web-workspace-renders-maths-with-bundled-katex.md) searched the `eq01` collection (Kingma and Welling, arXiv 1312.6114). The search returned 6 passages with 92 formulas. 5 of them were wrong: each showed running prose as red "formula" source, and the formulas after it flipped between maths and prose.

The stored chunks were sound. All 60 `$$` fences in the 24 stored chunks sit alone on their line, and no chunk holds an odd number of fences.

### Root cause

Context assembly merges adjacent chunks of one source. When the two texts share no exact overlap, `_join_spaced` in `src/omrs/core/retrieval/assembly.py` joined them with one space. A chunk that ended with a closing `$$` on its own line then read `...\n$$ where again...`.

In Markdown maths, a `$$` followed by text on the same line is not a closing fence. The block stays open, swallows the prose after it, and pairs the next `$$` the wrong way round. A real `remark-math` parse confirmed it. The same text goes to the answer model and into saved chat turns, so the fault was in the retrieval output, not in the web renderer.

## Decision

Change only the join. When the last line of the left text, or the first line of the right text, is `$$` after outer whitespace is stripped, the join is one line break. The fence test runs before the whitespace test, so `$$ ` and `$$` followed by a tab get the break too. Every other join stays as it was.

1. The overlap-removal path is unchanged. It cuts text and adds nothing.
2. A text that already ends or starts with a line break gets no extra one.
3. A one-line `$$ x^2 $$` is not a fence line and joins as before.
4. Only whitespace is added. Chunk text, IDs, scores and `page_labels` are unchanged.

## Consequences

- **Positive:** the same search went from 5 errors in 92 formulas to 0 errors in 109 formulas. Real `eq01` chunks 19 and 20 merged through `assemble` render 26 formulas with 0 errors.
- **Positive:** the answer model reads the same corrected text.
- **Negative:** chat turns saved before the fix keep the old join and still show the fault.
- **Neutral:** Experiment 31 is unaffected. Its matching rule collapses whitespace, and its corpus manifest has no `$$`.

## Alternatives Considered

| Option | Why not |
| --- | --- |
| A blank line at every join | Needless: `$$\nx\n$$` is enough. It also splits ordinary sentences and moves other tests. |
| A line break at every join | Moves existing join tests and Experiment 31 containment matching. |
| Repair it in the web renderer | The answer model reads the broken text too. |
| Re-chunk so fences never end a chunk | The stored chunks are sound. The fault is only in the merge. |

## How to Recognise / Handle This Again

- A search result shows red formula source that holds running prose: print the merged passage and look for a line that holds `$$` followed by text.
- Check the stored chunks first. If every `$$` sits alone on its line, the fault is in the join.
- Tests: `tests/test_merged_maths_join.py`.

## Revisit Triggers

- The chunker starts to cut a `$$` block in two. That needs its own fix.
- Another maths delimiter, such as `\[ \]`, appears in stored text.

## References

- `openspec/changes/archive/2026-11-03-fix-merged-chunk-maths-join/`
- PR #165
