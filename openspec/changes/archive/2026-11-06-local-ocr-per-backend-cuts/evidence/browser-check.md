# Browser check (tasks 6.4 and 7.7), 2026-11-06

## Set-up

- Browser: Orca embedded browser. Chrome DevTools could not start, because Google Chrome is not installed on this machine.
- Server: `omrs web` from this branch on port 8794 (checked free with `lsof`). Scratch config folder, state folder, home folder, workspace and LanceDB folder. No API key. Empty library. The live app was not touched.
- Test `omrs.jsonc`: `ocr_local_backends` set to `["pp-ocrv6-small", "indra"]`, plus the retired key `ocr_local_min_confidence: 0.9` with a comment above it.
- Indra is not installed in the scratch environment. The rows show "Not installed". The cut inputs still show and work.

## Settings › Document reading › Local OCR

| Check | Result |
| --- | --- |
| Retired-key notice shows, with "Remove it" | Pass |
| One "Confidence cut" input per listed backend, label "Confidence cut for &lt;name&gt;" | Pass |
| Empty input shows the default from the descriptor ("Default 0.92", "Default 0.94") | Pass, after a fix (below) |
| Inputs read-only until Edit | Pass |
| 1.5 shows "The cut must be a number from 0 to 1." and Save is disabled | Pass (`settings-1280-light-invalid.png`) |
| 0.95 on Indra, Save: one `PUT` with the list and `ocr_local_cuts: {"indra": 0.95}` | Pass |
| The file holds `"ocr_local_cuts": {"indra": 0.95}` and no `ocr_local_min_confidence`; the notice goes; "Restart to apply" shows | Pass |
| No horizontal scroll at 390 px (`scrollWidth` 390 = viewport 390) | Pass |
| Light and dark at 1280 px and 390 px | Pass (`settings-*.png`) |

Fix found by this check: the cut input was `w-28` (112 px) and clipped the placeholder ("Default 0.9"). It is now `w-36`. The placeholder text measures 79 px in a 142 px box.

Note: removing the retired key keeps the comment that sat above it. The shared JSONC writer keeps every comment the user wrote. The comment then sits above the next key.

## Integrations › Reading parts

| Check | Result |
| --- | --- |
| Before restart: cuts 0.92 and 0.94 (the saved 0.95 waits for a restart) | Pass |
| After a restart of the scratch server: cuts 0.92 and 0.95 | Pass (`integrations-1280-light-after-restart.png`) |
| 1280 px light and 390 px dark, no horizontal scroll | Pass (`integrations-*.png`) |

## Studio › Read document step (a duplicate of the Documents profile)

| Check | Result |
| --- | --- |
| One cut input per backend of the inherited host list | Pass |
| Empty input shows the default before restart ("Default 0.92", "Default 0.94") | Pass |
| After restart, the Indra input shows the host cut ("Host 0.95") | Pass |
| Help text: "An empty box inherits the host cut. A step entry replaces the host cut for its own backend in this pipeline only." | Pass |
| 1.4 shows "The cut must be a number from 0 to 1." | Pass (`studio-1280-light-invalid.png`) |
| 0.88 clears the message; "Value in use" shows the step map | Pass (`studio-1280-light.png`) |
| 390 px dark, no horizontal scroll | Pass (`studio-390-dark.png`) |

## Close

The scratch server was stopped and the tab closed.
