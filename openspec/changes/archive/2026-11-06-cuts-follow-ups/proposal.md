# Proposal: follow-ups from the per-backend local OCR cuts change

## Why

The review of `local-ocr-per-backend-cuts` (PR #183, archived 2026-11-06) left four low-score issues. The operator asked to fix them now (2026-11-06):

- P1. The example cut in the `omrs config init` template and in the start-up refusal for `OCR_LOCAL_MIN_CONFIDENCE` is typed as `0.92`. It drifts if the descriptor default changes.
- P2. "Remove it" for the retired `ocr_local_min_confidence` key sends a save of `ocr_local_cuts`. When `OCR_LOCAL_CUTS` locks that key, the server answers 409 and the page shows a save error.
- P3. Removing a retired key from `omrs.jsonc` keeps the comment written above it, so the comment then sits above the next key.
- P4. `omrs experiments new` leaves the `<person>` and `<agent, if used>` placeholders in the Operator line, and nothing reports them.

## What changes

- The example cut comes from the default backend's descriptor. No source file types the default cut outside the descriptor and its pinned `register()` line.
- When `OCR_LOCAL_CUTS` locks the cuts, the retired-key notice shows no "Remove it" button. It tells the operator to delete the key from `omrs.jsonc` by hand.
- When a save removes a retired key, the comment lines directly above that key go with it. The removal stops at a blank line, at code, or at a commented-out key. Every other removal keeps comments as today.
- `omrs experiments new` takes `--operator TEXT` and writes it into the Operator line. `omrs experiments check` warns when a record's `report.md` or `protocol.md` still holds an Operator placeholder.

## Capabilities

### Modified capabilities

- `settings-file`: a retired key's own comment goes with it.
- `workspace-settings`: the retired-key notice when the cuts are locked.
- `experiment-records`: the operator option and the placeholder warning.

## Impact

- Code: `config/reading_lists.py`, `config/legacy.py`, `config/jsonc_edit.py`, `config/settings_file_write.py`, `transports/cli/experiments.py`, `core/experiment_records/` (creator and checker), `web/src/settings/LocalOcrBackendsRow.tsx` and its words.
- No setting, default, index identity or API contract changes. No re-index.
