# Browser check (task 8.3)

- **Date:** 2026-10-26
- **Server:** scratch `omrs web` on port 8791, `OMRS_CONFIG_DIR` and `--workspace` in a scratch folder. The live app on port 8765 and `~/.omrs` were not touched. The server was stopped by its PID afterwards.
- **Branch:** `feat/edit-experiment-files-in-library`
- **Scratch project:** copies of `30-reader-fallback-chain-2026-09-13` (PASS, converted, `report.md`), `21-lancedb-literal-faithfulness-2026-09-02` and `1-reranker-threshold-calibration-2026-05-12` (PASS, converted, `results.md`), and `EXP_README.md`.

## Results

| Check | View | Result |
| --- | --- | --- |
| Edit on the Protocol tab opens the text area (20 rows, focused) with Save and Cancel | 1280 px light | PASS |
| Warning names `PASS`, says git keeps the old text and the app records the save | 1280 px light, 390 px light and dark | PASS |
| Plan tab with unsaved text opens "Discard your changes to protocol.md?"; Keep editing keeps the text and the tab | 1280 px light | PASS |
| Save shows "Saved." and "Last edited 26 Oct 2026, 19:26"; focus returns to Edit | 1280 px light | PASS |
| File changed in a terminal while the editor was open: the save shows the 409 notice and Reload, the text stays | 1280 px light | PASS |
| Reload loads the terminal change; Cancel without changes closes with no dialog; focus returns to Edit | 1280 px light | PASS |
| Plan tab shows no Edit button | 1280 px light | PASS |
| Report tab shows "Report (results.md)"; Save changes `results.md`, shows "Saved." and "Last edited" | 390 px dark | PASS |
| Edit button sits in the panel header | 1280 px dark | PASS |
| No sideways scroll; Save and Cancel fit | 390 px light and dark | PASS (`scrollWidth - innerWidth` = 0) |
| `edits.jsonl` has one line per save (1 in folder 30, 1 in folder 1); the 409 attempt added none; `after_sha256` matches the file; no `.omrs-edit-*.tmp` file left | disk | PASS |

## Finding fixed during the check

Experiment 21's `results.md` holds one NUL byte on purpose (it documents a NUL test value). The read marked it editable, but every save was refused with "The text must not hold a NUL character." The fix: a file that holds a NUL is not editable, so no Edit button appears (design D1, spec requirement "The protocol and the report can be edited", `is_editable`, with a unit test that failed first). After a server restart, the Report tab of folder 21 shows no Edit button, and its Protocol tab still does.

## Not checked in the browser

- The browser's own `beforeunload` prompt (covered by `FileEditor.test.tsx`).
- The `edit_log_unusable` refusal (covered by unit and route tests).
