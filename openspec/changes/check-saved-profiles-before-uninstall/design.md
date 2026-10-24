## Context

ADR-096 added uninstall from the app. Its in-use check (`uninstall_plan.in_use_setting`) reads the effective settings and the saved `omrs.jsonc`: a fixed map of backend settings (`IN_USE`) and provider roles resolved through the provider registries. Saved user profiles live in the workspace (`workspace.db`, ADR-080). The web server owns it and exposes read access as `WebRuntime.profiles.catalogue` (`compose_profiles.ProfileService.catalogue`, a `ProfileCatalogue`). It can be `None` when the profile service did not start.

Research on the current code found only two ways a user profile can select an optional extra:

- A `read.document` node in the ingest graph with `params.pdf_reader` (`core/ingestion/graph_adapters_catalogue.py`). A graph-wide `overrides.pdf_reader` is refused as host-owned (`core/pipelines/levers.py`).
- The profile row's `embed_provider` (ADR-081).

No node parameter names an LLM provider, a vector store, a reranker backend, a community algorithm or a document backend; those are host-owned or not levers at all. Built-in profiles (`documents`, `codebase`) name none of these and run on host settings (gotcha 17).

## Goals / Non-Goals

**Goals:**

- Refuse an uninstall while a user profile that is not deleted selects the extra.
- Name the profile, so the user can change it in Studio.

**Non-Goals:**

- No check of deleted profiles: they cannot run.
- No check of old pipeline revisions: only the current revision of each slot runs.
- No change to Studio or to how profiles save a PDF reader.

## Decisions

**D1. What counts.** For each profile from `catalogue.list_profiles()` (deleted ones are already left out), read `catalogue.slot_document(id, "ingest")`. Each node with `operation == "read.document"`, `enabled` not false, and a string `params.pdf_reader` is checked against the `IN_USE` rows whose key is `pdf_reader`. Then `embed_provider` is checked against `embeddings.registry.extra_for`. Bound or unbound makes no difference: Studio can run any profile's pipeline. Alternative: only profiles bound to a collection. Rejected, because a Studio run of an unbound profile would fail too.

**D2. Order.** Global settings first (as today), then profiles in creation order. The first match is reported. One match is enough to refuse.

**D3. Contract.** Keep the reason `in-use`. Add `uninstall_profile` to each entry: `{id, title}` or null. Add `profile` (`{id, title}`) to the 409 body when a profile is the cause. `uninstall_setting` names the key inside the profile (`pdf_reader` or `embed_provider`). Alternative: a new reason `in-use-by-profile`. Rejected: the page and the server already treat `in-use` as one refusal, and the extra field carries the difference.

**D4. No catalogue.** When `runtime.profiles` is `None`, or the catalogue raises, the profile part is skipped and a warning is logged. The global check still runs. Refusing every uninstall when the workspace cannot be read would block users without a workspace problem being their fault; the server logs the gap instead.

**D5. Injection.** `InstallJob` gains a `profiles` callable (returns the catalogue or `None`), like `installed` and `saved`, so tests replace it. The route wires it to `runtime.profiles`.

**D6. Page.** The in-use line names the profile title and links to `#/studio/<id>`: "The profile <title> uses this extra (`pdf_reader`). Change it in Studio before you uninstall it." No Uninstall button and no lasting command, as for a setting.

## Risks / Trade-offs

- [A future node parameter names another extra] → The folder guide for `transports/api` and the provider guide say to extend the walk; a test lists the node operations the walk reads.
- [Large workspaces] → One read per profile per catalogue request. Workspaces hold tens of profiles; the catalogue route already runs off the event loop.

## Migration Plan

Nothing to migrate. Revert the merge commit to roll back.
