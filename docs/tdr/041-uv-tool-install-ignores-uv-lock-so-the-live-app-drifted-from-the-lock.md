# TDR-041: uv tool install ignores uv.lock, so the live app drifted from the lock

- **Date:** 2026-10-26
- **Status:** Accepted
- **Deciders:** Maintainer
- **Tags:** install | uv | dependencies | live-app

## Context

The live app runs from a `uv tool` install in `~/.local/share/uv/tools/omrs`.
The documented update step was to run this from a checkout of `v3`:

```bash
uv tool install --reinstall "omrs[web,hybrid] @ <v3 checkout>"
```

On 2026-10-25 a reinstall like this gave versions that the lock did not hold:

| Package | `uv.lock` | Installed |
|---|---|---|
| lancedb | 0.37.1 | 0.40.0 |
| pylance | 10.0.0 | 13.0.0 |
| pyarrow | 25.0.1 | 26.0.0 |

lancedb 0.40 changes how filter values are written (ADR-098). At that time
the code was not tested with it. The live app ran an untested set of
packages, and nothing showed it.

### Root Cause Analysis

`uv tool install` does not read the project's `uv.lock`. By default it
resolves from scratch, from the ranges that `pyproject.toml` declares
(uv source: `crates/uv-tool-commands/src/install.rs` uses
`EnvironmentResolution::Specific` when tool locks are off). When tool locks
are on, uv reads a lock in the tool's own folder, never the project's. So
each reinstall takes the newest release inside each range. CI and local
tests use the lock. The live app did not.

Earlier reinstalls probably drifted in the same way, but no one compared
the installed versions with the lock.

## Decision

1. **Reinstall the live app with the lock as constraints.** Export the lock
   for the extras the app uses, then pass it to `uv tool install -c`:

   ```bash
   uv export --frozen --extra web --extra hybrid --no-hashes --no-emit-project --no-header -o <scratch>/live-constraints.txt
   uv tool install --reinstall -c <scratch>/live-constraints.txt "omrs[web,hybrid] @ <v3 checkout>"
   omrs web restart
   ```

   Name the same extras in both commands. A constraint only limits a
   version, so a package outside the export is still resolved freely.
2. **Check the result.** Compare every installed distribution in the tool
   environment with the export. Expect 0 differences. Then check
   `/v1/health`.
3. **The guide shows the locked command.** `docs/guides/cli-reference.md`
   (login item, rule 1) now uses it.

## Consequences

### Positive

- The live app runs the same versions that CI and the local tests run.
- A dependency upgrade reaches the live app only through a reviewed change
  to `uv.lock`.

### Negative

- The update step has two commands and a scratch file.
- The Integrations page installs an extra with `uv pip install` into the
  server's Python (ADR-094). That path does not use the lock. A new package
  can arrive at its newest version. Packages that are already installed
  and satisfy the range stay as they are.

### Neutral

- On 2026-10-26 the live app was reinstalled this way from `v3` at
  `4cc4eaa4`. 0 packages differed from the lock: lancedb 0.40.0, pylance
  10.0.0, pyarrow 25.0.1.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Keep the plain `uv tool install --reinstall` | It installs versions that no test has run. |
| Install the live app with `uv sync` into a fixed folder | The login item and the Integrations page expect a `uv tool` install (ADR-094). |
| Pin exact versions in `pyproject.toml` | A library must declare ranges. The dependency floor policy (ADR-042) needs them. |
| Turn on uv tool locks | The tool lock is a separate lock in the tool folder. It does not follow the project's `uv.lock`. |

## How to Recognise / Handle This Again

1. **Symptom:** the live app behaves differently from the tests, or a
   package version in the tool environment is newer than in `uv.lock`.
2. **Check:** list the tool environment's distributions and compare them
   with `uv export --frozen` for the same extras.
3. **Fix:** reinstall with the locked commands in decision 1, then restart.
4. **Before each reinstall:** back up `~/.omrs/workspace/workspace.db`.

## Revisit Triggers

- `uv tool install` learns to install from a project lock.
- OMRS ships a command that reinstalls itself from a lock.
- The Integrations install path starts to use the lock as constraints.

## References

- uv source: `crates/uv-tool-commands/src/install.rs` and `src/common.rs` (tool installs resolve without the project lock)
- `docs/guides/cli-reference.md` (login item, rule 1)
- ADR-042 (dependency floors), ADR-094 (app installs extras into itself), ADR-098 (lancedb 0.40)
- TDR-040 (the lancedb exit crash that the 0.40 upgrade fixed)
