import { TriangleAlert } from "lucide-react";
import { Badge } from "../components/ui/badge";
import type { Integration, IntegrationAvailability, InstallType } from "../api/integrations";
import { CopyCommand } from "./CopyCommand";
import { EntryRow } from "./EntryList";
import { InstallControls, installPhase } from "./InstallControls";
import { LastingUninstallCommand, UninstallControls, uninstallActive, uninstallPhase } from "./UninstallControls";
import type { InstallControl } from "./useIntegrationInstall";

const STATUS: Record<IntegrationAvailability, { label: string; variant: "success" | "error" | "warning" | "info" }> = {
  available: { label: "Installed", variant: "success" },
  "not-installed": { label: "Not installed", variant: "error" },
  unknown: { label: "Unknown", variant: "warning" },
  "restart-needed": { label: "Installed, restart to use", variant: "info" },
};

/** An uninstall that succeeded in this launch: the catalogue says restart-needed, but nothing was installed. */
const REMOVED = { label: "Removed, restart to apply", variant: "info" } as const;

/** A red callout with the entry's install caution. It shows only while the entry is not installed yet. */
export function InstallCaution({ text }: { text: string }) {
  return (
    <div data-slot="install-caution" className="flex min-w-0 gap-2 rounded-panel border border-status-error bg-status-error/10 px-3 py-2">
      <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-status-error-label" />
      <p className="min-w-0 text-ui text-status-error-label [overflow-wrap:anywhere]">
        <strong>Before you install: </strong>
        {text}
      </p>
    </div>
  );
}

/** The DOM id of an entry's card, so a link such as `#/integrations/anthropic` can focus it. */
export function integrationCardId(id: string): string {
  return `integration-${id}`;
}

interface IntegrationCardProps {
  integration: Integration;
  installType: InstallType;
  control: InstallControl;
}

/** One catalogue entry as a row: name, status badge with its value as text, purpose, then Install and Uninstall actions and commands. */
export function IntegrationCard({ integration, installType, control }: IntegrationCardProps) {
  const phase = installPhase(integration, control);
  const uninstall = uninstallPhase(integration, control);
  const status = uninstall === "removed" ? REMOVED : STATUS[integration.availability];
  const caution = integration.install_caution !== null && phase !== "restart" && (integration.availability === "not-installed" || integration.availability === "unknown");
  return (
    <EntryRow
      id={integrationCardId(integration.id)}
      title={integration.name}
      badges={
        <>
          <Badge variant={status.variant}>{status.label}</Badge>
          {/* Every install already holds a base entry, so nobody installs it twice. */}
          {integration.base ? <Badge variant="neutral">Base default</Badge> : null}
        </>
      }
      purpose={integration.purpose}
      details={
        <>
          {integration.readiness !== undefined ? (
            // A module check alone never says "Ready": the server checks the address or the key reference.
            <p className={integration.readiness.ready ? "text-meta text-status-success-label" : "text-meta text-muted-foreground"}>{integration.readiness.line}</p>
          ) : null}
          {integration.availability === "unknown" && <p className="text-meta text-muted-foreground">The server could not check this integration.</p>}
          {caution && <InstallCaution text={integration.install_caution ?? ""} />}
        </>
      }
      actions={
        <>
          {uninstallActive(uninstall) ? null : <InstallControls integration={integration} control={control} />}
          <UninstallControls integration={integration} control={control} phase={uninstall} />
          {integration.install_command === null ? (
            <p className="text-meta text-muted-foreground">Always on. Nothing to install.</p>
          ) : (
            <>
              <CopyCommand command={integration.install_command} subject={integration.name} />
              {installType === "uv-tool" && <p className="text-meta text-muted-foreground">This command keeps the extra after a later reinstall.</p>}
              {integration.pip_command !== null && (
                <p className="text-meta text-muted-foreground">
                  With pip: <code className="text-code [overflow-wrap:anywhere]">{integration.pip_command}</code>
                </p>
              )}
            </>
          )}
          <LastingUninstallCommand integration={integration} />
        </>
      }
    />
  );
}
