# ADR-111: The Web Workspace Renders Maths with Bundled KaTeX

- **Date:** 2026-11-03
- **Status:** Accepted (2026-11-03; built and merged in PR #165)
- **Deciders:** Maintainer
- **Related:** [ADR-072](072-modular-ocr-engines-dots-mocr-primary-and-maths-routing.md) (`dots-mocr` writes maths as `$...$` and `$$...$$`), [TDR-043](../tdr/043-a-closing-display-maths-fence-followed-by-text-swallows-the-prose.md) (the merge fault that the browser check found)
- **Change:** `openspec/changes/archive/2026-11-03-render-maths-in-web-workspace/`

## Context

OCR of maths pages gives LaTeX between dollar signs. The web workspace showed that text as raw source, so a search result for a paper such as Kingma and Welling (arXiv 1312.6114) read as a wall of backslashes.

The workspace is local-first and works offline. Chunk text is raw OCR or source text, so it must not be read as Markdown. Chat answers are Markdown, and the rule that raw model HTML is never rendered stays.

## Decision

1. **Use KaTeX through `remark-math` and `rehype-katex` inside the existing `react-markdown` pipeline.** Exact pins: `katex` 0.16.22, `remark-math` 6.0.0, `rehype-katex` 7.0.1. The lockfile holds one `katex` copy. The CSS and the 59 font files ship in the web bundle, under the `vendor` cascade layer. There is no CDN call.

2. **One module holds the configuration.** `web/src/lib/maths.ts` exports the KaTeX options and the plugin lists, and every surface imports them. Options: `trust: false` (so `\href`, `\url`, `\includegraphics` and `\html*` render as plain command names and add no element), `maxSize: 20`, and `errorColor` from the `--status-error-label` token. A formula that fails to parse shows its source in the error colour and never throws into React.

3. **A single `$` pair is maths only under the pandoc rule.** No space after the opening `$`, no space before the closing `$`, and no digit after the closing `$`. "It costs $5 and $10" and `echo $HOME and $PATH` stay text. A `$$ ... $$` pair on one line is always maths.

4. **Passages show as exact text.** `MathText` serves search results and the citation popover. It keeps only the maths nodes and shows every other character as stored, with its indentation and line breaks. Text in inline code or a fenced block stays literal, so `$x$` in a code sample renders no maths. The chunk viewer stays plain text.

5. **Answers keep their Markdown.** `AnswerText` and the Experiments Markdown view render maths beside their normal Markdown. A failed-claim list keeps inline maths only.

6. **Scope limits.** Maths stays out of the Integrations page, because KaTeX ships in the base build and is not an extra. The `\( \)` and `\[ \]` delimiters are not supported.

7. **A wide display formula scrolls inside its own box**, with `padding-block: 0.25em` so tall glyphs are not clipped. The page never scrolls sideways.

## Consequences

- **Positive:** formulas render at 1280 px and 390 px. On the `eq01` search, 109 formulas rendered with 0 errors.
- **Positive:** no network call and no new runtime service.
- **Negative:** the main script grows by 84.27 kB gzip (382.26 to 466.53 kB, under the 100 kB limit). The main CSS grows from 66.77 to 94.87 kB. The 59 font files add about 1.07 MB, and `static/` grows from 2,296 to 3,768 KB.
- **Negative:** three licences join `web/THIRD_PARTY_NOTICES.md` (KaTeX, with its OFL font notice, `rehype-katex`, `remark-math`).
- **Neutral:** `eq01` test fixture holds formulas only, with no paper prose, until the maintainer decides whether the arXiv text may stay in the repository.

## Alternatives Considered

| Option | Why not |
| --- | --- |
| Load KaTeX from a CDN | The workspace is offline and local-first. |
| Treat chunk text as full Markdown | OCR text would turn into headings, lists and links. |
| Render maths with `trust: true` | A formula in stored text could add links or images. |
| Render `$x$` inside code | Shell and PHP samples such as `$HOME` would turn into formulas. |

## How to Recognise / Handle This Again

- A dollar amount or shell variable renders as a formula: check the dollar rule in `web/src/lib/maths.ts`.
- A formula shows red source text: the LaTeX failed to parse. Check the stored chunk first, then [TDR-043](../tdr/043-a-closing-display-maths-fence-followed-by-text-swallows-the-prose.md).
- A new surface shows raw `$` maths: import the plugin lists from `maths.ts`. Do not write new options.

## Revisit Triggers

- The `\( \)` and `\[ \]` delimiters appear in stored text.
- The bundle size limit changes, or KaTeX fonts need lazy loading.
- The maintainer allows paper prose in the `eq01` fixture.

## References

- `openspec/changes/archive/2026-11-03-render-maths-in-web-workspace/design.md`
- PR #165
