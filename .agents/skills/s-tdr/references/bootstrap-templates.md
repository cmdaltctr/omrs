# Bootstrap Templates

Use these templates when a project does not yet have `docs/tdr/` set up.
Create `docs/tdr/README.md` and `docs/tdr/TEMPLATE.md` with the content below.

## docs/tdr/README.md

```markdown
# Technical Decision Records (TDRs)

TDRs capture **implementation-level technical decisions** — platform-specific
workarounds, debugging findings, build pipeline decisions, and behavioural
fixes. For **architectural** decisions (framework choice, auth model, data
architecture), see the [ADR index](../adr/).

## When to write a TDR vs an ADR

| TDR | ADR |
|-----|-----|
| How to make a specific technology behave correctly | What stack/structure to use |
| Platform-specific workarounds (WKWebView, sidecar) | Framework and language choices |
| Debugging findings with root cause analysis | Authentication and authorisation models |
| Build pipeline and tooling decisions | Data model and API design |
| "Why is X broken and how did we fix it?" | "Why did we choose X over Y?" |

## How to use

1. Copy `TEMPLATE.md` to a new file: `NNN-short-descriptive-title.md`
2. Fill in all sections — see the template for guidance
3. Add an entry to the table below
4. Commit with: `docs: add TDR-NNN <short title>`

## Index

| ID  | Title | Status | Date |
|-----|-------|--------|------|
| _No TDRs yet_ | | | |

## Status values

- **Proposed** — under discussion, not yet agreed
- **Accepted** — agreed and active
- **Superseded** — replaced by a later TDR (link to superseding TDR)
- **Deprecated** — no longer relevant, not superseded by a specific TDR

Once a TDR is **Accepted**, never edit its decision — supersede it with a new
TDR and update the status here.
```

## docs/tdr/TEMPLATE.md

```markdown
# TDR-NNN: <Short descriptive title — imperative or declarative>

- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Superseded by TDR-XXX | Deprecated
- **Deciders:** <Names>
- **Supersedes:** TDR-XXX (if applicable)
- **Tags:** tauri | desktop | ocr | security (optional, for filtering)

## Context

<What is the problem? What constraints exist? What was tried before?
State the facts — no opinion yet. Keep under 200 words.>

### Root Cause Analysis (if debugging-driven)

<What is the actual cause? Distinguish symptom from cause.
Include error messages, logs, or empirical findings as evidence.>

## Decision

<What did you decide? Be concrete — include code snippets, config changes,
or commands that make the decision immediately actionable.>

## Consequences

### Positive

- <Benefits gained>

### Negative

- <Trade-offs accepted>

### Neutral

- <Side effects that are neither good nor bad>

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| <Option A> | <Why it was rejected> |
| <Option B> | <Why it was rejected> |

## How to Recognise / Handle This Again

<Diagnostic steps, symptoms to watch for, recovery commands.
This section turns the TDR from a historical artefact into an operational
playbook. Include:>

1. <Symptom description>
2. <Diagnostic steps>
3. <Recovery or workaround commands>

## Revisit Triggers

<What conditions should prompt re-evaluating this decision?
Examples: "Tauri v3 release", "App Store submission", "team grows beyond 2".>

## References

- <Links to docs, GitHub issues, PRs, related ADRs/TDRs>
- <File paths in the codebase that implement this decision>
```
