# Design: follow-ups from the per-backend local OCR cuts change

## Decisions

### D1. Example cut from the descriptor (P1)

The `ocr_local_cuts` field example and the start-up refusal text build `{"<default backend>": <its default cut>}` from `core/reading_parts`. The descriptor stays the one source of the default cut. A test pins that each example equals the descriptor value.

### D2. No "Remove it" under an environment lock (P2)

The page already knows the lock (`ocr_local_cuts.locked`). It hides the button and shows a plain instruction. The server is not changed: a write of a locked key must stay refused. Rejected: letting the server remove the retired key without writing `ocr_local_cuts`. That adds a new write route for one rare case.

### D3. Retired keys take their own comment, nothing else (P3)

`remove_value` gains a keyword `with_comment` (default off). With it on, it also removes the comment lines directly above the member, up to a blank line, a code line or a commented-out key line (`// "name": ...`). Only the retired-key removals in `settings_file_write` turn it on.

Why so narrow: in the `omrs config init` template, a nested block has no blank lines between entries. Each description sits directly under the previous commented-out key. A rule that removed every comment above a cleared key would delete a neighbour's template lines. A plain clear keeps today's behaviour, so the requirement "a page save keeps the rest of the file" still holds for every normal save.

### D4. Operator option and a warning (P4)

`omrs experiments new --operator TEXT` fills the Operator line. The text is the operator's own choice; OMRS never reads a name from git or the system, so no personal identifier enters a file unasked. The checker adds the warning `operator-placeholder` (a warning, not an error), so old records and records made in the web view are reported without failing a run. Rejected: a fixed default text, because earlier records name a real person by the operator's choice.

## Decisions made while applying (2026-11-06)

- D5. `--operator` refuses blank text and text with a line break (`ScaffoldError`). A blank value would erase the Operator line without a sign; a line break would break the header. Reverse: delete the one check in `create_experiment` and its test.
- D6. Only `//` comment lines go with a retired key. `/* */` blocks stay; the scanner does not split them by line. No template writes block comments.
- D7. The web "create experiment" route stays unchanged. It passes no operator, so the checker flags its records with `operator-placeholder`.
