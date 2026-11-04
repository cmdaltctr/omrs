# Browser check: Reading parts and the local OCR backend list (tasks 6.3 and 6.4)

Date: 2026-11-04. Operator approval: 2026-11-04 (browser check through Orca).

## Set-up

- Branch `feat/local-ocr-backends` at `6fd9d44d`, web bundle built with `npm run build`.
- Scratch `omrs web` on port 8791, with an empty scratch config folder, workspace, LanceDB and state folder. No API key. The live app on port 8765 was not touched.
- One Orca browser tab bound to the worktree, signed in with a one-time link.
- The server and the tab were stopped and closed after the check.

## Results

| Check | Width | Result |
| --- | --- | --- |
| Integrations > Reading parts: PP-OCRv6 small is Ready, cut 0.9, model files present | 1280 px | Pass |
| Page rules: Blank pages On, Maths pages On, Non-Latin scripts Off, each Version 1 | 1280 px | Pass |
| Discovered parts: "No installed package adds a reading part." | 1280 px | Pass |
| Integrations page width equals the viewport (no horizontal scroll) | 390 px | Pass (`scrollWidth` 390) |
| Settings > Document reading > Local OCR backends: add `indra`, move it up, save | 1280 px | Pass: the file holds `"ocr_local_backends": ["indra", "pp-ocrv6-small"]` |
| After save: restart notice, then "Saved for the next launch: indra, pp-ocrv6-small" and "Restart to apply" | 1280 px | Pass |
| Settings page width equals the viewport | 390 px | Pass (`scrollWidth` 390) |
| Browser console errors and warnings | both | None |

## Notes

- In the Orca tab, a click on Save did not submit the form; `form.requestSubmit()` on the same button did. The same Orca quirk was seen on the Chat Send button on 2026-10-20. Vitest covers the Save handler.
- The only call to Ollama was the keyless health probe `GET /api/version` from the Integrations page. No model ran.

## Screenshots

- `browser-reading-parts-1280.png`, `browser-reading-parts-390.png`
- `browser-settings-local-backends-edit-1280.png`, `browser-settings-local-backends-saved-1280.png`, `browser-settings-local-backends-390.png`
