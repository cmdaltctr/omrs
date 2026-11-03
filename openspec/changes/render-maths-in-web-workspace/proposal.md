# Proposal: render maths in the web workspace

## Why

The OCR engine (`dots-mocr`) writes formulas as LaTeX between `$...$` and `$$...$$` in its Markdown. The web workspace has no maths renderer: `web/package.json` has only `react-markdown` 10.1.0 and `remark-gfm` 4.0.1. So a formula shows as raw LaTeX source in chat answers, in search results and in the citation passage. The OCR work already checks formulas with KaTeX 0.16.22 (`ocr-runtime-evaluation`): the scratch `eq01` collection (Kingma and Welling, arXiv 1312.6114) holds 300 formulas in 20 chunks, and all 300 render with 0 KaTeX errors. The workspace must show the same formulas as maths.

## What Changes

- **Three exact pins in the base front-end install.** `remark-math` 6.0.0, `rehype-katex` 7.0.1 and `katex` 0.16.22 go into `dependencies` in `web/package.json`. All three are MIT. They are not optional and they are not an integration.
- **Offline maths.** The KaTeX stylesheet loads through `app.css` into the `vendor` cascade layer. Vite bundles the KaTeX fonts into the build output. The page loads no file from a CDN or any other host.
- **One shared maths configuration.** One module holds the plugin lists and the KaTeX options (`trust: false`, `maxSize: 20`, a token error colour). Every surface uses it.
- **Dollar signs that are not maths stay text.** A single `$` pair is a formula only when no space follows the opening dollar sign, no space comes before the closing one, and no digit follows it (the pandoc rule). "It costs $5 and $10" and `echo $HOME and $PATH` show as written. The `$$` forms are not affected.
- **Surfaces that render maths:**
  1. Chat answer text (`chat/AnswerText.tsx`, `AnswerText`).
  2. Claims that failed verification (`chat/AnswerText.tsx`, `ClaimList`), inline maths only.
  3. Experiment Markdown files (`experiments/library/MarkdownText.tsx`).
  4. Knowledge Base search results (`knowledge-base/ResultList.tsx`): the passage text renders maths and keeps every other character as plain text.
  5. The citation popover passage (`chat/CitationPopover.tsx`, text view), which the Sources panel "Show passage" button also opens: same maths-only text.
- **Surfaces that stay as they are:** the chunk viewer (`components/ChunkViewer.tsx`, the exact stored text), run detail previews and the "Open full output" view (spec requires plain text), and the reasoning box.
- **A broken formula never breaks the page.** It shows its LaTeX source in the error colour. The rest of the text renders.
- **The raw-HTML rule stays.** HTML from the model or from a document still shows as text. KaTeX runs with `trust: false`, so a formula cannot add a link, an image or a script element.
- **No Integrations entry.** Maths rendering has no catalogue row and no Install button.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-ui-stack`: adds the shared maths renderer (exact pins, offline CSS and fonts, no Integrations entry), the broken-formula rule, the HTML safety rule for maths, and the display-formula overflow rule.
- `workspace-chat`: answers, failed claims and the citation passage render maths.
- `workspace-projects`: Knowledge Base search results render maths.
- `workspace-experiment-library`: experiment Markdown files render maths.

## Impact

- Code: `web/package.json` and `web/package-lock.json`; a new shared maths module and a maths-only text component in `web/src/components/`; edits to `AnswerText.tsx`, `MarkdownText.tsx`, `ResultList.tsx` and `CitationPopover.tsx`; one `@import` and one components-layer rule in `web/src/styles/app.css`.
- Tests: new Vitest cases with a committed `eq01` fixture and a broken-formula case. `cascade.test.ts` already requires a third-party stylesheet in the `vendor` layer, so it guards the new import. The Python clean-base tripwire counts pytest cases only, so its pin does not change.
- Build size: the KaTeX script adds about 76 kB gzip (277 kB minified). The fonts add 59 files (about 1.07 MB on disk across woff2, woff and ttf) to `src/omrs/transports/api/static/` and so to the wheel. A browser downloads only the woff2 files a formula needs. The task list measures the real numbers.
- Docs: `docs/guides/web-workspace.md` (answer text paragraph, search and citation passages) and `web/THIRD_PARTY_NOTICES.md` (new rows).
- HTTP API and Python: no change.
- Dependencies: three new npm runtime packages and their transitive packages (`mdast-util-math`, `micromark-extension-math`, `hast-util-from-html-isomorphic` and its family, `hast-util-to-text`). No Python dependency.
