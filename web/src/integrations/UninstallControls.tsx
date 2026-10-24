import { LoaderCircle, Trash2 } from "lucide-react";
import { useState } from "react";
import type { Integration } from "../api/integrations";
import { Button } from "../components/ui/button";
import { RestartDialog } from "../settings/RestartDialog";
import { CopyCommand } from "./CopyCommand";
import { FailedJob } from "./InstallControls";
import { InstallRefusal } from "./InstallRefusal";
import { UninstallDialog } from "./UninstallDialog";
import type { InstallControl } from "./useIntegrationInstall";

export type UninstallPhase = "removed" | "running" | "failed" | "ready" | "in-use" | "shared" | "none";

/** The uninstall phase of one entry, from the catalogue and the uninstall job of this launch. */
export function uninstallPhase(integration: Integration, control: InstallControl): UninstallPhase {
  const extra = integration.extra;
  if (extra === null || integration.base) return "none";
  const job = control.install;
  const mine = job?.extra === extra && job.action === "uninstall";
  // After a restart the catalogue says not installed, and the cached success must not hide that.
  if (mine && job.state === "succeeded" && integration.availability !== "not-installed") return "removed";
  if ((mine && job.state === "running") || control.uninstalling === extra) return "running";
  if (mine && job.state === "failed") return "failed";
  if (integration.uninstall_reason === "in-use") return "in-use";
  if (integration.uninstall_reason === "nothing-to-remove") return "shared";
  // While another job runs the server reports `install-running`; the button then stays, disabled.
  return integration.uninstallable || integration.uninstall_reason === "install-running" ? "ready" : "none";
}

/** True while the uninstall phase owns the card, so the install controls stay hidden. */
export function uninstallActive(phase: UninstallPhase): boolean {
  return phase === "removed" || phase === "running" || phase === "failed";
}

/** The reinstall command without this extra, when the uv tool receipt lists it. */
export function LastingUninstallCommand({ integration }: { integration: Integration }) {
  if (integration.lasting_uninstall_command === null) return null;
  return (
    <div className="flex min-w-0 flex-col gap-1 border-t border-border pt-3">
      <CopyCommand command={integration.lasting_uninstall_command} subject={integration.name} label="Copy reinstall command without" />
      <p className="text-meta text-muted-foreground">This command reinstalls OMRS without this extra, so a later reinstall does not add it back and the packages left behind go.</p>
    </div>
  );
}

interface UninstallControlsProps {
  integration: Integration;
  control: InstallControl;
  phase: UninstallPhase;
}

/** The Uninstall button, its confirm dialog, the progress line, the failure output, the in-use line and the Restart action of one entry. */
export function UninstallControls({ integration, control, phase }: UninstallControlsProps) {
  const [confirming, setConfirming] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const extra = integration.extra ?? "";
  const error = control.uninstallRefusal(extra);
  const refusal = error !== null ? <InstallRefusal action="uninstall" error={error} onRetry={() => control.uninstall(extra)} onCheck={control.recheck} /> : null;

  if (phase === "none") return null;
  if (phase === "in-use") {
    return (
      <p className="text-meta text-muted-foreground [overflow-wrap:anywhere]">
        {integration.uninstall_setting === null ? "A setting" : <code className="text-code">{integration.uninstall_setting}</code>}
        {" uses this extra. Change that setting before you uninstall it."}
      </p>
    );
  }
  if (phase === "shared") {
    // Every package stays because something else needs it, for example PyTorch's packages and lancedb.
    return (
      <p className="text-meta text-muted-foreground [overflow-wrap:anywhere]">
        {`Other installed packages need every package of this extra (${integration.keeps.join(", ")}), so the app cannot remove it.`}
      </p>
    );
  }
  if (phase === "removed") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-meta text-muted-foreground">Restart the server to finish the uninstall.</p>
        <Button type="button" variant="outline" size="sm" onClick={() => setRestarting(true)}>
          Restart
        </Button>
        <RestartDialog change={restarting ? integration.name : null} onLater={() => setRestarting(false)} />
      </div>
    );
  }
  if (phase === "running") {
    return (
      <p role="status" className="flex items-center gap-2 text-ui">
        <LoaderCircle aria-hidden="true" className="size-4 shrink-0 motion-safe:animate-spin" />
        <span className="min-w-0 [overflow-wrap:anywhere]">{`Uninstalling ${extra}. This can take a minute.`}</span>
      </p>
    );
  }
  if (phase === "failed" && control.install !== undefined) {
    return (
      <>
        <FailedJob integration={integration} install={control.install} action="uninstall" busy={control.busy} onRetry={() => control.uninstall(extra)} />
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
          aria-label={`Uninstall ${integration.name}`}
          disabled={control.busy || !integration.uninstallable}
          onClick={() => setConfirming(true)}
        >
          <Trash2 aria-hidden="true" />
          Uninstall
        </Button>
      </div>
      {refusal}
      <UninstallDialog
        integration={integration}
        open={confirming}
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          control.uninstall(extra);
        }}
      />
    </div>
  );
}
