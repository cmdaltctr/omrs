# TDR Format Guide

Section-by-section guidance for writing Technical Decision Records.

## Header

```markdown
# TDR-NNN: <Short descriptive title>

- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Superseded by TDR-XXX | Deprecated
- **Deciders:** <Names>
- **Supersedes:** TDR-XXX (if applicable)
- **Tags:** tauri | desktop | ocr | security (optional)
```

Write the header fields as a bullet list. Field lines without bullets join
into one paragraph when the markdown renders.

- **ID**: Zero-padded, monotonic. `NNN` = next number in sequence.
- **Title**: Imperative or declarative. Scopes to one decision.
- **Status**: `Proposed` while under discussion, `Accepted` once agreed,
  `Superseded by TDR-XXX` when replaced, `Deprecated` when no longer relevant.
- **Supersedes**: Link to the TDR this replaces (if any). Never edit an
  Accepted TDR — supersede it.
- **Tags**: Optional. Lowercase, pipe-separated. Useful for filtering as the
  collection grows.

## Context

State the problem and constraints factually. No opinion yet. Answer:
- What is the issue?
- What environment/platform does it occur in?
- What was tried before this decision?

Keep under 200 words. If the TDR is debugging-driven, include a **Root Cause
Analysis** subsection that distinguishes symptom from cause, with error
messages or empirical evidence.

### Example (from TDR-003)

```markdown
## Context

The dashboard customise mode allows users to reorder widgets via drag-and-drop.
The original implementation used the HTML5 drag-and-drop API. This worked in
browsers but did not work in Tauri's WKWebView on macOS.

### Root cause

Tauri v2 enables an internal native drag-and-drop system by default
(`dragDropEnabled: true`). This system intercepts drag-related events at the
native level, blocking both HTML5 and pointer-based drag-and-drop from
reaching the DOM.
```

## Decision

Be concrete. Include code snippets, config changes, or commands that make the
decision immediately reproducible. A reader should be able to implement the
fix from this section alone without reading the codebase.

If the decision has multiple parts, use numbered subsections.

## Consequences

Split into three subsections:

- **Positive** — benefits gained from this decision
- **Negative** — trade-offs accepted (be honest)
- **Neutral** — side effects that are neither good nor bad

This split forces honest trade-off assessment. The Negative section is the
most important — it records what you knowingly gave up.

## Alternatives Considered

Table format:

```markdown
| Option | Rejected Because |
|--------|-----------------|
| Keep programmatic open_devtools() | Forces inspector open every startup; no way to close it |
| Keyboard shortcut only (no menu bar) | No discoverable UI; macOS users expect menu bar items |
```

This is the most valuable section for future readers. It captures *why not*
the obvious alternatives, preventing re-litigation of settled decisions.

## How to Recognise / Handle This Again

This is the standout section that distinguishes TDRs from standard ADRs. Turn
the TDR into an operational playbook:

1. **Symptoms** — what does the problem look like?
2. **Diagnostics** — how to confirm it's the same issue?
3. **Recovery** — commands or steps to fix it

### Example (from TDR-001)

```markdown
### PHP sidecar health check timeout after build

1. Check if `src-tauri/laravel-app/` or `src-tauri/target/debug/laravel-app/`
   exists — these are stale build artefacts.
2. Remove them: `rm -rf src-tauri/laravel-app src-tauri/target/debug/laravel-app`
   (keep `src-tauri/laravel-app/.gitkeep`).
3. Verify `app_path()` resolves to the project root.
4. If userData storage is missing framework directories, create them:
   `mkdir -p ~/Library/Application\ Support/com.receiptscanner.app/storage/framework/{cache/data,sessions,views}`
```

## Revisit Triggers

Record conditions that should prompt re-evaluating the decision. This prevents
external dependency drift — the scenario where a decision is still "Accepted"
but the rationale has rotted because the world changed.

### Examples

```markdown
## Revisit Triggers

- Tauri v3 release — `dragDropEnabled` behaviour may change
- App Store submission — must remove `devtools` Cargo feature (private API)
- Cross-platform support (Linux/Windows) — menu bar and drag-and-drop may differ
```

## References

List:
- External documentation links (Tauri docs, GitHub issues)
- Related ADRs and TDRs (cross-link by ID)
- File paths in the codebase that implement this decision

```markdown
## References

- Tauri v2 Debug docs: <https://tauri.app/develop/debug/>
- GitHub Issue #11768: <https://github.com/tauri-apps/tauri/issues/11768>
- `src-tauri/Cargo.toml` — `devtools` feature
- ADR-014: Tauri Desktop Packaging
- TDR-001: Tauri DevTools Menu Bar
```
