import { useMemo } from "react";
import { ApiError } from "../api/client";
import { AlertNotice } from "../components/AlertNotice";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";

type RefusalAction = "retry" | "check";
type RefusalKind = "install" | "tool-install" | "uninstall";

/** A marimo editor that this server started blocks a marimo install or uninstall (ADR-101). */
export const EDITOR_RUNNING = "A marimo editor that OMRS started is running. Stop it in Experiments, Code editor, then try again.";

/** One line and one action for each `reason` of a refused install (409). */
const REFUSALS: Record<string, { message: string; action: RefusalAction }> = {
  "install-running": { message: "Another install is running. Wait for it to finish, then try again.", action: "retry" },
  "not-installable-here": { message: "This integration cannot be installed from the app. Run its command instead.", action: "check" },
  "not-uv-tool": { message: "This server was not installed with uv tool, so it cannot install from the app. Run the command instead.", action: "check" },
  "status-unknown": { message: "The server could not check this integration, so it cannot install it. Run the command instead.", action: "check" },
  "uv-not-found": { message: "The server cannot find uv, so it cannot install from the app. Run the command instead.", action: "check" },
  "already-installed": { message: "This integration is already installed. Restart the server to use it.", action: "check" },
  "no-requirements": { message: "This integration adds no packages, so there is nothing to install.", action: "check" },
  "editor-running": { message: EDITOR_RUNNING, action: "check" },
};

/** The lines of a refused tool install. A tool lives in its own uv tool environment, so it needs no restart. */
const TOOL_REFUSALS: Record<string, { message: string; action: RefusalAction }> = {
  ...REFUSALS,
  "already-installed": { message: "This tool is already installed. It needs no restart.", action: "check" },
};

/** One line and one action for each `reason` of a refused uninstall (409). `in-use` names its setting separately. */
const UNINSTALL_REFUSALS: Record<string, { message: string; action: RefusalAction }> = {
  "install-running": { message: "Another install or uninstall is running. Wait for it to finish, then try again.", action: "retry" },
  "not-uninstallable-here": { message: "This integration cannot be uninstalled from the app.", action: "check" },
  "not-installed": { message: "This integration is not installed now, so there is nothing to uninstall.", action: "check" },
  "nothing-to-remove": { message: "Other installed packages need every package of this extra, so the app cannot remove it.", action: "check" },
  "in-use": { message: "A setting uses this extra. Change that setting before you uninstall it.", action: "check" },
  "not-uv-tool": { message: "This server was not installed with uv tool, so it cannot uninstall from the app.", action: "check" },
  "uv-not-found": { message: "The server cannot find uv, so it cannot uninstall from the app.", action: "check" },
  "editor-running": { message: EDITOR_RUNNING, action: "check" },
  "not-installed-by-app": {
    message: "This marimo was not installed from this card, so the app does not remove it. Use the command on the card in a terminal.",
    action: "check",
  },
};

/** The line for a setting that still uses the extra, such as `vector_store`. */
export function inUseMessage(setting: string): string {
  return `${setting} uses this extra. Change that setting before you uninstall it.`;
}

/** The line for a saved user profile that still uses the extra. */
export function profileInUseMessage(title: string, setting: string): string {
  return `The profile ${title} uses this extra through ${setting}. Change it in Studio before you uninstall it.`;
}

/** The `profile` title of a 409 refusal body, or `null`. */
function refusalProfile(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.kind !== "http" || error.status !== 409) return null;
  const body = error.body;
  if (typeof body !== "object" || body === null) return null;
  const profile = (body as Record<string, unknown>).profile;
  if (typeof profile !== "object" || profile === null) return null;
  const title = (profile as Record<string, unknown>).title;
  return typeof title === "string" ? title : null;
}

/** The body field `key` of a 409 refusal, or `null` for any other failure. */
function refusalField(error: unknown, key: "reason" | "setting"): string | null {
  if (!(error instanceof ApiError) || error.kind !== "http" || error.status !== 409) return null;
  const body = error.body;
  if (typeof body !== "object" || body === null) return null;
  const value = (body as Record<string, unknown>)[key];
  return typeof value === "string" ? value : null;
}

const REFUSAL_LINES = { install: REFUSALS, "tool-install": TOOL_REFUSALS, uninstall: UNINSTALL_REFUSALS };

function knownRefusal(error: unknown, action: RefusalKind): { message: string; action: RefusalAction } | undefined {
  const reason = refusalField(error, "reason");
  if (reason === null) return undefined;
  const refusal = REFUSAL_LINES[action][reason];
  const setting = refusalField(error, "setting");
  const profile = refusalProfile(error);
  if (refusal !== undefined && reason === "in-use" && setting !== null && profile !== null) return { ...refusal, message: profileInUseMessage(profile, setting) };
  if (refusal !== undefined && reason === "in-use" && setting !== null) return { ...refusal, message: inUseMessage(setting) };
  return refusal;
}

interface InstallRefusalProps {
  error: unknown;
  /** Sends the install again. */
  onRetry: () => void;
  /** Reads the catalogue again, so the entry shows what the server can do now. */
  onCheck: () => void;
  /** Which start was refused. It picks the lines. */
  action?: RefusalKind;
}

/**
 * A refused install or uninstall as one friendly line and one action. A known 409 reason
 * gets its own line; anything else falls back to `describeError`. The raw
 * message goes to the console only.
 */
export function InstallRefusal({ error, onRetry, onCheck, action = "install" }: InstallRefusalProps) {
  const known = useMemo(() => {
    const refusal = knownRefusal(error, action);
    if (refusal !== undefined) console.error(error instanceof Error ? error.message : String(error), error);
    return refusal;
  }, [error, action]);

  if (known === undefined) return <ErrorNotice error={error} onRetry={onRetry} />;
  return (
    <AlertNotice message={known.message}>
      {known.action === "retry" ? (
        <Button type="button" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      ) : (
        <Button type="button" variant="outline" onClick={onCheck}>
          Check again
        </Button>
      )}
    </AlertNotice>
  );
}
