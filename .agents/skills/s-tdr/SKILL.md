---
name: s-tdr
description: "Technical Decision Record format and best practices. Use when writing or reviewing a TDR, creating a technical decision record, documenting a workaround or debugging finding, or when asked about TDR format."
---
# Skill: s-tdr

This skill provides the TDR (Technical Decision Record) format, template, and
best practices for any software project.

## When to write a TDR vs an ADR

- **TDR** — implementation-level: platform-specific workarounds, debugging
  findings, build pipeline decisions, behavioural fixes. Answers "why is X
  broken and how did we fix it?"
- **ADR** — architectural: framework choice, auth model, data architecture.
  Answers "why did we choose X over Y?"

If the decision is about *what stack/structure to use*, write an ADR.
If it's about *how to make a specific technology behave correctly*, write a TDR.

## TDR format

Every TDR lives in `docs/tdr/NNN-short-descriptive-title.md` and follows this
structure:

1. **Header** — ID, Date, Status, Deciders, Supersedes (optional), Tags (optional).
   Write the fields under the title as a bullet list (`- **Date:** ...`).
2. **Context** — the problem, constraints, what was tried. Include a Root Cause
   Analysis subsection if debugging-driven.
3. **Decision** — what was decided, with concrete code/config/commands.
4. **Consequences** — Positive / Negative / Neutral.
5. **Alternatives Considered** — table of rejected options and why.
6. **How to Recognise / Handle This Again** — diagnostic steps and recovery
   commands. This is the standout section that makes TDRs operationally useful.
7. **Revisit Triggers** — conditions that should prompt re-evaluation.
8. **References** — links to docs, issues, PRs, related ADRs/TDRs, file paths.

## Bootstrap (if docs/tdr/ does not exist)

If the project does not yet have a `docs/tdr/` directory, create it with:

1. `docs/tdr/README.md` — index file with TDR-vs-ADR guidance and an empty table
2. `docs/tdr/TEMPLATE.md` — copy-and-fill template

Use the templates in `references/bootstrap-templates.md` for the exact content
of these two files.

## Workflow

1. **Check for `docs/tdr/`** — if it doesn't exist, bootstrap it (see above)
2. **Check for `docs/tdr/TEMPLATE.md`** — if missing, create it from
   `references/bootstrap-templates.md`
3. **Check for `docs/tdr/README.md`** — if missing, create it from
   `references/bootstrap-templates.md`
4. **Find the next number** — list `docs/tdr/` and take the highest existing
   `NNN` plus one. Check other local branches for the same number before
   committing, so two branches don't collide.
5. Copy `docs/tdr/TEMPLATE.md` to `docs/tdr/NNN-short-title.md` (next number)
6. Fill in all sections — see the format guide for guidance
7. **Add an entry to the table in `docs/tdr/README.md`** — read the tail of the
   existing table first and append the new row after the last one, matching the
   columns and status wording already in use. Do not rewrite the table.
8. Commit with: `docs: add TDR-NNN <short title>`

## Committing

- Commit the TDR as its **own** `docs:` commit, separate from the code fix it
  describes. If the fix and the TDR are already staged together, split them.
- The TDR may be written before the fix is committed, but say so plainly and
  don't claim it is committed until it is.
- If a docs test guards the TDR index or the paths a TDR cites (for example
  `tests/test_docs_references.py`), run it before committing.

## Updating an existing TDR

Once Accepted, a TDR is immutable. If a later finding shows an earlier TDR is
wrong, do not silently rewrite its decision: mark the affected sections as
superseded (with a pointer to the new TDR) and record the corrected evidence in
the new one.

## Key principles

- **Brevity** — one page max. Link to separate docs for deep detail.
- **Immutability** — once Accepted, never edit the decision. Supersede with a
  new TDR and update the status field.
- **Actionability** — the Decision section must contain enough detail (code,
  config, commands) to reproduce the fix without reading the codebase.
- **Operational value** — "How to Recognise / Handle This Again" turns each TDR
  into a playbook entry, not just a historical record.
- **Revisit awareness** — "Revisit Triggers" prevents external dependency drift
  from making accepted decisions silently stale.

## References

- [Format guide](references/format-guide.md) — detailed section-by-section guidance with examples
- [Best practices](references/best-practices.md) — principles derived from Nygard, Fowler, and project experience
- [Bootstrap templates](references/bootstrap-templates.md) — README.md and TEMPLATE.md content for new projects
