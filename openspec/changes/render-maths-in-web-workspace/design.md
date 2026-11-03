# Design: render maths in the web workspace

## Context

- `dots-mocr` emits Markdown with inline maths `$...$` and display maths `$$...$$` on their own lines. Experiment 34 found that all 59 formulas on `eq01` p11 and `bd03` render in KaTeX. A scratch check on the `eq01` collection found 263 formulas (30 display, 233 inline) and 0 KaTeX 0.16.22 errors.
- The web app renders Markdown in two places only: `chat/AnswerText.tsx` (`AnswerText` and `ClaimList`) and `experiments/library/MarkdownText.tsx`. Both use `react-markdown` 10.1.0 with `remark-gfm` 4.0.1 and no rehype plugin.
- Chunk text shows as plain text with `whitespace-pre-wrap` in three places: Knowledge Base search results (`knowledge-base/ResultList.tsx`), the citation popover text view (`chat/CitationPopover.tsx`, also opened by "Show passage" in `chat/SourcesPanel.tsx`) and the chunk viewer (`components/ChunkViewer.tsx`, which says "rendered as plain text, never markup").
- Run detail previews (`experiments/runs/EvidenceRows.tsx`, `EvidenceInspector.tsx`) and "Open full output" are plain text by spec (`local-web-workspace`, "The workspace opens truncated run output": "plain text, never markup").
- `web-ui-stack` allows two stylesheets only. Third-party CSS must load through `app.css` into the `vendor` layer. Overrides of a library's own class names go in the `components` layer. `cascade.test.ts` enforces this.
- `react-markdown` turns raw HTML in the source into text, because there is no `rehype-raw`. A test pins this: `AnswerText.test.tsx`, "does not render raw HTML or script from the model".

## Goals / Non-Goals

**Goals:**

- Render `$...$` and `$$...$$` as maths in chat answers, failed claims, experiment Markdown files, Knowledge Base search results and the citation passage.
- Ship the renderer in the base front-end build, with its CSS and fonts bundled, and with no network request at runtime.
- Keep the raw-HTML rule: HTML from the model or a document never becomes an element.
- Keep a broken formula local: it shows its source, and the page keeps working.

**Non-Goals:**

- `\(...\)` and `\[...\]` delimiters. `remark-math` does not read them. See Open Questions.
- Maths in the chunk viewer, in run previews, in "Open full output" or in the reasoning box. These show exact text on purpose.
- Any Integrations page entry, setting or switch for maths.
- Any change to the answer prompt, the HTTP API or Python code.
- A KaTeX upgrade. The pin stays at 0.16.22, the version the OCR evaluation measures with, although npm now offers 0.19.1.

## Decisions

### 1. Exact pins in `dependencies`

Add `"remark-math": "6.0.0"`, `"rehype-katex": "7.0.1"` and `"katex": "0.16.22"` with no range prefix, like every other entry in `web/package.json`. `rehype-katex` 7.0.1 asks for `katex@^0.16.0`, so npm can resolve it to the one top-level copy at 0.16.22. A task checks `npm ls katex` for exactly one copy. If npm keeps a second copy, add an `overrides` entry that pins `katex` to 0.16.22.

npm registry and package licence files (checked 2026-11-03): `remark-math` 6.0.0 MIT, `rehype-katex` 7.0.1 MIT, `katex` 0.16.22 MIT (`Copyright (c) 2013-2020 Khan Academy and other contributors`). The KaTeX fonts ship inside the `katex` package. A task confirms their licence terms before the notices are written.

Alternative: a lazy-loaded optional chunk behind the Integrations page. Rejected by the operator: maths is part of reading documents, not an add-on.

### 2. One shared maths module

A new module `web/src/lib/maths.ts` exports the plugin lists and the KaTeX options. Every surface imports from it, so the options cannot drift.

- `remarkPlugins`: `remark-math` with its defaults (single-dollar inline maths on, because `dots-mocr` uses `$...$`), then a small plugin that turns an `inlineMath` node back into the text it was parsed from when the single-dollar pair breaks the pandoc rule (decision 9).
- `rehypePlugins`: `[rehypeKatex, KATEX_OPTIONS]`.
- `KATEX_OPTIONS`: `{ trust: false, maxSize: 20, errorColor: "var(--status-error-label)" }`. `trust: false` is the KaTeX default. The module sets it explicitly so a later edit has to remove it on purpose. `maxSize` is in em; KaTeX's default is unlimited, so a `\rule{5000em}{5000em}` would draw a block about 80,000 px square. The error colour is a token reference, so no literal colour enters a component.

### 3. Broken formulas: rehype-katex's own fallback

`rehype-katex` 7.0.1 does not accept `throwOnError` (its `Options` type omits it). It calls `katex.renderToString` with `throwOnError: true`. On a `ParseError` it records a message on the file and renders again with `throwOnError: false` and `strict: "ignore"`. KaTeX then returns a `span.katex-error` that holds the LaTeX source, with the error text in `title` and `errorColor` as its colour. On any other error, `rehype-katex` builds the same `span.katex-error` itself. Nothing is thrown into React. So the design uses the plugin's behaviour, which is the same as `throwOnError: false`, and adds no error boundary.

The test feeds `$\frac{a}{$` (the case in the scratch `broken.json`) and checks three things: one `.katex-error` element whose text is the source, the text after the formula still renders, and nothing is thrown.

### 4. HTML safety

- No `rehype-raw` is added. Raw HTML nodes still become text in `react-markdown`, so `<b>`, `<script>` and `<img onerror>` in an answer stay text.
- `rehype-katex` replaces only `code.language-math` elements made by `remark-math`. It parses KaTeX's own output string into hast elements. The model's text reaches KaTeX only as LaTeX source, and KaTeX escapes every character it outputs.
- With `trust: false`, KaTeX refuses `\href`, `\url`, `\includegraphics`, `\htmlClass`, `\htmlId`, `\htmlStyle` and `\htmlData`. KaTeX shows the command name as plain text in the error colour and adds no element.
- KaTeX limits macro expansion (`maxExpand`, default 1000). Its `maxSize` default is unlimited, so `KATEX_OPTIONS` sets `maxSize: 20`, which bounds a `ule` or a box.
- New tests: a formula with `\href{javascript:alert(1)}{x}` creates no `a` element; `$<script>$` creates no `script` element; the existing raw-HTML test still passes with the maths plugins on.

### 5. CSS and fonts through the build

- `app.css` gains `@import "katex/dist/katex.min.css" layer(vendor);` beside the React Flow import. `cascade.test.ts` already checks that every third-party import carries `layer(vendor)`.
- Vite rewrites the `url(fonts/KaTeX_*.woff2)` references in that stylesheet and copies the font files into the build output with hashed names. The `base: "./"` setting keeps the URLs relative, so they load from the OMRS server.
- A components-layer rule in `app.css` lets a wide display formula scroll inside its own box: `.katex-display { overflow-x: auto; overflow-y: hidden; }`. The page itself must not scroll sideways at 390 px.
- Tailwind preflight (base layer) loses to the KaTeX rules (vendor layer). KaTeX sets its own `display` on its SVGs, so preflight's `svg { display: block }` does not break radicals or arrows.

The build copies woff, ttf and woff2 files (59 files, about 1.07 MB). A browser reads only woff2. Copying only woff2 would need a hand-written `@font-face` set. That would be a third stylesheet or a large rule block that repeats KaTeX's CSS. This change accepts the extra disk use and measures it in tasks.

### 6. Surfaces

| Surface | File | Today | After |
|---|---|---|---|
| Chat answer | `chat/AnswerText.tsx` `AnswerText` | Markdown (GFM) | Markdown (GFM) and maths |
| Failed claims | `chat/AnswerText.tsx` `ClaimList` | Inline Markdown, allow list `p, strong, em, code` | Same, plus inline maths |
| Experiment file | `experiments/library/MarkdownText.tsx` | Markdown (GFM) | Markdown (GFM) and maths |
| Search result passage | `knowledge-base/ResultList.tsx` | Plain text | Maths-only text |
| Citation passage (popover and "Show passage") | `chat/CitationPopover.tsx` | Plain text | Maths-only text |
| Chunk viewer | `components/ChunkViewer.tsx` | Plain text | Unchanged: shows the exact stored text |
| Run previews and full output | `experiments/runs/*` | Plain text (spec) | Unchanged |
| Reasoning box | `chat/ReasoningBox.tsx` | Plain text | Unchanged |

`ClaimList` keeps its allow list. `react-markdown` applies `allowedElements` after the rehype plugins, so the list would unwrap KaTeX's spans and leave its MathML and HTML text twice. The claim filter therefore uses `allowElement`: an element passes when its tag is in the allow list, when it is a KaTeX root (`span.katex`, `span.katex-display` or `span.katex-error`), or when its parent passed as part of a KaTeX tree. A test checks that a claim with `$x^2$` holds one `.katex` element, and that a heading in a claim still drops to text.

Citation markers do not change. `CitedText` splits only string children, and KaTeX output reaches it as elements, so `[1]` inside a formula never becomes a button.

### 7. Maths-only text for chunk passages

Search results and citation passages are raw chunk text. Rendering them as Markdown would change how `*`, `_`, `#`, list markers, indentation and trailing spaces look in OCR and source text. So these surfaces get a new component, `components/MathText.tsx`. It parses the text with `remark-math` and one small remark plugin. The plugin keeps only the maths nodes of the tree, cuts the source between them into plain text nodes and drops the rest of the Markdown tree. Every non-maths character therefore stays exactly as stored. `mdast-util-to-hast` trims the spaces around every line break of a plain text node, so each text node goes through a `span` (`data.hName` and `hChildren`), which it leaves alone. The wrapper is `whitespace-pre-wrap`. A display formula owns the line break before its opening `$$` and after its closing `$$`, because the block is a line of its own. An earlier draft disabled the CommonMark constructs in the parser. That kept most characters but still stripped indentation and trailing spaces, because paragraph rules run on the rest.

Tests pin the result: `*a* # b <i>c</i> [d](e)` renders as that exact text; indentation, tabs, trailing spaces and runs of blank lines are kept; `$x$` renders one `.katex` element; shell and PHP dollar signs stay text.

Alternatives:

- KaTeX `auto-render`. It edits the DOM after React renders, so React and KaTeX would both own the same nodes. Rejected.
- A hand-written `$` splitter. It would be a second parser with rules that differ from the chat answer. Rejected.
- Full Markdown for chunk passages. A larger visible change than the operator asked for. Rejected for now.

### 8. The `eq01` fixture

The test fixture is `web/src/test/fixtures/eq01-chunks.json`. It holds the formulas of the stored `eq01` chunks that contain maths (300 formulas, 30 of them display, in 20 chunks), copied once from the scratch collection `scratchpad/g3/lancedb-eq01` (read only). Each row keeps `chunk_id`, `source`, the formula counts and a `text` of the formulas joined by blank lines. The header records the source paper (arXiv 1312.6114), the collection, the extraction date and the counts, and says the file holds no paper prose. The tests render each chunk through `AnswerText`, `MathText` and `ResultList`, then count `.katex-error` elements (must be 0) and `.katex` elements (must be at least the counted formulas). The operator chose formulas only, so the repository holds none of the paper's text.

### 9. The dollar rule

`remark-math` reads `$5 and $` as a formula. KaTeX then drops the spaces in maths mode, so "another $40 more. A ton of coal is another $" shows as italic run-together letters. The review found 17 such spans in 5 of the 43 tracked `dots_mocr` pages of the experiments, which the experiment library opens through `MarkdownText`. So `lib/maths.ts` adds a plugin after `remark-math`: it reads the source of each `inlineMath` node and, for a single-dollar pair, keeps it as maths only when no space follows the opening dollar sign, no space comes before the closing one, and no digit follows it. Otherwise the node becomes text again. A `$$ ... $$` pair on one line is never changed. All five surfaces share the rule because they share the plugin list.

## Risks / Trade-offs

- **Dollar amounts.** Decision 9 keeps "It costs $5 and $10" as text. A rare shape still reads as maths: a span with no space inside its dollar signs and no digit after the closing one, such as `$a$` in a price list. The result is a formula, as it would be in LaTeX. Accept.
- **A `$$` block cut by the chunker.** An open `$$` with no close runs to the end of the passage, like an open code fence. KaTeX then shows an error span with the source. The text is all still visible. Accept.
- **Bundle size.** The main script grows by about 76 kB gzip, and the build already warns at 500 kB. Task 5 measures it. If the growth crosses 100 kB gzip, a follow-up can split KaTeX into a lazy chunk. This change does not do that.
- **Wheel size.** About 1.07 MB of font files. Measured in task 5.
- **KaTeX `strict` warnings.** The default `strict: "warn"` writes a console warning for some Unicode in maths mode. This does not change the output. Accept.

## Migration Plan

None. The change is front-end only and needs no data migration. To roll back, revert the commit and run `npm ci` and `npm run build`.

## Open Questions

1. Resolved: the operator chose formulas only for the `eq01` fixture. Nothing from the paper's prose is committed.
2. Chat answers from some models use `\(...\)` and `\[...\]`. Should a follow-up add these delimiters (a text step before `remark-math`), or ask the answer prompt to use `$`? This change does neither.
