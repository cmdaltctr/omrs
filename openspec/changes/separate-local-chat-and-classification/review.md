# Open-code-review: separate-local-chat-and-classification (task 8.2)

- Date: 2026-10-29
- Session: `622ab7bc-ab64-4f03-a7e3-8929087c1a04`
- Command: `ocr review --audience agent --concurrency 2 --from v3 --to HEAD`, with tests, docs, OpenSpec files, Markdown, `openapi.yaml` and `.env.example` excluded.
- Scope: 44 source files under `src/omrs/` and `web/src/`. No timeout and no 429.
- Result: 6 findings. Each finding has a score (likelihood x impact). A score of 5 or more is fixed in this change. A lower score is a proposed issue.

| # | File | Finding | Score | Outcome |
| --- | --- | --- | --- | --- |
| 1 | `src/omrs/transports/api/routes/llamacpp_server.py` | A switch to `external` reads the server state without the manager lock, so a Start sent at the same moment can slip past the `server-running` check. | 1 x 3 = 3 | Proposed issue |
| 2 | `web/src/api/settingsMutations.ts` | A Classification address save does not refresh the llama.cpp server status, so the shared-address warning stays stale. | 6 x 2 = 12 | Fixed test first: `useRefreshProviders` invalidates `llamacppServerKey`. The new test failed before the fix. |
| 3 | `web/src/api/settings.ts` | `ChatSettings.reason` is typed `string \| null`, not a union of the fixed reasons. | 1 x 2 = 2 | Proposed issue |
| 4 | `src/omrs/transports/api/routes/llamacpp_server.py` | `_CHOICES` repeats `ACCEPTED["llamacpp_chat_server"]` from `config/rules.py`. | 1 x 3 = 3 | Proposed issue |
| 5 | `web/src/settings/ChatServerChoice.tsx` | A failed session read shows "A credentials session is needed to change this." | 2 x 2 = 4 | Proposed issue |
| 6 | `web/src/settings/ChatServerChoice.tsx` | A nested ternary builds the read-only reason. | 1 x 1 = 1 | Proposed issue |

## Proposed issues

1. **Serialise the `server-running` check with Start** (L1 x I3). Trigger: Start and a switch to `external` sent within milliseconds of each other. The choice is saved as `external` while the owned server starts. The user can stop it from the panel.
2. **Type `ChatSettings.reason` as a union** (L1 x I2). Trigger: a typo in a reason comparison in the front end.
3. **Read the Chat server choices from `ACCEPTED`** (L1 x I3). Trigger: someone adds a third choice in only one place.
4. **Separate a failed session read from a missing scope in `ChatServerChoice`** (L2 x I2). Trigger: `GET /v1/session` fails.
5. **Replace the nested ternary in `ChatServerChoice`** (L1 x I1). Style only.
