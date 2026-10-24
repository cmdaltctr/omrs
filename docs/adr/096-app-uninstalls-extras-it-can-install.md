# ADR-096: The App Uninstalls the Extras It Can Install

- **Date:** 2026-10-24
- **Status:** Proposed
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-094](094-app-installs-allowed-extras-into-itself.md) (the app installs allowed extras), [ADR-087](087-settings-live-in-omrg-jsonc.md) (settings in `omrs.jsonc`)
- **Change:** `openspec/changes/uninstall-integrations-from-the-app/` (design D1 to D7)

## Context

ADR-094 lets the Integrations page install an allowed extra into the server's
own `uv tool` environment. The page had no way back. A user who tried Chroma,
Azure or PyTorch had to leave the app and rebuild the environment by hand.

OMRS is meant to be modular. Each non-base extra adds one capability, and the
app must start and search without it. The code already has fallbacks: a
built-in BM25 when `rank_bm25` is missing, the ONNX reranker when PyTorch is
missing, and a PDF reader factory that picks an installed reader for `auto`.
No test proved that promise for each extra.

Removing packages is riskier than adding them:

- An extra can list a package that another package, another extra or the
  base install also needs. Removing it breaks something unrelated.
- A setting can select the extra, for example `vector_store` set to `chroma`.
  The next start would then fail.
- The `uv tool` receipt still lists the extras it was built with, for example
  `omrs[web,hybrid]`. A later reinstall from the receipt adds a removed extra
  back.
- `uv pip uninstall` removes only the named packages. Packages that only the
  removed ones pulled in stay behind.

## Decision

The app may uninstall an extra that it can install, under the guards of
ADR-094 and two more rules.

1. **Same job, same guards.** `POST /v1/integrations/{extra}/uninstall` uses
   the install job with `action` set to `uninstall`. One job runs at a time.
   It needs the browser session with the `manage` scope. It stops after
   600 s, gets no `*_API_KEY` variable and keeps 40 redacted output lines.
   The command is the argument list
   `uv pip uninstall --python <server Python> <names>`, then `uv pip check`.
   A clash fails the job with `check-failed`. Success marks the entry
   `restart-needed`, and its `pending_restart` field says `install` or
   `uninstall` until the server restarts. The page reads that field, so a
   later job in the same launch cannot change what an earlier card shows.
2. **Only the extra's own packages (D1).** The names come from the extra's
   requirements in the installed OMRS metadata, never from request text. The
   server keeps every name that a base requirement, another installed extra
   or any other installed distribution requires. A requirement behind
   another package's extra (`extra == "x"`) counts only when an installed
   package or the receipt asks for that extra, as `pip check` does. Other
   markers count as true, so the check can only keep too much. A package
   that only another package of the same uninstall requires goes too, as in
   pip-autoremove. The entry lists both groups as `removes` and `keeps`.
   When every package is kept, the server refuses with `nothing-to-remove`.
3. **Never an extra in use (D2).** A fixed map, next to the catalogue, names
   the backend setting that selects each extra: `vector_store` (`chroma`),
   `retrieval.rerank_backend` (`torch`), `pdf_reader` (`pypdfium2`),
   `document_backend` (`azure`) and `community_algorithm` (`leiden`).
   Provider settings come from the provider registries instead: each
   provider declares its extra, and the check resolves the answer,
   verification, metadata and embedding roles as the Providers page does,
   with `local` and `cloud` resolved. So Anthropic, or a later provider with
   an extra, blocks its extra, and `ollama` and `openai_compatible` never
   block. `hybrid` is never in use, because the built-in BM25 takes over.
   The server checks the effective settings and the saved `omrs.jsonc`,
   because the next start reads the saved value. A match gets 409 `in-use`
   with the setting.
4. **No base entry and no `web`.** A base entry comes with every install, and
   `web` runs the page. Both get `not-uninstallable-here`. Magika has no
   extra, so the route finds it by its id and refuses it the same way.
5. **Leftovers stay; the card shows the lasting command.** The app does not
   remove orphan packages. When the receipt lists the extra, the entry gives
   `lasting_uninstall_command`, the `uv tool install --reinstall` command
   without that extra. It drops the extra for good and removes the orphans.
   The page hides it while a setting uses the extra.
6. **A test proves each extra is optional (D5).** For each non-base extra, a
   fast test hides its modules, starts the web app, checks that the extra
   reports `not-installed`, and searches a small LanceDB collection.

ADR-094's decision text does not change. This ADR adds the reverse action.

## Consequences

### Positive

- A user can try an extra and remove it again without a terminal.
- The modularity promise is tested for every non-base extra, not only read
  from the code.
- A removal cannot break the next start through a setting that selects the
  extra, or break another package through a shared requirement.

### Negative

- Orphan packages stay until the user runs the lasting command.
- The backend rows of the in-use map are kept by hand. A new extra needs a
  map entry; a test fails until it has one. Provider rows follow the
  registries.
- Saved user profiles and pipelines are not checked yet. A profile that
  names a removed provider or PDF reader fails when it runs; the app still
  starts.
- The reverse map is conservative, so a package that could go can stay. The
  dialog lists it as kept.
- `torch` itself stays after a PyTorch uninstall, because it is a dependency
  of `sentence-transformers`, not a requirement of the extra. The lasting
  command removes it.

### Neutral

- The receipt file does not change. Only `uv tool install --reinstall`
  changes it.
- A checkout or a pip install still cannot uninstall from the app.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Remove every requirement of the extra** | `llamacpp` and `openrouter` share packages, and a package can be both an extra requirement and a dependency of another library. |
| **Warn about an extra in use, then allow it** | The app would fail at the next start. |
| **Remove orphan packages too** | Finding them safely needs a full resolver. The lasting reinstall command already drops them. |
| **Rewrite the receipt after an uninstall** | The receipt belongs to `uv tool`. Editing it by hand can break the next reinstall. |
| **Do nothing (copy command only)** | The user has no way back from an install made in the app. |

## References

- `src/omrs/transports/api/install_environment.py`, `install_job.py`, `integrations_catalogue.py`, `routes/integrations.py`
- `src/omrs/transports/api/openapi.yaml` (`uninstallIntegration`)
- `web/src/integrations/`
- `tests/unit/test_extras_modularity.py`
- [ADR-094](094-app-installs-allowed-extras-into-itself.md)
