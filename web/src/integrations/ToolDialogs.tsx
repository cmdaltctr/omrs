import type { ExternalTool } from "../api/integrations";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { useReturnFocus } from "../studio/useReturnFocus";
import { InstallCaution } from "./IntegrationCard";

interface ToolDialogProps {
  tool: ExternalTool;
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/** The command a tool dialog runs, in a block that wraps at any width. */
function Command({ text }: { text: string }) {
  return (
    <code dir="ltr" className="block min-w-0 rounded-small border border-border bg-muted px-2 py-1.5 text-code [overflow-wrap:anywhere]">
      {text}
    </code>
  );
}

/** Asks before a tool install. It names the command, says where the tool goes, and repeats the caution. */
export function ToolInstallDialog({ tool, open, onCancel, onConfirm }: ToolDialogProps) {
  const returnFocus = useReturnFocus();
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <DialogContent {...returnFocus}>
        <DialogHeader>
          <DialogTitle>{`Install ${tool.name}?`}</DialogTitle>
          <DialogDescription>
            {`This runs the command below. ${tool.name} goes into its own uv tool environment, outside OMRS. No restart is needed.`}
          </DialogDescription>
        </DialogHeader>
        <Command text={tool.install_command} />
        {tool.install_caution !== null ? <InstallCaution text={tool.install_caution} /> : null}
        <p className="text-meta text-muted-foreground">{`The install does not register ${tool.name}. You do that in Experiments, Code editor.`}</p>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" onClick={onConfirm}>
            Install
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Asks before a tool uninstall. It says that the whole tool environment goes and what happens to a registration. */
export function ToolUninstallDialog({ tool, open, onCancel, onConfirm }: ToolDialogProps) {
  const returnFocus = useReturnFocus();
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <DialogContent {...returnFocus}>
        <DialogHeader>
          <DialogTitle>{`Uninstall ${tool.name}?`}</DialogTitle>
          <DialogDescription>
            {`This runs the command below. The whole ${tool.name} tool environment goes, with every package in it.`}
          </DialogDescription>
        </DialogHeader>
        <Command text={tool.uninstall_command} />
        <p className="text-ui">{`A ${tool.name} registration in Experiments, Code editor then shows as unavailable.`}</p>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" onClick={onConfirm}>
            Uninstall
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
