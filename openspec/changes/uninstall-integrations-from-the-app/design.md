## Context

See proposal.md, section Why. Install already exists (ADR-094, specs `integration-install` and `workspace-integrations`):

- `install_environment.py` detects the install type, finds `uv`, reads extra requirements from the installed OMRS metadata, and since `fa60f810` marks base entries (`is_base_extra`).
- `install_job.py` runs one job on `WebRuntime` with a 600 s limit, no `*_API_KEY`, 40 redacted lines, and `uv pip check` after the install. A succeeded job marks the extra `restart-needed`.
- Missing extras already degrade in code: the sparse search has a built-in BM25 fallback, the torch reranker falls back to ONNX, the vector store registry names the `chroma` extra when it is missing, and the PDF reader factory picks an installed reader for `auto`.
- The live app is a `uv tool` install with the receipt `omrs[web,hybrid]`.

## Goals / Non-Goals

**Goals:**

- Uninstall an extra from the page with the same guards as install.
- Never leave the app unable to start or serve its current settings.
- Prove each non-base extra is optional with a test, not only by reading code.

**Non-Goals:**

- No removal of packages that only the removed packages pulled in (orphans). `uv pip uninstall` does not remove them, and finding them safely needs a full resolver. The lasting reinstall command drops them.
- No uninstall for a checkout or a pip install. Those cards keep their copy command.
- No change to the receipt file. Only `uv tool install --reinstall` changes it.

## Decisions

**D1. Packages to remove.** Start from `extra_requirements(extra)` names. Drop each name that a base requirement names, that another installed extra's requirements name, or that any other installed distribution requires (a reverse map built from `importlib.metadata.distributions()`, reading each `Requires-Dist` name without markers, so the check is conservative). The dialog lists both groups: removed and kept. Alternative: remove every requirement of the extra. Rejected, because `llamacpp` and `openrouter` share packages, and a package can be both an extra requirement and a dependency of another library.

**D2. In-use refusal.** A fixed map in code, from extra to the setting values that select it, checked against the frozen `EffectiveSettings` and the saved `omrs.jsonc` values:

| Extra | Refused when |
| --- | --- |
| `chroma` | `vector_store` is `chroma` |
| `torch` | `retrieval.rerank_backend` is `torch` |
| `pdf-pypdfium2` | `pdf_reader` is `pypdfium2` |
| `azure` | `document_backend` is `azure` |
| `community-leiden` | `community_algorithm` is `leiden` |
| `anthropic` | `answer.provider` or `answer.verify_provider` is `anthropic` |
| `hybrid` | never; the built-in BM25 takes over |

A saved value counts, because the next launch reads it. A collection on a Chroma store is caught by `vector_store`. The reason is `in-use` with a `setting` field. Alternative: warn and allow. Rejected, because the app would fail at the next start.

**D3. One job, two actions.** `InstallJob` gains an `action` (`install` or `uninstall`). The status route reports it. The argument list is `uv pip uninstall --python <own Python> <names>`, then `uv pip check`. A failed check marks the job `failed` with `check-failed`, as for install. After success the entry reports `restart-needed` and the card says "Removed, restart to apply".

**D4. Route and catalogue fields.** `POST /v1/integrations/{extra}/uninstall` (manage session, 202 on start, 404 for an unknown extra, 409 with a reason). Each catalogue entry gains `uninstallable`, `uninstall_reason` (`not-uninstallable-here`, `not-installed`, `in-use`, `not-uv-tool`, `uv-not-found`, `install-running`), `uninstall_setting` (the setting for `in-use`, else null), `removes` and `keeps` (package names), and `lasting_uninstall_command` (only when the extra is in the receipt).

**D5. Modularity test.** For each non-base extra, a test hides its top-level modules (a `sys.meta_path` finder that raises `ImportError` for them, plus `capabilities.module_installed` returning false), builds the web app with default settings and a LanceDB store in a tmp folder, and checks: the app starts, `GET /v1/integrations` reports the extra `not-installed`, and a search on a small ingested collection returns results. This runs in the fast suite with the `web` extra, like the other web tests.

**D6. Browser check on a real install.** A scratch `UV_TOOL_DIR` install of `omrs[web,hybrid,chroma,torch,anthropic,pdf-pypdfium2,azure,community-leiden]` from this worktree. Uninstall each extra from the page, restart after each, and check that the app starts and Search answers. The live app on port 8765 is not touched.

**D7. Record it.** A new ADR next to ADR-094: the app may remove an extra it can install, under D1 and D2.

## Risks / Trade-offs

- [A setting outside the D2 map selects an extra] → The modularity test covers start and search. The map lives next to the catalogue, and a test fails when a catalogue extra has no map entry and is not marked "never in use".
- [Orphan packages stay after an uninstall] → The card states it and shows the lasting command, which rebuilds the environment without them.
- [The reverse map keeps a package that could go] → Safe by design; the dialog lists it as kept.
- [A user removes `hybrid`, which the live receipt holds] → The next reinstall adds it back unless the lasting command is used; the card shows that command.

## Migration Plan

Nothing to migrate. To roll back, revert the merge commit. An extra removed by mistake comes back with Install.
