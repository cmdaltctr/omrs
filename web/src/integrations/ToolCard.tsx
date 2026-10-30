import type { ExternalTool, ToolAvailability } from "../api/integrations";
import { Badge } from "../components/ui/badge";
import { formatRoute } from "../lib/routes";
import { CopyCommand } from "./CopyCommand";
import { EntryRow } from "./EntryList";
import { InstallCaution, integrationCardId } from "./IntegrationCard";
import { ToolInstallControls, toolInstallPhase } from "./ToolInstallControls";
import { ToolUninstallControls, toolUninstallPhase } from "./ToolUninstallControls";
import type { InstallControl } from "./useIntegrationInstall";

const STATUS: Record<ToolAvailability, { label: string; variant: "success" | "error" | "warning" }> = {
  ready: { label: "Installed", variant: "success" },
  "needs-jupytext": { label: "Needs jupytext", variant: "warning" },
  "outside-range": { label: "Outside tested range", variant: "warning" },
  "not-installed": { label: "Not installed", variant: "error" },
  unknown: { label: "Unknown", variant: "warning" },
};

const CODE_EDITOR = formatRoute({ area: "experiments", section: "code-editor" });

/** The installed version and executable path, and what the state means for the Library. */
function ToolDetails({ tool }: { tool: ExternalTool }) {
  return (
    <>
      {tool.availability === "unknown" && <p className="text-meta text-muted-foreground">{`The server could not check ${tool.name}. Run the command below in a terminal.`}</p>}
      {tool.availability === "needs-jupytext" && (
        <p className="text-ui [overflow-wrap:anywhere]">jupytext is missing from the marimo tool environment. The Library cannot convert analysis.py without it.</p>
      )}
      {tool.availability === "outside-range" && (
        <p className="text-ui [overflow-wrap:anywhere]">{`This ${tool.name} ${tool.version ?? ""} is outside the range that OMRS tested (${tool.requirement}).`}</p>
      )}
      {tool.version !== null && <p className="text-meta text-muted-foreground">{`Version ${tool.version}`}</p>}
      {tool.executable !== null && (
        <p className="min-w-0 text-meta text-muted-foreground">
          {"Executable: "}
          <code dir="ltr" className="text-code [overflow-wrap:anywhere]">
            {tool.executable}
          </code>
        </p>
      )}
    </>
  );
}

/** The next step after an install: register the tool, or recheck a registration that the install changed (design D4). */
function NextStep({ tool, justInstalled }: { tool: ExternalTool; justInstalled: boolean }) {
  if (tool.availability !== "ready") return null;
  const link = (
    <a href={CODE_EDITOR} className="text-primary-label underline underline-offset-4">
      Code editor
    </a>
  );
  if (tool.plugin_status === null) {
    return (
      <p className="text-ui">
        {`Register ${tool.name} in Experiments, `}
        {link}.
      </p>
    );
  }
  if (!justInstalled) return null;
  return (
    <p className="text-ui">
      {`Recheck ${tool.name} in `}
      {link}.
    </p>
  );
}

/** One external tool: name, status badge with its value as text, purpose, version and path, Install and Uninstall, and commands. */
export function ToolCard({ tool, control }: { tool: ExternalTool; control: InstallControl }) {
  const install = toolInstallPhase(tool, control);
  const uninstall = toolUninstallPhase(tool, control);
  const installActive = install === "running" || install === "failed";
  const uninstallActive = uninstall === "running" || uninstall === "failed";
  const job = control.install;
  const justInstalled = job?.tool === tool.id && job.action === "install" && job.state === "succeeded";
  const status = STATUS[tool.availability];
  return (
    <EntryRow
      id={integrationCardId(tool.id)}
      title={tool.name}
      badges={<Badge variant={status.variant}>{status.label}</Badge>}
      purpose={tool.purpose}
      details={
        <>
          <ToolDetails tool={tool} />
          <NextStep tool={tool} justInstalled={justInstalled} />
          {tool.install_caution !== null && install !== "running" && !uninstallActive && <InstallCaution text={tool.install_caution} />}
        </>
      }
      actions={
        <>
          {uninstallActive ? null : <ToolInstallControls tool={tool} control={control} phase={install} />}
          {installActive ? null : <ToolUninstallControls tool={tool} control={control} phase={uninstall} />}
          <CopyCommand command={tool.install_command} subject={tool.name} />
          {tool.uninstall_reason === "not-installed-by-app" && (
            <div className="flex min-w-0 flex-col gap-1 border-t border-border pt-3">
              <CopyCommand command={tool.uninstall_command} subject={tool.name} label="Copy uninstall command for" />
              <p className="text-meta text-muted-foreground">{`This ${tool.name} was not installed from this card, so the app does not remove it. To remove it, run this command in a terminal.`}</p>
            </div>
          )}
        </>
      }
    />
  );
}
