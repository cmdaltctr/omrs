# Browser check (task 5.3)

Date: 2026-11-03. Branch `feat/ordered-reader-and-ocr-lists` at `ef62814d`. Browser: Orca embedded tab.

## Setup

- A scratch `omrs web` server on port 8791. It used a scratch config folder, workspace and LanceDB folder. No live data was read or written.
- The live app on port 8765 stayed up and was not touched.
- The scratch server was stopped and the tab was closed after the check.
- Built web pages: `npm run build` in `web/` at the same commit.

## Results

| Check | 1280 px | 390 px |
| --- | --- | --- |
| Integrations › PDF readers: one row per registered reader, installed state, position in the host list, copy command for a missing reader | Pass (screenshot) | Pass: no horizontal overflow (scroll width 390) |
| Settings › Document reading: `pdf_readers` and `ocr_engines` rows with default, lock and reason lines | Pass (screenshot) | Pass: no horizontal overflow (scroll width 390) |
| Reader list editor: move up, move down, remove, add | Pass | All 6 controls inside the viewport, none smaller than 44 by 36 px, each named by reader |
| Save after a reorder | `omrs.jsonc` held `"pdf_readers": ["liteparse", "pdf_inspector", "pypdf"]` and no old key. The page said "Saved for the next launch" and "Restart to apply". | not repeated |
| Last reader cannot be removed | Move and Remove disabled, "The list needs at least one reader." | not repeated |
| `pdf_inspector` alone | Warning "pdf_inspector alone has no retry: a PDF with no text layer indexes nothing. Add liteparse or pypdf." | not repeated |
| Add reader offers a reader that is not installed | `pypdfium2 (not installed)` is a disabled option | not repeated |
| OCR engines editor | Two engines, "not provisioned" reasons, link to Integrations, Save disabled until a change | not repeated |
| Browser console | No entries | |
| Network | 80 requests, none 4xx or 5xx | |

The restart dialog after a save said the server runs in a terminal and cannot restart itself. That is correct for a server started from a terminal.

## Not checked here

- The Studio Read document step. Vitest covers `ListParam` (10 tests) and the backend covers the step rules.
- Light theme.
- 390 px screenshots. Orca stitched the sticky header more than once into those captures, so they are not kept. The 390 px results above come from measuring the page elements.

## Note for review

The PDF readers rows follow the registry order (liteparse, pdf_inspector, pypdf, pypdfium2), as the `workspace-integrations` spec says. Their labels give the host list position, so a row can read "Second" above a row that reads "First".
