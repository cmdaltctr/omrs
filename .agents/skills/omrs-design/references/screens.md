# Screen guidance

This file turns the `redesign-web-workspace` spec deltas into layout and styling decisions. The deltas stay the contract. Read the delta for the view you touch, then apply the design rules here. If they disagree, the delta wins. Report the disagreement.

## Card groups

These rules apply to every group of cards in any view.

- Cards of the same size: use a plain grid, `grid grid-cols-1 items-start gap-3 md:grid-cols-2 xl:grid-cols-3`.
- Cards of different heights in one group, each short enough for one column: use the masonry layout.
- For masonry, use the shared `MasonryColumns` component in `web/src/components/MasonryColumns.tsx` (tests in `web/src/components/MasonryColumns.test.tsx`). It fits as many columns of at least 300px as the area allows, up to three. It puts each card in the shortest column, so a short card does not sit under a tall one. It places the cards again when the area or a card changes size. It does not move a card while focus is inside the cards, so a card that grows during an edit stays in its column. The cards move when focus leaves.
- Masonry stays only on Knowledge Base > Add. Do not copy it to a new view.
- A card too tall for one column goes full width and splits into two columns with container queries. Do not put it in masonry. Make the card the container (`@container`) and split its body with `grid grid-cols-1 gap-x-6 gap-y-3 @3xl:grid-cols-2`. That splits from 768 px of card width, not from the window width. Examples: `web/src/settings/ProviderCard.tsx`, `McpSection.tsx`, `McpHttpPanel.tsx`, `DocumentReadingSection.tsx`.
- Do not make a tall card span two masonry columns. Do not rely on the window width to split a card.
- Put an extra panel under the card's fields. Separate it with `border-t border-border pt-3`.
- Heavy panels that people seldom use sit behind `PanelDisclosure` (`web/src/settings/PanelDisclosure.tsx`). The panel starts closed with a one-line state on the toggle row. It opens by itself when it needs attention, such as a missing program path or a failed server. Used for Local server (`LlamacppServerPanel.tsx`) and Get a model (`ModelDownloadPanel.tsx`).
- Settings > Providers: local providers sit full width in an "On this machine" band. From 768 px of card width each local card splits into two columns: addresses and models left, Chat and Get a model right. Cloud providers follow in a grid of equal-height cards (`grid grid-cols-1 gap-3 @xl:grid-cols-2 @4xl:grid-cols-3`, container queries). The card's notice and Test sit at its foot. Files: `ProvidersSection.tsx`, `ProviderCard.tsx`.
- Settings > MCP shows two full-width cards, Stdio client then MCP over HTTP. Each splits into two columns from 768 px of card width: settings left, client configuration right. The HTTP card holds the switch and URL as compact rows, then the MCP token and Web port blocks inside it.
- Settings > Document reading: the OCR card groups its settings under titled blocks (When to use OCR, Maths pages, Engines) in two columns from 768 px of card width.
- Do not use CSS columns (`columns-2`) for card groups. The order then reads down each column, and cards move to a different column when their height changes.
- Do not use native CSS masonry (`grid-lanes`) yet. Browser support is not ready.

## Mini cards inside cards

Every card holds its parts in mini cards or, on a settings page with many settings, in compact rows. Apply these rules in every view without being asked.

- Use `CardInset` from `web/src/components/ui/card.tsx` for one part of a card: one setting, one field, one read-only list, one status block, one drop zone.
- `CardInset` is lighter than the card: `rounded-control border border-border bg-background/60 p-3`, no shadow. It is the same pattern as the OMMS inner cards.
- Give each setting its own `CardInset`. Do not stack several settings in one.
- Exception: Settings > Configuration shows each block as one table in its card, not as mini cards.
- A settings page with many settings per card uses `DenseSettingRows` (`web/src/settings/SettingBox.tsx`). Inside it, each setting is a compact row with a hairline between rows: label, then value and source on one line, a ghost Edit on the right. Use `SettingBox` instead of `CardInset` for a new part of such a card. It falls back to a mini card outside `DenseSettingRows`.
- Pages that use `DenseSettingRows` today: Providers, Document reading, MCP and the Text card on Appearance. The other Settings tabs keep mini cards.
- `SettingRow`, `KeySettingRow` (`web/src/settings/SettingRow.tsx`) and `ReadingSettingRow` render a `SettingBox`: a `CardInset` normally, a compact row inside `DenseSettingRows`. Use them for a new setting, and do not wrap them again.
- Keep the card title, the card description, notices such as "Text you send leaves this machine" and the card's own action (for example Test) outside the mini cards.
- Never put a `Card` inside a `Card`. A section that brings its own cards (for example Knowledge Base > Add) sits outside the section card.
- A view with no cards at all is wrong. Put each panel of the view in a `Card`, then its parts in mini cards.
- When you apply this rule, check every tab of the view, not only the tab you were shown. `web/src/settings/SettingsCards.test.tsx` fails when a Settings tab has no card. Add a case there for a new tab.

## Shell

Navigation has seven items in this order: Home, Chat, Knowledge Base, Studio, Experiments, Integrations, Settings. Home is the landing view. Each row has a Lucide icon before its label and `aria-current="page"` on the active row.

| Element | Rule |
| --- | --- |
| Top bar | Muted surface, 1px bottom border, elevation shadow. Shows the brand, an engine status pill (collection count, or "offline"), the theme `Select` (System, Light, Dark), and an icon-only button beside it that shows sun or moon for the theme in effect and switches Light and Dark in one click. Its accessible name names the target theme. |
| Inspector | The global toggle and empty panel are gone. Detail regions open inside Chat, Studio, and Experiments on selection. |
| Skip link, main focus | Keep the existing skip link. Focus moves to the view `h1` after navigation. |
| Routes | Typed hash routes from `lib/routes.ts` (design D9): `#/home`, `#/knowledge-base[/<collection>]`, `#/chat[/<collection>]`, `#/studio[/<profile-id>[/<purpose>]]` (purpose is `ingest`, `search` or `answer`), `#/experiments`, `#/experiments/runs/<run-id>`, `#/experiments/library/<project>/<folder>`, `#/experiments/notebooks/<notebook-id>`, `#/integrations`, `#/settings`. Segments are URI-encoded. An unknown hash opens Home and is rewritten to `#/home`; earlier routes are not redirected. |
| Narrow screens | Below `md`, the navigation becomes one row of the seven area icons with short labels under the top bar (owner decision; no menu button). Targets are at least 44px. No horizontal page scroll. |

Read the presentation spec and `web/src/App.tsx` before you change route names.

## Home

A grid of project cards (`gap-3`, `items-start`). Each card is flat with a 1px border and shows the collection name (subsection title), a profile badge (hue hash), and document and chunk counts as meta text. The whole card opens the project.

Empty state: icon, one sentence naming the cause, one action that starts an ingest into a named collection.

A card opens `#/knowledge-base/<collection>`: source table with orphan status, upload panel, folder ingest panel, profile information, deletion, and search. Orphan status is a badge with text. The route is the active project; `lastCollection` in `omrs-preferences` is only the default for `#/knowledge-base` and `#/chat`.

## Chat

Layout: a centred transcript column at `min(100%, 48rem)`, the composer docked at the bottom of that column, and a right-hand knowledge base panel listing collections with counts and a selected state (`chip` or `--selection`, never the accent).

- Messages are plain rows with role labels. No bubble framework and no chat library.
- The view states that each question answers on its own. Put this notice near the composer in meta text.
- A "New chat" action clears the transcript. It keeps the selected knowledge base.
- Each assistant turn shows the answer, the verification status as text with its badge, citations as chips under the answer, and evidence in a collapsible section. Opening a chip or an evidence row shows the chunk in the shared chunk viewer.
- A failed turn shows one friendly line and a Retry action. The raw message goes to the console only.
- Switching the knowledge base mid-conversation keeps earlier turns. The next turn queries the new collection.
- The composer sends on a clear action. Disable it while a turn is pending, and keep the pending state visible as text.

Reuse `views/shared/ChunkViewer.tsx` (or its moved location). Delete `views/search/` and `views/ask/` only after chat tests cover their behaviour (task 3.5).

## Knowledge Base

Four sections, switched with `chip` buttons and shown one at a time: Sources, Search, Add, Profile (owner decision).

Manages the active project's sources: file upload (managed upload plus an ingest job), folder ingest from approved roots, and the source table.

- Sources, Search and Profile sit in one section card. Add shows two cards in `MasonryColumns`: Upload files and Ingest from an approved folder.
- Pick files with `FileDropZone` (`web/src/knowledge-base/FileDropZone.tsx`): drop files on the zone or press Choose files. Each pick adds to the list. Each listed file shows its size and a Remove button. The list clears when the upload run ends, and the results list replaces it.

- Show job status as text with a status badge.
- Refuse an oversized file in the client with a friendly message before any upload. Never send it.
- With no approved root, state that no folder is approved and name the `--root` server flag in a `code` element.
- Pick the active project with the same project switch used elsewhere. Do not add a second selector pattern.

## Studio

Gallery first: profile cards in two groups, "Built-in profiles" and "Your profiles", plus a "New empty profile" card. A closed "How profiles work" disclosure sits under the header. Each card shows the title, the profile ID, use and readiness, with Open profile, Duplicate and (for your profiles) Delete. Built-in profiles are read-only.

The canvas sub-page (`#/studio/<profile-id>/<purpose>`). The header shows the profile, an Ingest, Search and Answer switch and an "All profiles" link. A built-in profile shows a read-only notice and "Duplicate to edit". The panel sections are Pipeline settings (Base profile as text, Collection), Operations, Steps and connections, Connect ports, Revision and run, Step settings. An open section shows its title, icon and chevron in the accent colour (`data-[state=open]:text-primary-label` in `web/src/components/ui/accordion.tsx`); an open section on the collapsed rail shows the same colour. The panel header holds an Expand all / Collapse all button beside Collapse panel (`web/src/studio/CanvasPanel.tsx`). "Save revision" asks "Save this revision?" when a collection uses the profile:

- The flow surface fills the main area.
- The operation palette is the right-hand column.
- Selecting a step opens its settings in a detail region on the same page.
- Revision, validation, and run behaviour are unchanged.

React Flow nodes and edges read the semantic tokens. Node kind badges use the hue hash. Run state on a node pairs the status colour with text. Respect `prefers-reduced-motion` for edge animation (`runs/useReducedMotion.ts` exists). The canvas needs a keyboard route to add, select, and delete nodes. Do not regress what `CanvasView` tests cover.

## Experiments

Five section chips in this order: Library (default), Notebooks, Sandboxes, Code editor, Runs.

Library lists research experiments from the projects the user adds. A project picker starts with "All projects". Filters for status and category and a text search sit above the cards. One card per experiment: number, title, status badge, category, date, finding, and a count of checker errors and warnings. Status badges: `PASS` success, `FAIL` error, `INCONCLUSIVE` and `ACTIVE` warning, `PLANNED` and `MEASURED` info, `SUPERSEDED` muted. At 390 px show one card per row.

The experiment page (`#/experiments/library/<project>/<folder>`) has a record header, tabs Protocol, Plan, Report, Files and Checks, and an "Add to notebook" menu. Render Markdown with no raw HTML. List files the app does not open (HTML review pages, images, PDFs) with their size and say they are not opened in the app.

Notebooks lists project notebooks first, then user notebooks. A notebook page (`#/experiments/notebooks/<id>`) shows entry cards. A missing entry shows as missing with a remove action.

Sandboxes holds the experiment contexts: folder groups, each listing its sub-experiments. An empty folder still shows with an empty indication. Provide forms to create a main folder and a sub-experiment with declared factors. A rejected path shows a validation message next to the field.

Code editor keeps the marimo notebook panels intact: tool registration, trust notice, one-time credentials, and editor launch with a stop action. The one-time credential is shown once, so keep the copy action and the warning visible. Do not log or screenshot secrets.

A Runs section holds the run list, status filter, refresh, and run detail with evidence. Two sections keep this long view manageable. Use the existing filters.

With no experiment root approved, state it and name the `--experiment-root` server flag.

## Integrations

Section chips: Extras, Tools, OCR engines, Model files, Local servers. Each section is one full-width card with a row per entry, in server order (`EntryList` and `EntryRow` in `web/src/integrations/EntryList.tsx`), with a hairline between rows. A row shows the name and status badge, the purpose and any state lines on the left. Install, Uninstall and the copy commands sit on the right from 768 px of card width (`@3xl:grid-cols-2`). A tall row only makes that row taller, so no masonry is needed. The OCR workers folder card sits above the OCR engines list. A row keeps the id `integration-<id>` with `tabIndex=-1`, so a link such as `#/integrations/anthropic` focuses it.

State that availability reflects the running launch. Install and Uninstall run from the row when the server can install (ADR-094, ADR-096); an extra needs a server restart, a tool does not (ADR-101). Otherwise the row offers the command to run outside the app. A failed load shows the friendly line and Retry. Give the copy action visible confirmation and an announcement for assistive technology (a polite live region).

## Settings

Seven sections switched with `chip` buttons, one at a time (redesign design D13): Appearance, Providers, Chat, MCP, Server log, Runtime, Workspace. Each chip writes `#/settings/<section>`. Controls that moved to other views are removed with their tests.

- Appearance: a Theme card with System, Light and Dark chips (the same mode as the top-bar switch), a filter, and a light and a dark theme list. Each list is a radio list with a colour swatch per theme: the OMRS default plus the 29 OpenChamber pairs in `web/src/lib/themes/themeData.ts` (generated by `web/scripts/themes_from_openchamber.py`; do not edit it by hand). A Text card holds the interface font, the code font and the text size (80 % to 150 %). Every choice is stored in `omrs-preferences` in this browser. Put `relative` on the scroll box of each list: its radios are `sr-only`, and without `relative` they sit outside the box and stretch the page height (`web/src/settings/ThemeList.tsx`). The Text card uses `DenseSettingRows`.
- Providers: one card per registered LLM provider (Ollama, llama.cpp, OpenRouter, OpenAI-compatible, Anthropic; names come from the server) with read-only URLs and model names in `code`, role badges, "Installed" or an install hint, an address `Input` with source line, Save and Reset, a key `Input type="password"` (write-only, empties after save, Save key and Remove key), and a Test button that shows reachable or the reason as a status badge. An environment value shows "Set from environment (read-only here)" and locks the field. A config-file value shows "Set from config file (read-only here)" with the lock text "Set in ~/.config/omrs/omrs.jsonc. Edit that file and restart to change it." and locks the field. A key-file value shows "Set from key file (read-only here). Saving a key in the keychain overrides it." and keeps the key input. With no system keychain, one line replaces the key input and names the environment variable. Saved values apply at once, so show no restart banner. Show a key only as "Key set", its source, the save time and the last four characters when the server sends them. Never render a full key.
- Ollama card: add a number `Input` "Context window (tokens)" (2048 to 262144) with its source line and lock text; friendly error "Enter 2,048 to 262,144." for a bad value.
- Provider cards use no masonry (see Card groups). Local providers go full width in the "On this machine" band, cloud providers in an equal-height grid. The llama.cpp "Local server" panel is a `PanelDisclosure` that sits under the provider fields after `border-t border-border pt-3`.
- llama.cpp card, "Local server" panel: state `Badge` with text (`stopped`, `starting`, `running`, `failed`) and one friendly line for each fixed reason (`binary-invalid`, `model-invalid`, `not-loopback`, `port-in-use`, `exited`, `timeout`, `not-configured`); `Input` fields for program path, model, context window and idle sleep with source lines, plus a one-line note on what idle sleep does; Start, Stop and Restart buttons (Start disabled while starting or running, Stop disabled while stopped); the line "omrs starts and stops only this server. It never touches a server you started yourself."; "Restart to apply" when saved values differ; program and model read-only without the `credentials` scope. Never show output of the server.
- Chat: a `Select` for the provider (items not ready are disabled with the reason), an `Input` for the model name, List models (fills a second `Select`), Test, Save and Clear. Say where the choice applies: MCP clients of this server without their own model, not metadata extraction, not stdio or the CLI. Show the cloud warning when the provider is cloud.
- MCP: two full-width cards (see Card groups). The stdio client configuration (`uv run --directory <config_dir> omrs`) in a `code` block with a copy button, and, from `add-mcp-http-transport`: the HTTP on/off switch (show only the state the server returns), the HTTP configuration with the `/mcp` URL, token rotate and revoke with a new token shown once, and the saved web port with a next-launch notice.
- Server log: a monospace, terminal-style panel on the muted surface (`bg-muted`), one record per line (time, level badge, logger, message), level filter chips, Pause, Copy, and auto-scroll only while scrolled to the bottom. Mark it `role="log"` so screen readers announce new lines politely.
- Configuration: one `Card` for each block, with one `Table` (Setting | Value | Source) inside it. The card header holds the title on the left and Edit on the right. In edit mode, Cancel and Save (primary) take the place of Edit. Save sends every changed cell of that table in one request, and only one table is in edit mode at a time. Each editable Value cell holds only its `SettingControl` and its rule line. A read-only value stays text with a lock icon, and in edit mode its reason shows on a row under it. A row that waits for a restart shows "Next launch: <value>" under the value and "Restart to apply" in the Source cell. Below `sm` the Source column hides and the source shows under the key. Document reading keeps its mini cards.
- Runtime and Workspace: capabilities and the workspace path. Keep paths in `code` elements with `overflow-wrap: anywhere`.
