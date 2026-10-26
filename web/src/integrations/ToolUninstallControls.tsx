import { Trash2 } from "lucide-react";
import { useState } from "react";
import type { ExternalTool } from "../api/integrations";
import { Button } from "../components/ui/button";
import { FailedJob } from "./InstallControls";
import { EDITOR_RUNNING, InstallRefusal } from "./InstallRefusal";
import { ToolUninstallDialog } from "./ToolDialogs";
import { TOOL_FAILURE, ToolProgress, type ToolPhase } from "./ToolInstallControls";
import type { InstallControl } from "./useIntegrationInstall";

/** The uninstall phase of a tool. It reads only an uninstall job of this tool, never an extras job (design D9). */
export function toolUninstallPhase(tool: ExternalTool, control: InstallControl): ToolPhase {
  const job = control.install;
  const mine = job?.tool === tool.id && job.action === "uninstall";
  if ((mine && job.state === "running") || control.toolUninstalling === tool.id) return "running";
  if (mine && job.state === "failed") return "failed";
  // The server checks the receipt before `install-running` and `editor-running`, so these keep a card-installed tool.
  return tool.uninstallable || tool.uninstall_reason === "install-running" || tool.uninstall_reason === "editor-running" ? "ready" : "none";
}

/** The Uninstall button, its confirm dialog, the progress line and the failure output of a tool the card installed. */
export function ToolUninstallControls({ tool, control, phase }: { tool: ExternalTool; control: InstallControl; phase: ToolPhase }) {
  const [confirming, setConfirming] = useState(false);
  const error = control.toolUninstallRefusal(tool.id);
  const uninstall = () => control.uninstallTool(tool.id);
  const refusal = error !== null ? <InstallRefusal action="uninstall" error={error} onRetry={uninstall} onCheck={control.recheck} /> : null;

  if (phase === "none") return null;
  if (phase === "running") return <ToolProgress text={`Uninstalling ${tool.name}. This can take a minute.`} />;
  if (phase === "failed" && control.install !== undefined) {
    return (
      <>
        <FailedJob name={tool.name} install={control.install} action="uninstall" busy={control.busy} onRetry={uninstall} lines={TOOL_FAILURE.uninstall} />
        {refusal}
      </>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label={`Uninstall ${tool.name}`}
          disabled={control.busy || !tool.uninstallable}
          onClick={() => setConfirming(true)}
        >
          <Trash2 aria-hidden="true" />
          Uninstall
        </Button>
      </div>
      {tool.uninstall_reason === "editor-running" && error === null && tool.install_reason !== "editor-running" ? (
        <p className="text-meta text-muted-foreground">{EDITOR_RUNNING}</p>
      ) : null}
      {refusal}
      <ToolUninstallDialog
        tool={tool}
        open={confirming}
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          uninstall();
        }}
      />
    </div>
  );
}
