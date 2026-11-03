# Proposal: keep display maths intact when chunks merge

## Why

Context assembly merges adjacent chunks of one source into one passage. When the two texts share no exact overlap, `_join_spaced` in `src/omrs/core/retrieval/assembly.py` joins them with one space. If the first chunk ends with a closing `$$` fence on its own line, the merged passage reads `...\n$$ where again...`. A closing `$$` followed by text on the same line is not a closing fence in Markdown maths. The block stays open, swallows the prose after it, and pairs the next `$$` the wrong way round.

The `render-maths-in-web-workspace` browser check showed the effect. A search on the scratch `eq01` collection (Kingma and Welling, arXiv 1312.6114) returned 6 passages with 92 formulas. 5 formulas were wrong: each showed running prose as red "formula" source, and the formulas after it flipped between maths and prose. The stored chunks are sound: all 60 `$$` fences in the 24 stored chunks sit alone on their line, and no chunk holds an odd number of fences. Only the merge breaks them.

The same text goes to the answer model as evidence and into saved chat turns, so the fault is in the retrieval output, not in the web renderer.

## What Changes

- The join of two merged chunks that have no exact overlap puts one line break between them when the end of the left text, or the start of the right text, is a display-maths fence (a line that holds only `$$`). Every other join keeps its current form.
- The overlap-removal path is unchanged: it cuts text out of the second chunk and adds nothing new.
- Chunk text, chunk IDs, scores, `page_labels` and the diagnostics fields are unchanged.
- No new setting, no new field and no API change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `retrieval-context-assembly`: adds a requirement that a merge never joins a display-maths fence to text on the same line.

## Impact

- Code: `src/omrs/core/retrieval/assembly.py` (`_join_spaced` or one helper beside it). About 10 lines.
- Tests: new cases in the new file `tests/test_merged_maths_join.py`. No existing case changes, because none joins a `$$` fence.
- Evidence text: a merged passage with a display formula now holds a line break where it held a space. Experiments that score on text containment (Experiment 31) are expected to be unaffected, because their corpora hold few `$$` fences. Task 3.1 of this change checks it.
- Saved chats: a chat turn stores the evidence text it was given. Turns saved before this fix keep the old join and still show the fault. This change does not rewrite them.
- Web: no change. `render-maths-in-web-workspace` keeps its renderer and its tests, and its browser check (task 6.1) repeats on the fixed server.
- Docs: `docs/guides/` needs no edit unless a guide describes the join. Task 4 checks it.
