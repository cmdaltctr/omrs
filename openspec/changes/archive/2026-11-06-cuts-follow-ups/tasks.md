# Tasks

Tests first: write the test, run it on current code and record that it fails, implement, then one mutation check per behaviour.

## 1. Example cut from the descriptor (P1)

- [x] 1.1 Write failing tests: the `ocr_local_cuts` field example and the `OCR_LOCAL_MIN_CONFIDENCE` refusal text each equal `{"<default backend>": <descriptor default cut>}`, read from `core/reading_parts`; with the descriptor default patched, both follow.
- [x] 1.2 Build both from the descriptor in `config/reading_lists.py` and `config/legacy.py`. Verify `grep -rn "0\.92" src/omrs web/src` finds only the descriptor and its pinned `register()` line.

## 2. Retired-key notice under a lock (P2)

- [x] 2.1 Write a failing Vitest test in `web/src/settings/DocumentReadingBackends.test.tsx`: cuts locked by `OCR_LOCAL_CUTS` and `retired_keys` holding the old key show the notice without "Remove it", naming `OCR_LOCAL_CUTS` and the hand removal.
- [x] 2.2 Implement in `LocalOcrBackendsRow.tsx` and `documentReadingWords.ts`. Mutation: show the button again; the test fails.

## 3. Retired key takes its comment (P3)

- [x] 3.1 Write failing tests for `remove_value(..., with_comment=True)`: one comment line above goes; two description lines go; a commented-out key line above stays; a blank line stops it; a comment on the same line after another member stays; default call keeps every comment.
- [x] 3.2 Write a failing test through the page write: a save of `ocr_local_cuts` removes `ocr_local_min_confidence` and its comment; a plain clear of another key keeps its comment.
- [x] 3.3 Implement in `config/jsonc_edit.py` and turn it on for retired-key removals only in `config/settings_file_write.py`. Mutation: always on; the plain-clear test fails. Mutation: never on; the retired-key test fails.

## 4. Operator line (P4)

- [x] 4.1 Write failing tests: `omrs experiments new --operator "X"` writes `X` into the Operator line of every template file it creates; without it the placeholder stays; the checker reports `operator-placeholder` as a warning for a placeholder Operator line and nothing for a filled one.
- [x] 4.2 Implement in `transports/cli/experiments.py`, the folder creator and the checker in `core/experiment_records/`. Document the option and the warning in `docs/guides/experiment-records.md`.

## 5. Close

- [x] 5.1 Re-pin the clean-base tripwire by test-ID diff against `v3`.
- [x] 5.2 Run `./scripts/local_ci.sh` and `openspec validate --all --strict`.
- [x] 5.3 Browser check of the locked notice is not needed: the test renders it, and no layout changes. Record this.
- [x] 5.4 Push, open a PR into `v3`, watch CI, handle review. Do not merge without the operator's word.
  - Done 2026-11-06: PR #184, every check green, merged by the operator-set auto-merge as `d382a763`.
