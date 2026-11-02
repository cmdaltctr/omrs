# TDR Best Practices

Principles derived from Michael Nygard's ADR template, Martin Fowler's
guidance, the ADR GitHub community, and project experience.

## 1. Brevity

Keep each TDR to one page. Martin Fowler: *"The most important thing to bear
in mind here is brevity. Keep the ADR short and to the point — typically a
single page. If there's supporting material, link to it."*

If a TDR needs more detail, link to a separate design document rather than
bloating the record. TDR-003 (78 lines) is ideal. TDR-001 (203 lines) is
borderline — the two-issue scope justifies it, but single-issue TDRs should
stay under 120 lines.

## 2. Immutability

Once a TDR is **Accepted**, never edit its decision. If circumstances change,
create a new TDR that supersedes it:

1. Write the new TDR with `Status: Accepted`
2. Update the old TDR's status to `Superseded by TDR-XXX`
3. Add a `- **Supersedes:** TDR-XXX` bullet to the new TDR's header
4. Update the index in `README.md`

This creates a clear decision log showing how long each decision governed the
work, which is the primary value of decision records over time.

## 3. Actionability

The Decision section must contain enough concrete detail (code snippets, config
changes, commands) that a reader can reproduce the fix without exploring the
codebase. Vague decisions like "use pointer events instead" are insufficient —
show the actual config change and approach.

## 4. Operational value

The "How to Recognise / Handle This Again" section is what makes TDRs more
useful than standard ADRs. It transforms each record from a historical artefact
into a playbook entry. Future you (or a teammate) encountering the same symptom
can find the TDR and follow the recovery steps directly.

Always include:
- **Symptoms** — what the problem looks like to someone encountering it fresh
- **Diagnostics** — how to confirm it's the same issue, not a different one
- **Recovery** — exact commands or steps to resolve it

## 5. Revisit awareness

External dependency drift is the hardest decay mode to catch. A decision made
when AWS Lambda had multi-second cold starts may be stale after Provisioned
Concurrency — but nothing in the ADR signals this.

The "Revisit Triggers" section records the conditions under which the decision
should be re-evaluated. This is a lightweight checkpoint: when a trigger fires,
re-read the TDR and decide whether to supersede it.

## 6. One decision per TDR

Each TDR should capture a single decision. If two issues surfaced together
(like TDR-001's DevTools + stale laravel-app), they can share a TDR only if
the decisions are tightly coupled. Otherwise, split into separate TDRs for
clarity and independent supersession.

## 7. Store in version control

TDRs live in `docs/tdr/` in the project repository, in markdown. This makes
them:
- Available to anyone working in the codebase
- Diffable like code (see when and how decisions changed)
- Discoverable in the IDE

## 8. Numbering and naming

- Zero-padded monotonic numbers: `001`, `002`, `003`
- Filename: `NNN-short-descriptive-title.md`
- Title in file: `TDR-NNN: Short Descriptive Title`
- Names should be readable in a directory listing — capture the decision, not
  the symptom. "Disable Tauri Native Drag-and-Drop" is better than "Drag and
  Drop Bug Fix".

## 9. Alternatives are the most valuable section

The Alternatives Considered table captures *why not* the obvious alternatives.
This prevents re-litigation of settled decisions. When a new developer asks
"why don't we just do X?", the TDR answers immediately.

Be specific about rejection reasons. "Lacks features" is weak. "Lacks native
queue orchestration, mature policy classes, and Laravel's testing/migration
ecosystem" is strong.

## 10. Link related records

Cross-link ADRs and TDRs by ID. A TDR about DevTools should reference the ADR
about Tauri Desktop Packaging. This creates a navigable decision graph.
