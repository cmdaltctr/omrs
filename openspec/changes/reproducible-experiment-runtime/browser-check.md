# Browser check (task 8.3)

Date: 2026-10-27. Branch `feat/reproducible-experiment-runtime`.

## Set-up

- Scratch server: `omrs web --workspace <scratch>/ws --port 8791 --experiment-root <scratch>/proj`, with `OMRS_CONFIG_DIR=<scratch>/config` and `LANCEDB_URI=<scratch>/lancedb`.
- The live app on port 8765 and `~/.omrs` were not used.
- Browser: the Orca built-in browser. Google Chrome is not installed on this Mac.
- Project: an empty scratch project `Scratch`, added with the Add project form.

## Results

| Check | Result |
| --- | --- |
| Purpose field order | PASS. The options are `Optimisation`, then `Publication`. `Optimisation` is selected first. |
| Create an `Optimisation` experiment | PASS. `1-opt-check-2026-10-27/experiment.json` holds `"purpose": "optimisation"` and `"size": "Standard"`. |
| Choose `Publication` | PASS. The size changes to `Confirmatory`. The form shows "A publication plan needs a pinned llama.cpp runtime." |
| Create a `Publication` experiment | PASS. `3-pub-real-2026-10-27/experiment.json` holds `"purpose": "publication"` and `"size": "Confirmatory"`. |
| Purpose label in the list | PASS. Each card shows `Optimisation` or `Publication`. |
| Purpose label on the experiment page | PASS. The page of experiment 3 shows `Confirmatory` and `Publication`. |
| Checker on the new publication experiment | PASS. Checks (1) shows `publication-runtime-invalid`, because the template build `0` is refused until the plan is pinned. |
| No sideways scroll | PASS. At 1280 px and at 390 px, `scrollWidth` equals the window width on the list and on the page. |

## Notes

- Experiment 2 (`2-pub-check`) is `Optimisation`. The Orca `select` command did not send a change event to the form, so the choice did not apply. A native change event was then used for experiment 3. This is a limit of the browser driver, not of the form. The form tests cover the select.
- The Orca `click` command did not submit the form. Enter on the focused Create button did. The form tests cover the click.
- The check found that each `publication-*` message repeated the folder name, which the CLI already prints. The messages now leave it out (commit after this check).
- The server was stopped after the check. Port 8791 is free.
