# Browser check (tasks 6.4 and 7.4)

Run on 2026-11-07 in Orca against a scratch `omrs web` (scratch config folder, `ocr_skip_blank_pages: false`, empty library, port 8911). The server is stopped.

## Settings, Document reading
- One "Page routing" card holds the fallback and routing unit rows, then five numbered steps in flow order: PDF readers, Pages decided by their content, Pages that look fine, Local OCR backends, OCR engines.
- Step 1 on a checkout install shows the reason and the copy command, with no Install button.
- Step 2 shows the fixed-order line. Skip blank pages shows Off with source "Saved in settings (omrs.jsonc)" and default On.
- Step 3 holds the host router row and the "Define routers in Router section" link.
- Step 4 shows a Confidence cut box for the listed backend. Step 5 shows the workers folder line.
- No horizontal scroll at 1280 px and 390 px (scroll width equals window width), in light and dark.

## Studio, Read document step
- The step holds the Page routing panel with the five steps and the intro "Inherit uses the value from Settings".
- Inherit choices read "Inherit from Settings: On (default)", "Inherit from Settings: off (default)" and "Inherit from Settings: No router". There is no Install button.
- At 1280 px there is no horizontal scroll. At 390 px the page does not scroll sideways, but the Read document rows were NOT checked at that width: the Step settings drawer would not open with the Orca tool. Task 7.4 was closed with this gap accepted by the operator on 2026-11-07.

## Not checked
- Locked-by-environment state and the OCR-off line (covered by Vitest).
- A built-in profile in Studio (covered by Vitest).
- Screenshots were kept out of the repository (public repo).
