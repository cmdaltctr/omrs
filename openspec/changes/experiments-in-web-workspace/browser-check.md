# Browser check (task 6.3)

Date: 2026-10-25. Branch `feat/experiments-in-web-workspace` at `da81fd6e`, with a fresh `npm run build`.

## Set-up

- A scratch `omrs web` server on a loopback port, with a scratch config folder (`OMRS_CONFIG_DIR`), a scratch LanceDB folder and a scratch workspace. The live app and its workspace were not used.
- The page ran in the Orca built-in browser. The viewport was set to 1280 x 900, then to 390 x 844.
- Projects: this repository (50 experiments) and a scratch project, which held only `experiments/EXP_README.md` from the package template.

## Results

| Step | Width | Result |
|---|---|---|
| Add this repository as a project | 1280 | Pass. 201 from `POST /v1/experiment-projects`. The library shows 50 cards and the three reserved numbers |
| Open experiment 22, Protocol tab | 1280 | Pass. The record header and the protocol text show |
| Report tab | 1280 | Pass. `results.md` shows as the report. Only the Report chip has `aria-pressed="true"` |
| Create notebook "Paper 1" | 1280 | Pass. The notebook shows next to the project notebook "OMRS" |
| Add experiment 22 to "Paper 1" | 1280 | Pass. "Added to Paper 1." The notebook page shows the entry card |
| Add the scratch project | 1280 | Pass. "No experiment folder exists in this project yet." |
| Create a Quick experiment (`runtime`) | 1280 | Pass. Folder `2-quick-smoke-2026-10-25` has only `experiment.json` (`Quick`, `runtime`, `PLANNED`) and `report.md`. The index row was added to `EXP_README.md` |
| Library | 390 | Pass. `scrollWidth` 390. One card per row, full width. A long folder path wraps |
| Experiment page, Protocol, Report and Files tabs | 390 | Pass. `scrollWidth` 390 on each tab |
| Notebook page | 390 | Pass. `scrollWidth` 390 |

## Notes

- The section chips (Library, Notebooks and so on) are page state, not routes. `#/experiments/notebooks` without an id opens Home. This follows design D8, which gives routes only to an experiment page and a notebook page.
- The form selects are Radix selects with a hidden native `<select>`. Browser automation must click the trigger and then the option. Setting the hidden `<select>` changes nothing, so the first scratch experiment was created with the default `Standard` and `retrieval`. That is an automation limit, not a product fault. A person using the page clicks the options.
- The screenshots stay outside the repository, because their paths name the local user folder.
