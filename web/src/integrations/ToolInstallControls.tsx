import { Download, LoaderCircle } from "lucide-react";
import { useState } from "react";
import type { ExternalTool, InstallAction } from "../api/integrations";
import { Button } from "../components/ui/button";
import { FailedJob, type FailureLines } from "./InstallControls";
import { EDITOR_RUNNING, InstallRefusal } from "./InstallRefusal";
import { ToolInstallDialog } from "./ToolDialogs";
import type { InstallControl } from "./useIntegrationInstall";

/** The failure lines of a tool job. A tool job has no `uv pip check`: `check-failed` means the tool is not in the state the job asked for. */
export const TOOL_FAILURE: Record<InstallAction, FailureLines> = {
  install: {
    "exit-code": "The install failed. The last output lines are below.",
    "check-failed": "uv finished, but the marimo tool environment is still not ready. Read the output below, or run the command in a terminal.",
    "timed-out": "The install stopped after 10 minutes. The last output lines are below.",
    "start-failed": "The install could not start.",
  },
  uninstall: {
    "exit-code": "The uninstall failed. The last output lines are below.",
    "check-failed": "uv finished, but the marimo tool environment is still there. Read the output below, or run the command in a terminal.",
    "timed-out": "The uninstall stopped after 10 minutes. The last output lines are below.",
    "start-failed": "The uninstall could not start.",
  },
};

export type ToolPhase = "running" | "failed" | "ready" | "none";

/** The install phase of a tool. It reads only an install job of this tool, never an extras job (design D9). */
export function toolInstallPhase(tool: ExternalTool, control: InstallControl): ToolPhase {
  const job = control.install;
  const mine = job?.tool === tool.id && job.action === "install";
  if ((mine && job.state === "running") || control.toolStarting === tool.id) return "running";
  if (mine && job.state === "failed") return "failed";
  // While another job or a marimo editor runs, the button stays, disabled.
  return tool.installable || tool.install_reason === "install-running" || tool.install_reason === "editor-running" ? "ready" : "none";
}

/** The progress line of a running tool job. */
export function ToolProgress({ text }: { text: string }) {
  return (
    <p role="status" className="flex items-center gap-2 text-ui">
      <LoaderCircle aria-hidden="true" className="size-4 shrink-0 motion-safe:animate-spin" />
      <span className="min-w-0 [overflow-wrap:anywhere]">{text}</span>
    </p>
  );
}

/** The Install button, its confirm dialog, the progress line and the failure output of a tool. A tool needs no restart. */
export function ToolInstallControls({ tool, control, phase }: { tool: ExternalTool; control: InstallControl; phase: ToolPhase }) {
  const [confirming, setConfirming] = useState(false);
  const error = control.toolRefusal(tool.id);
  const start = () => control.startTool(tool.id);
  const refusal = error !== null ? <InstallRefusal error={error} onRetry={start} onCheck={control.recheck} action="tool-install" /> : null;

  if (phase === "none") return null;
  if (phase === "running") return <ToolProgress text={`Installing ${tool.name}. This can take a few minutes.`} />;
  if (phase === "failed" && control.install !== undefined) {
    return (
      <>
        <FailedJob name={tool.name} install={control.install} action="install" busy={control.busy} onRetry={start} lines={TOOL_FAILURE.install} />
        {refusal}
      </>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div>
        <Button type="button" size="sm" aria-label={`Install ${tool.name}`} disabled={control.busy || !tool.installable} onClick={() => setConfirming(true)}>
          <Download aria-hidden="true" />
          Install
        </Button>
      </div>
      {tool.install_reason === "editor-running" && error === null ? <p className="text-meta text-muted-foreground">{EDITOR_RUNNING}</p> : null}
      {refusal}
      <ToolInstallDialog
        tool={tool}
        open={confirming}
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          start();
        }}
      />
    </div>
  );
}
