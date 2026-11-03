# Design

## Context

`_join_spaced` in `src/omrs/core/retrieval/assembly.py` is the only place that joins two merged chunk texts when no exact overlap is removed. `_merge_pair` calls it in two cases: the overlap budget is zero or a text is empty, and no suffix/prefix match fits the budget. It adds one space unless a text already has whitespace at the join. See proposal.md for the fault this causes with a closing `$$` fence.

The stored chunks are sound, so the fix belongs at the join and nowhere else.

## Goals / Non-Goals

**Goals:**

- A display-maths fence never shares a line with other text after a merge that has no exact overlap to remove.
- Every join that does not touch a fence stays byte for byte as it is.

**Non-Goals:**

- Repair of a `$$` block that the chunker cut in two. A cut block stays as the stored chunks hold it.
- Repair of chat turns saved before the fix.
- Any change to the web renderer.
- Detection of `\[ \]` or `$ $` maths. Only the `$$` fence that `dots-mocr` writes is in scope.

## Decisions

### 1. Add one line break only at a fence

A join gets `"\n"` instead of one space when the last line of the left text, or the first line of the right text, is `$$` once outer whitespace is stripped. The test reads one line from each side, so it costs nothing on long texts.

The fence test runs before the whitespace test, so a fence line that ends in a space or tab (`$$ `) still gets its line break. The join adds nothing only when the left text ends with a line break or the right text starts with one.

A left text that ends with a line break has an empty last line, so it is not a fence line and the existing whitespace rule joins the texts directly. The same holds for a right text that starts with a line break. This gives the "break already there" scenario without extra code.

A one-line `$$ x^2 $$` is not a fence line, so it keeps the space. `remark-math` reads `$$ x^2 $$ text` as inline double-dollar maths, which is correct and swallows nothing.

Alternatives rejected:

- **A blank line at every join.** A chunk can end in the middle of a sentence. A paragraph break there changes how every merged passage reads, moves the existing join tests and changes text that Experiment 31 matches by containment. The fault needs none of it.
- **A blank line instead of one line break.** It is not needed. `remark-math` 6.0.0 reads all of these as display maths with the prose outside it: `$$`, a line break, then prose; and prose, a line break, then `$$`. A blank line adds more whitespace than the fault needs.
- **The space that the code adds today.** `x\n$$ where` swallows the prose into the block, and `rewritten as: $$\nx\n$$` reads as an empty formula. Both shapes were parsed to confirm this.
- **A repair in the web renderer.** After the merge, the text no longer shows where one chunk ended, so the renderer cannot tell a joined `$$ where` from a written one. It also leaves the answer model with the broken text.

### 2. Where the code goes

The rule sits in `_join_spaced`, so both fallback paths use it. The overlap-removal path (`left + right[length:]`) cuts text and adds none, so it needs no rule.

A small helper `_is_maths_fence(line)` returns whether a line holds only `$$`. It has one caller and stays private to the module.

### 3. Test strategy

Unit tests in `tests/test_merged_maths_join.py` call `_assemble` with the texts from each scenario. A test that merges the real `eq01` shape (a chunk ending in `$$` and a chunk starting `where again`) needs no stored paper text. Each new test is run on the old code first and must fail there.

## Risks / Trade-offs

- **A code block that holds a `$$` line** (a shell snippet, for example) gets a line break at a join. This is harmless and rare.
- **Evidence text changes for answers.** The answer model reads a line break where it read a space. This only happens at a merge that touches a fence, where the old text was already broken.
- **Saved chats** keep the old text and the old fault. A re-asked question gets the fixed text.
- **Retrieval parity fixtures** (`tests/fixtures/pipeline_parity/retrieval/`) may hold a `$$` join. Task 2.4 runs them and reports any change.

## Open Questions

None.
