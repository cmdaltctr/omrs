---
name: s-adr
description: "Document architectural and technical decisions that affect the project's direction. Use this skill when documenting why you chose one technology over another, recording a significant architecture change, or creating decision records in docs/adr/. Triggers on: ADR, architectural decision, why did we choose, technology decision, design rationale, document this decision, record this choice."
---

# Architecture Decision Records (ADR)

This skill provides the template, conventions, and process for creating and
maintaining Architecture Decision Records in `docs/adr/`.

## When to Create an ADR

Create an ADR for any decision that is:
- **Architectural** — affects system structure, dependencies, or core patterns
- **Significant** — non-trivial, not obvious from code alone
- **Consequential** — has tradeoffs worth documenting for future maintainers
- **Not purely code-style** — formatting preferences don't need ADRs

> **Heuristic**: If a future maintainer would ask "Why did we choose X over Y here?"
> and the answer isn't obvious from the code — it needs an ADR.

## Quick Reference: What an ADR Contains

| Section | Purpose |
|---------|---------|
| **Context** | Problem, constraints, forces — what made this decision necessary |
| **Decision** | What was chosen, specifically, and why |
| **Consequences** | Positive, negative, and neutral outcomes |
| **Alternatives Considered** | Options rejected and why (table format) |
| **References** | Links to code, docs, related ADRs |

## Directory Setup

If `docs/adr/` does not exist in the project, create it:

```
mkdir -p docs/adr
```

## ADR Template

The full template lives at `references/adr-template.md`. **Read it when you
are about to create a new ADR.** It includes the complete section structure
with placeholder guidance.

The template follows this structure at a glance:

```markdown
# ADR-NNN: [Title]

- **Date:** YYYY-MM-DD
- **Status:** Proposed
- **Deciders:** [Name or team]

## Context
…

## Decision
…

## Consequences
### Positive
…
### Negative
…
### Neutral
…

## Alternatives Considered
| Option | Rejected Because |
|--------|-----------------|
| … | … |

## References
…
```

## ADR Naming Convention

Files are named: `NNN-kebab-case-title.md`

- `NNN` — three-digit zero-padded sequential number (001, 002, …)
- `kebab-case-title` — brief, descriptive slug matching the ADR title

To determine the next number, read the existing ADR files in `docs/adr/` and
increment the highest. If the directory is empty, start at `001`.

## Status Lifecycle

| Status | Meaning |
|--------|---------|
| **Proposed** | Freshly created, not yet confirmed |
| **Accepted** | Decision confirmed and implemented |
| **Deprecated** | Superseded by a later ADR |
| **Superseded** | Replaced; see "Superseded by ADR-NNN" |

New ADRs start as **Proposed**. Once implementation is complete and verified,
update status to **Accepted**. ADRs are immutable once Accepted; superseded
decisions get a `- **Superseded by:** ADR-00X` bullet in the header list.

## Index File (ADR_README.md)

Every `docs/adr/` directory MUST have an `ADR_README.md` index file. It
serves as the discoverable table of contents.

**If `ADR_README.md` does not exist**: Read `references/adr-readme-template.md`
to get the full template, then create the file.

**If it already exists**: Append a new row to the index table in chronological
order. Do NOT replace or rewrite the existing convention section.

The index table format:

```markdown
| ADR | Title | Date | Status |
|-----|-------|------|--------|
| [NNN](./NNN-kebab-case-title.md) | Title | YYYY-MM-DD | Proposed |
```

## ADR Creation Workflow

1. **Determine the number**: Read `docs/adr/`, find highest sequential number, increment
2. **Read the full template**: `references/adr-template.md`
3. **Create the ADR file**: `docs/adr/NNN-kebab-case-title.md` using the template
4. **Update the index**: Add a new row to `docs/adr/ADR_README.md`
5. **Report back**: ADR number, title, and file path

### Example

For a decision to "Use Bun as the JavaScript runtime":

1. Read `docs/adr/` → highest number is 018 → new number is 019
2. Read `references/adr-template.md`
3. Create `docs/adr/019-use-bun-as-javascript-runtime.md`
4. Update `ADR_README.md` index table with new row
5. Report: "Created ADR-019: Use Bun as JavaScript Runtime at `docs/adr/019-use-bun-as-javascript-runtime.md`"

## Reference Files

- **`references/adr-template.md`** — the complete, copy-paste ADR template with section guidance. Read this before creating any ADR.
- **`references/adr-readme-template.md`** — the `ADR_README.md` index file template. Read this when initialising `docs/adr/` for the first time.
