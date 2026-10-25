# Review page pattern (operator labels and verdicts)

Use this when an experiment needs the operator to judge pages by eye: maths labels, noise verdicts, sample review. The page is a local HTML file in `output/` (gitignored). It shows the page image beside the engine output, records one answer per item, and downloads the answers as JSON. A script merges that JSON into a committed file.

Worked examples: Experiment 37 `label_page.py` (labels) and `make_noise_review.py` (verdicts); Experiment 34 `make_review.py` (renderer).

## Layout (use this for every review and labelling page)

Follow the Experiment 34 review page (`experiments/34-worker-sample-review-2026-09-19/make_review.py`, output `review.html`). Import its `HTML_HEAD` style block and the zoom viewer (`<div id="lb">` and the "Zoomable viewer" script in `HTML_TAIL`) rather than copying them; Experiment 37 `make_noise_review.py` `_exp34_parts()` shows how.

- **Sticky top bar**: title, a prominent progress pill ("Done n / N verdicts · n / N pages", bold, turns green when complete), **Next unreviewed**, **Collapse all**, **Download**.
- **One intro paragraph** under the bar: what to judge, what each answer means, what the views show.
- **One collapsible card per page** (`details.page`): the summary shows the page key, chips for what needs an answer, and a status on the right (`✓ reviewed`, `n / m`). Only one page open at a time; opening one closes the others and keeps its header in view.
- **Side by side inside a card** (`.body` grid, 5fr : 7fr): page image **pinned left** (sticky), click opens the **zoom viewer** (pinch, Cmd/Ctrl-scroll, drag, double-click, Esc); **outputs right**.
- **One collapsible panel per engine or source** (`details.engine`) with badges (why it is listed, any screen numbers) and its own status. Panels that need an answer open with the page; the others stay closed.
- **Answers as chips** (radio styled as pills), plus an optional note and a **Clear** link, inside the panel they belong to.
- **Rendered / Raw toggle** above each output.
- Stacks to one column below 900 px.

A labelling page with no engine output (for example maths labels from page images only) uses the same card, with the answer chips on the right in place of engine panels.

## Rendering engine output

Engine output is Markdown with LaTeX maths and sometimes HTML. Never show it only as raw text in a `<pre>`: the operator cannot judge formulas or tables that way.

1. **Render Markdown.** Headings, paragraphs, pipe tables and HTML tables. Reuse the project's existing review renderer when one exists (for OMRS: `_mini_markdown` in `experiments/34-worker-sample-review-2026-09-19/make_review.py`), imported, not copied.
2. **Render maths with KaTeX auto-render.** Delimiters `$$…$$` (display) and `$…$` (inline), `throwOnError: false` so one bad formula does not blank the panel. Pin the KaTeX version the experiment uses for its checks.
3. **Load KaTeX locally.** Install with Bun in a gitignored folder of the experiment (`katex/`, `bun add katex@<version>`) and link `../katex/node_modules/katex/dist/…` from `output/`. No CDN: the page must work offline.
4. **Protect inline maths from the Markdown pass.** A renderer that turns `*text*` into italics runs before KaTeX and eats the `*` in formulas such as `$p_{\theta^*}$`. Swap each `$…$` span for a placeholder before rendering, then put it back HTML-escaped. Display blocks must stay in one element so auto-render sees both delimiters.
5. **Strip layout HTML, keep every word.** Engines emit `<div style=…>`, `<img …>`, `<span>`, `<center>`. Remove the tags (keep table tags for the renderer) and show images as `[image]`. Do NOT use an ingestion normaliser that deletes text inside image or figure blocks: in a noise review that can hide the very text the operator must judge.
6. **Keep a raw view.** A toggle per panel: *Rendered* and *Raw* (exact engine text, any screen highlights). The rendered view is for reading; the raw view is the evidence.
7. **Page image:** see Layout above (pinned left, zoom viewer). Render images with the tool the project already has (for OMRS: `pypdfium2` from an engine environment); never install a renderer just for this.

## Recording answers

- **Blind where it matters.** A labelling page shows no detector flag, score or engine output. Tell the operator not to open the results file first.
- **Autosave** to `localStorage` (wrap in try/catch, show "autosave unavailable: download often" on failure) and restore on load.
- **One download button** writing `<name>_download.json`: a list of `{key, label|verdict, note}`.
- **Merge refuses incomplete work**: any item without an answer stops the merge and writes nothing.
- **Merge is additive.** It keeps answers already merged and adds the new ones; a changed answer is printed. This lets a second page cover only the remaining items.
- **A follow-up page for remaining items** uses its own `localStorage` key and download name, so it can never overwrite earlier answers.
- After the merge, record the file's SHA-256 in the `frozen` list of `plan.json`. Do this before the first run; after it, `plan.json` takes amendments only.

## Rebuilding a page the operator already opened

- An open browser tab does not refresh itself. When the page is rebuilt (more items, fixed rendering), tell the operator to reload (Cmd+Shift+R). Check the download's item count against the expected count before merging.
- Keep the `localStorage` key the same when the item list does not change, so answers survive the rebuild.

## Verify before handing over

Open the page in a headless browser (chrome-devtools MCP, isolated context) and check, by script:

- KaTeX loaded; count of rendered formulas; `.katex-error` count is 0;
- each rendered formula's TeX annotation equals the formula in the raw text, in order (catches the `*` bug);
- no `<div`, `<img`, `<span` text visible in the rendered view;
- no word of the raw text (outside formulas and tags) missing from the rendered view;
- every image link resolves to a file; the inline script passes `node --check`;
- with a card open, the image and the outputs sit side by side (image right edge left of the outputs, same top); the zoom viewer opens; one answer click updates the progress text, and Clear resets it.

Take one screenshot of an open card and look at it before giving the link.

Fix and rebuild until all checks pass. Then give the operator the `file://` link.
