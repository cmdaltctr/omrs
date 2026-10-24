import type { Integration } from "../api/integrations";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { useReturnFocus } from "../studio/useReturnFocus";

function PackageList({ label, intro, names }: { label: string; intro: string; names: string[] }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 text-ui">
      <p>{intro}</p>
      <ul aria-label={label} className="flex flex-col gap-1">
        {names.map((name) => (
          <li key={name}>
            <code dir="ltr" className="text-code [overflow-wrap:anywhere]">
              {name}
            </code>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface UninstallDialogProps {
  integration: Integration;
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/** Asks before an uninstall. It lists the packages that go, the packages that stay, and what stays behind. */
export function UninstallDialog({ integration, open, onCancel, onConfirm }: UninstallDialogProps) {
  const returnFocus = useReturnFocus();
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <DialogContent {...returnFocus}>
        <DialogHeader>
          <DialogTitle>{`Uninstall ${integration.name}?`}</DialogTitle>
          <DialogDescription>
            {"This removes the "}
            <code className="text-code">{integration.extra}</code>
            {" extra from the server. The server needs a restart to finish."}
          </DialogDescription>
        </DialogHeader>
        {integration.removes.length > 0 ? <PackageList label="Packages to remove" intro="It removes these packages:" names={integration.removes} /> : null}
        {integration.keeps.length > 0 ? (
          <PackageList label="Packages to keep" intro="It keeps these packages, because something else needs them:" names={integration.keeps} />
        ) : null}
        <p className="text-meta text-muted-foreground">Packages that only these pulled in stay until you reinstall OMRS without this extra.</p>
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
