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

**D1 revised (2026-10-24).** Review against `pip check` and pip-autoremove found D1 too strict in one place and too loose in another:

- A requirement written `pkg; extra == "x"` applies only when something asks for `name[x]`. `pip check` evaluates markers with no extra, and pip-autoremove reads only a package's plain requirements. D1 counted every such line, so lancedb's own extras kept both `torch` packages, and the app could never remove PyTorch. Now an edge with an `extra` clause is active only when an installed package's active requirement, or the receipt for `omrs`, asks for that extra (found by repeating until nothing changes). Other markers (Python version, platform) still count as true, which can only keep too much.
- A package that only another package of the same uninstall requires stays under D1, for example `igraph` behind `leidenalg`. pip-autoremove removes such a group. The removal set is now found by repeating until nothing changes, limited to the extra's own installed requirements, so orphans outside the extra still stay.
- When D1 keeps every package, the server refuses with `nothing-to-remove`. This now needs a real requester, for example a package that asks for `lancedb[embeddings]`.

**D2 revised (2026-10-24).** Provider settings are not a hand-kept row. Each LLM and embedding provider already declares its extra in its registry (`_PROVIDER_EXTRAS`, `ConnectionDescriptor.extra`). The check resolves each role the way the Providers page does (`compose_connections._role_providers`): answers (`answer.provider`), verification (`answer.verify_provider`, with `cloud` and `local` resolved), metadata (`metadata.extraction_mode` or `metadata_llm_provider`) and embeddings (`embed_provider`). It ignores the role switches (`answer.enabled`, `verify_claims`), because a saved choice can be turned on later. It runs on the effective settings and again with the saved `omrs.jsonc` values laid over them, so a saved-only value counts. The reported setting is the key that names the provider: `local_backend` or `cloud_backend` when the role resolves through an alias. A provider without an extra (`ollama`, `openai_compatible`) never blocks. The backend rows (`vector_store`, `retrieval.rerank_backend`, `pdf_reader`, `document_backend`, `community_algorithm`) stay as a fixed map. Saved user profiles and pipelines can also name an Anthropic answer step or a PDF reader; a missing extra fails only when that profile runs, and the app still starts. Scanning them needs the workspace store and is a separate change.

**D3. One job, two actions.** `InstallJob` gains an `action` (`install` or `uninstall`). The status route reports it. The argument list is `uv pip uninstall --python <own Python> <names>`, then `uv pip check`. A failed check marks the job `failed` with `check-failed`, as for install. After success the entry reports `restart-needed` and the card says "Removed, restart to apply".

**D4. Route and catalogue fields.** `POST /v1/integrations/{extra}/uninstall` (manage session, 202 on start, 404 for an unknown extra, 409 with a reason). Magika has no extra, so the route also finds an entry by its id, and Magika gets 409 `not-uninstallable-here`. `nothing-to-remove` (added during apply, 2026-10-24): D1 can keep every package of an extra. The `torch` packages are an example, because `lancedb` names both under its own extras and D1 reads `Requires-Dist` without markers. The server refuses rather than run an empty `uv pip uninstall`, and the card shows the kept packages. Each catalogue entry gains `uninstallable`, `uninstall_reason` (`not-uninstallable-here`, `not-installed`, `nothing-to-remove`, `in-use`, `not-uv-tool`, `uv-not-found`, `install-running`, in that order), `uninstall_setting` (the setting for `in-use`, else null), `removes` and `keeps` (package names), and `lasting_uninstall_command` (only when the extra is in the receipt).

**D4 revised (2026-10-24).** The job keeps a map from extra to the action that succeeded in this launch (`install` or `uninstall`), and each entry reports it as `pending_restart` (null otherwise). The page takes its badge and restart line from that field. Before, it read the last job, so an uninstall of A followed by an install of B showed A as "Installed, restart to use". The server is now the single source of this state, as TanStack Query advises for server state. The page hides the lasting command while the reason is `in-use`, because that command would remove an extra the next start needs.

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
