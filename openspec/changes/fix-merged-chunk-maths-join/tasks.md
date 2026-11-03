# Tasks

## 1. Failing tests first

- [x] 1.1 Add tests in the new file `tests/test_merged_maths_join.py` (`tests/test_context_assembly.py` already runs to 794 lines) for the scenarios in `specs/retrieval-context-assembly/spec.md`: a closing fence then prose, prose then an opening fence, an ordinary join, a one-line display formula, a break that is already there, overlap removal with a fence in the text, and a check that only whitespace is added. Use the `eq01` shape (a chunk ending in a line that holds only `$$`, a chunk starting `where again the term`) with no paper text. Verify: run `uv run --no-sync pytest tests/test_context_assembly.py -q` on the unchanged code. The fence cases fail. The ordinary-join, one-line, break-already-there and overlap cases pass.

## 2. The fix

- [x] 2.1 Add `_is_maths_fence` and the fence rule to `_join_spaced` in `src/omrs/core/retrieval/assembly.py` (design.md decisions 1 and 2). Update the module docstring line that says texts are concatenated, so it names the fence rule. Verify: the tests of 1.1 all pass.
- [x] 2.2 Break the fix on purpose: remove the fence rule, run the tests of 1.1 and confirm the fence cases fail, then restore it. Verify: the failure and the pass are both seen.
- [x] 2.3 Run `uv run --no-sync pytest tests/test_context_assembly.py tests/test_adjacent_overlap_assembly.py tests/test_merged_page_labels.py tests/test_lineage_retrieval.py -q`. Verify: all pass, and no existing test changed.
- [x] 2.4 Run the retrieval parity fixtures and the answer tests that read merged text: `uv run --no-sync pytest tests/unit/test_retrieval_graph_adapters.py tests/unit/test_answer_graph_adapters.py tests/test_answer_core.py -q`. Verify: all pass. If a parity fixture holds a `$$` join and changes, record the change in the PR description.

## 3. Evidence and experiments

- [x] 3.1 Check Experiment 31 (`run_eval.py`) for evidence text that holds a `$$` fence at a chunk join. Verify: none does, or the scoring still matches because it tests containment of text on one side of the fence. State the result in the PR description. Result: the frozen matching rule (`matching.py`, `normalise`) collapses all whitespace to one space on both sides, so a line break and a space compare equal, and `corpus_manifest.json` holds no `$$`.
- [x] 3.2 Merge the real adjacent chunks 19 and 20 of the scratch `eq01` collection through `assemble` in a script in the scratchpad (read only, on a copy of the LanceDB folder). Verify: the merged text has a line break after the closing `$$`, and the merged passage renders with 0 `.katex-error` elements in the `MathText` component from `render-maths-in-web-workspace`.

## 4. Docs and gates

- [x] 4.1 Search `docs/guides/` for a description of how merged chunks are joined (`grep -n -i "merge" docs/guides/*.md`). Verify: a guide that states the join gets one sentence about the fence rule. If none does, no edit is made. Result: no guide states the join, so no edit.
- [x] 4.2 Run `uv run --no-sync ruff check src tests`, `uv run --no-sync ruff format --check src tests` and `openspec validate fix-merged-chunk-maths-join --strict`. Verify: all pass.
- [x] 4.3 Repeat the browser check of `render-maths-in-web-workspace` task 6.1 on a scratch server from this worktree. Run the same search as before (`variational lower bound estimator`). Verify: 0 `.katex-error` elements in the 6 results, at 1280 px and at 390 px. Then tick that task.

## 5. Review fixes

- [x] 5.1 Fence lines that end in a space or tab get the line break (2 new tests in `tests/test_merged_maths_join.py`, tripwire pin 9753).

## Workflow follow-up

- Run `./scripts/local_ci.sh` only after the operator agrees. The clean-base tripwire pins the executed test count, so adding tests moves the pin: diff the collected test IDs against the last pin, as the tripwire notes in `AGENTS.md` say, and update the pin in the same commit.
- Commit with `uv run --no-sync git commit`. Do not push and do not merge without the operator's word.
