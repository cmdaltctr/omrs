# Tasks

Work in `/Users/aizat/Development/PROJECTS/om-systems/omrs/omrs-feat-render-maths` on `feat/render-maths-in-web-workspace`. Run `npm ci` in `web/` first (a new worktree has no `node_modules/`). Do not run Prettier.

## 1. Dependencies and licences

- [ ] 1.1 Record the baseline before any change: run `npm run build` in `web/` and save the size of each emitted file, the gzip size of the main script, the chunk-size warning text and the total size of `src/omrs/transports/api/static/`. Verify: the numbers are in the PR description draft.
- [ ] 1.2 Add `"katex": "0.16.22"`, `"rehype-katex": "7.0.1"` and `"remark-math": "6.0.0"` to `dependencies` in `web/package.json`, in alphabetical order with exact versions. Run `npm install` to update `web/package-lock.json`. Verify: `npm ls katex` lists one copy at 0.16.22. If it lists two, add an `overrides` entry for `katex` and run `npm install` again.
- [ ] 1.3 Confirm the licence of each new runtime package from its `LICENSE` file and `package.json` in `node_modules/`: `katex`, `rehype-katex`, `remark-math`, and every new transitive package that `npm ls --omit=dev` shows (expected: `mdast-util-math`, `micromark-extension-math`, `hast-util-from-html-isomorphic`, `hast-util-from-dom`, `hast-util-from-html`, `hast-util-to-text`, `hastscript`, `web-namespaces`, `unist-util-find-after`, `unist-util-remove-position`, `parse5` and `entities` if pulled in). Confirm the KaTeX font licence terms from the `katex` package. Verify: a list of package, version and licence; every licence is permissive. Stop and ask the operator if one is not.
- [ ] 1.4 Add the rows to `web/THIRD_PARTY_NOTICES.md` under "Bundled runtime packages": `katex` (with a note that its fonts are bundled), `rehype-katex`, `remark-math`, and the new unified-family packages in the existing `remark-gfm` family row or a new family row. Update the "Versions are from `web/package-lock.json` on" date. Verify: `grep -n "katex\|remark-math\|rehype-katex" web/THIRD_PARTY_NOTICES.md` shows each package.

## 2. Shared maths module and stylesheet

- [ ] 2.1 Write failing tests first in `web/src/lib/maths.test.ts`: `KATEX_OPTIONS.trust` is `false`; `errorColor` is `var(--status-error-label)`; the package pins in `web/package.json` are the exact versions from design.md. Verify: the tests fail because the module does not exist.
- [ ] 2.2 Add `web/src/lib/maths.ts` with `remarkMathPlugins`, `rehypeMathPlugins` and `KATEX_OPTIONS` (design.md decision 2). Verify: the tests from 2.1 pass.
- [ ] 2.3 Add `@import "katex/dist/katex.min.css" layer(vendor);` to `web/src/styles/app.css` after the React Flow import, and add the `.katex-display` overflow rule in the `components` layer with a one-line comment. Update the app.css header comment that lists vendor CSS. Verify: `npm test -- src/styles/cascade.test.ts` passes, and it fails when `layer(vendor)` is removed from the new import.

## 3. Fixture and Markdown surfaces

- [ ] 3.1 Build `web/src/test/fixtures/eq01-chunks.json` from the scratch collection `/private/tmp/claude-501/-Users-aizat-Development-PROJECTS-om-systems-omrs-omrs-v3/1aee3d32-8b8e-40ec-bbfe-d8f0e3eac6b4/scratchpad/g3/lancedb-eq01` (open it read only; do not write to it). Keep every chunk that contains `$`, with `chunk_id`, `source` and `text`. Add a header with the paper (arXiv 1312.6114), the collection path, the date and the formula count. If the scratch folder is gone, rebuild the chunks from `~/Development/DATA/omrs/experiments/37-dots-mocr-routing-acceptance-2026-09-30/output/dots-mocr/eq01` (read only). Apply the operator's answer to Open Question 1 first. Verify: extract the fixture's formulas with the regexes in `scratchpad/g3/katex/extract.py`, run `node scratchpad/g3/katex/check.mjs` on them, get 0 errors, and record the formula count.
- [ ] 3.2 Write failing tests in `web/src/chat/AnswerText.test.tsx`: each fixture chunk renders with 0 `.katex-error` elements and at least as many `.katex` elements as its formulas; the broken formula `Before $\frac{a}{$ after` gives one `.katex-error` with the source text and still renders `after`; `$x$ <b>raw</b><script>window.__x = 1</script>` creates no `b` or `script` element; `$\href{javascript:alert(1)}{x}$` creates no `a` element; `[1]` next to a formula stays a citation button. Add the `ClaimList` cases from the `workspace-chat` delta. Verify: the maths tests fail on the current code, and the existing raw-HTML test still passes.
- [ ] 3.3 Add the shared plugins to `AnswerText` and `ClaimList`. In `ClaimList`, replace `allowedElements` with an `allowElement` test that also passes KaTeX roots and their descendants (design.md decision 6). Verify: all `AnswerText.test.tsx` tests pass, and the fixture test fails when `rehypeMathPlugins` is removed from `AnswerText`.
- [ ] 3.4 Write failing tests in `web/src/experiments/library/MarkdownText.test.tsx` for the two `workspace-experiment-library` scenarios, then add the shared plugins to `MarkdownText`. Verify: the new tests pass and the existing link-safety test still passes.

## 4. Maths-only text for chunk passages

- [ ] 4.1 Write failing tests in `web/src/components/MathText.test.tsx`: `*a* # b <i>c</i> [d](e)` renders as that exact text; `$x$` gives one `.katex`; a fixture chunk gives 0 `.katex-error`; line breaks stay; a broken formula stays local. Verify: the tests fail because the component does not exist.
- [ ] 4.2 Add `web/src/components/MathText.tsx` with the remark plugin that disables the CommonMark constructs listed in design.md decision 7. Verify: the tests from 4.1 pass, and the `*a*` test fails when `attention` is removed from the list.
- [ ] 4.3 Use `MathText` for the passage in `knowledge-base/ResultList.tsx` and for the text view in `chat/CitationPopover.tsx`. Leave `components/ChunkViewer.tsx` unchanged. Add tests for the `workspace-projects` scenarios and for the citation passage and chunk viewer scenarios in the `workspace-chat` delta, in the existing test files for these views. Verify: the new tests pass and fail when the view goes back to plain `{text}`.

## 5. Gates and measurement

- [ ] 5.1 Run the four gates in `web/`: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`. Verify: all four pass. Each new and changed file stays under 500 lines.
- [ ] 5.2 Measure the build against the baseline from 1.1: main script size and gzip size, the KaTeX CSS size, the number and total size of font files, and the total size of `src/omrs/transports/api/static/`. Confirm that `grep -rn "cdn.jsdelivr\|unpkg\|googleapis" src/omrs/transports/api/static/` finds no KaTeX reference. Verify: the table is in the PR description. If the main script grows by more than 100 kB gzip, tell the operator before merge (design.md, Risks).
- [ ] 5.3 Check the clean-base tripwire result in the `./scripts/local_ci.sh` run of task 6.3. Verify: the executed-count pin is unchanged, because this change adds Vitest cases only. If a Python test is added after all, update the pin by test ID as the tripwire comment says.

## 6. Browser check, docs and CI

- [ ] 6.1 Browser check with a local `omrs web` on a free port and a scratch config and workspace (never `~/.omrs` or `~/.config/omrs`), with the `eq01` scratch collection. Use `chrome-devtools`; switch to the `orca-cli` browser if Chrome is missing. At 1280 px and at 390 px, in light and dark theme: a Knowledge Base search for "variational lower bound" shows rendered formulas; a chat answer with `$...$` and `$$...$$` renders (or a stored chat with that text); the citation popover passage renders; a long display formula scrolls in its own box at 390 px with no page sideways scroll; the network list shows KaTeX font requests to the local server only and none to another host; the console shows no error. Save screenshots in the scratchpad. Stop the server after. Verify: each item is checked and the screenshot paths are in the PR description.
- [ ] 6.2 Update `docs/guides/web-workspace.md`: in the answer text paragraph, state that `$...$` and `$$...$$` render as maths, that a formula that cannot be read shows its source in red, and that dollar amounts can render as maths; in the Knowledge Base and citation text, state that passages render maths and keep other characters as written, and that the chunk viewer shows the stored text. Use ASD-STE100 style, British English and no em dashes. Verify: `grep -n "maths" docs/guides/web-workspace.md` shows the new lines.
- [ ] 6.3 Run `./scripts/local_ci.sh` and `openspec validate render-maths-in-web-workspace --strict`. Verify: both pass with no `SKIPPED` step.

## Workflow follow-up

- Open a pull request from `feat/render-maths-in-web-workspace` into `v3`. Do not merge; wait for the operator.
- Watch CI until every check ends, and answer every review thread.
- Archive the change after merge and verification.
