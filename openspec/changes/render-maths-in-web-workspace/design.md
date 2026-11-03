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

- `remarkPlugins`: `remark-math` with its defaults (single-dollar inline maths on, because `dots-mocr` uses `$...$`).
- `rehypePlugins`: `[rehypeKatex, KATEX_OPTIONS]`.
- `KATEX_OPTIONS`: `{ trust: false, errorColor: "var(--status-error-label)" }`. `trust: false` is the KaTeX default. The module sets it explicitly so a later edit has to remove it on purpose. The error colour is a token reference, so no literal colour enters a component.

### 3. Broken formulas: rehype-katex's own fallback

`rehype-katex` 7.0.1 does not accept `throwOnError` (its `Options` type omits it). It calls `katex.renderToString` with `throwOnError: true`. On a `ParseError` it records a message on the file and renders again with `throwOnError: false` and `strict: "ignore"`. KaTeX then returns a `span.katex-error` that holds the LaTeX source, with the error text in `title` and `errorColor` as its colour. On any other error, `rehype-katex` builds the same `span.katex-error` itself. Nothing is thrown into React. So the design uses the plugin's behaviour, which is the same as `throwOnError: false`, and adds no error boundary.

The test feeds `$\frac{a}{$` (the case in the scratch `broken.json`) and checks three things: one `.katex-error` element whose text is the source, the text after the formula still renders, and nothing is thrown.

### 4. HTML safety

- No `rehype-raw` is added. Raw HTML nodes still become text in `react-markdown`, so `<b>`, `<script>` and `<img onerror>` in an answer stay text.
- `rehype-katex` replaces only `code.language-math` elements made by `remark-math`. It parses KaTeX's own output string into hast elements. The model's text reaches KaTeX only as LaTeX source, and KaTeX escapes every character it outputs.
- With `trust: false`, KaTeX refuses `\href`, `\url`, `\includegraphics`, `\htmlClass`, `\htmlId`, `\htmlStyle` and `\htmlData`. These render as an error span with their source as text.
- KaTeX limits macro expansion (`maxExpand`, default 1000) and size (`maxSize`), which bounds a hostile formula.
- New tests: a formula with `\href{javascript:alert(1)}{x}` creates no `a` element; `$<script>$` creates no `script` element; the existing raw-HTML test still passes with the maths plugins on.

### 5. CSS and fonts through the build

- `app.css` gains `@import "katex/dist/katex.min.css" layer(vendor);` beside the React Flow import. `cascade.test.ts` already checks that every third-party import carries `layer(vendor)`.
- Vite rewrites the `url(fonts/KaTeX_*.woff2)` references in that stylesheet and copies the font files into the build output with hashed names. The `base: "./"` setting keeps the URLs relative, so they load from the OMRS server.
- A components-layer rule in `app.css` lets a wide display formula scroll inside its own box: `.katex-display { overflow-x: auto; overflow-y: hidden; }`. The page itself must not scroll sideways at 390 px.
- Tailwind preflight (base layer) loses to the KaTeX rules (vendor layer). KaTeX sets its own `display` on its SVGs, so preflight's `svg { display: block }` does not break radicals or arrows.

The build copies woff, ttf and woff2 files (60 files, about 1.2 MB). A browser reads only woff2. Copying only woff2 would need a hand-written `@font-face` set. That would be a third stylesheet or a large rule block that repeats KaTeX's CSS. This change accepts the extra disk use and measures it in tasks.

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

Search results and citation passages are raw chunk text. Rendering them as full Markdown would change how `*`, `_`, `#`, list markers and indented lines look in OCR output. So these surfaces get a new component, `components/MathText.tsx`. It uses `react-markdown` with `remark-math`, `rehype-katex` and one small remark plugin that turns off every CommonMark construct except paragraphs and maths. The plugin adds a micromark extension `{ disable: { null: [...] } }` to the parser, the same hook `remark-math` uses. The list: `attention`, `autolink`, `blockQuote`, `characterEscape`, `characterReference`, `codeFenced`, `codeIndented`, `codeText`, `definition`, `hardBreakEscape`, `headingAtx`, `htmlFlow`, `htmlText`, `labelEnd`, `labelStartImage`, `labelStartLink`, `list`, `setextUnderline`, `thematicBreak`. Paragraphs render with `whitespace-pre-wrap`, as today.

Tests pin the result: `*a* # b <i>c</i> [d](e)` renders as that exact text; `$x$` renders one `.katex` element.

Alternatives:

- KaTeX `auto-render`. It edits the DOM after React renders, so React and KaTeX would both own the same nodes. Rejected.
- A hand-written `$` splitter. It would be a second parser with rules that differ from the chat answer. Rejected.
- Full Markdown for chunk passages. A larger visible change than the operator asked for. Rejected for now.

### 8. The `eq01` fixture

The test fixture is `web/src/test/fixtures/eq01-chunks.json`. It holds the text of the stored `eq01` chunks that contain maths, copied once from the scratch collection `scratchpad/g3/lancedb-eq01` (read only). Each row keeps `chunk_id`, `source` and `text`. A header field records the source paper (arXiv 1312.6114), the collection path, the extraction date and the formula count. The test renders each chunk through `AnswerText` and through `MathText`, then counts `.katex-error` elements (must be 0) and `.katex` elements (must be at least the counted formulas). If the operator wants no paper prose in the repository, the fallback is a formulas-only fixture made from `eq01-formulas.json`, wrapped in `$` or `$$`. See Open Questions.

## Risks / Trade-offs

- **Dollar amounts.** "It costs $5 and $10" renders `5 and ` as maths, because `remark-math` reads single dollars. Likelihood is low in the current corpora (papers and reports). Impact is cosmetic. Turning off single-dollar maths would break `dots-mocr` inline maths, which is the purpose of this change. Accept, and note it in the guide.
- **A `$$` block cut by the chunker.** An open `$$` with no close runs to the end of the passage, like an open code fence. KaTeX then shows an error span with the source. The text is all still visible. Accept.
- **Bundle size.** The main script grows by about 76 kB gzip, and the build already warns at 500 kB. Task 5 measures it. If the growth crosses 100 kB gzip, a follow-up can split KaTeX into a lazy chunk. This change does not do that.
- **Wheel size.** About 1.2 MB of font files. Measured in task 5.
- **KaTeX `strict` warnings.** The default `strict: "warn"` writes a console warning for some Unicode in maths mode. This does not change the output. Accept.

## Migration Plan

None. The change is front-end only and needs no data migration. To roll back, revert the commit and run `npm ci` and `npm run build`.

## Open Questions

1. Fixture content: may the committed `eq01` fixture keep the stored chunk prose from arXiv 1312.6114, or must it hold only the formulas? The design assumes chunk text. The formulas-only fallback is ready.
2. Chat answers from some models use `\(...\)` and `\[...\]`. Should a follow-up add these delimiters (a text step before `remark-math`), or ask the answer prompt to use `$`? This change does neither.
