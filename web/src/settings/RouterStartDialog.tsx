import type { RouterDownloadsNeeded } from "../api/llamacppRouter";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { useReturnFocus } from "../studio/useReturnFocus";
import { formatBytes } from "./modelDownloadWords";

/** "Download 2 models, 6.5 GiB?", or "Download 2 models?" while any size is unknown. */
export function downloadTitle(needed: RouterDownloadsNeeded): string {
  const count = needed.models.length;
  const what = `${count} ${count === 1 ? "model" : "models"}`;
  return needed.total_bytes === null ? `Download ${what}?` : `Download ${what}, ${formatBytes(needed.total_bytes)}?`;
}

/**
 * The question before a Start that has to download listed models. Download goes on with the Start;
 * Cancel starts nothing. It is open while `needed` is set.
 */
export function RouterStartDialog({ needed, onDownload, onCancel }: { needed: RouterDownloadsNeeded | null; onDownload: () => void; onCancel: () => void }) {
  const returnFocus = useReturnFocus();
  return (
    <Dialog open={needed !== null} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <DialogContent {...returnFocus}>
        {needed === null ? null : (
          <>
            <DialogHeader>
              <DialogTitle>{downloadTitle(needed)}</DialogTitle>
              <DialogDescription>
                {needed.total_bytes === null ? "The size is unknown. " : ""}
                OMRS downloads these models from Hugging Face into its cache, then starts the router.
              </DialogDescription>
            </DialogHeader>
            <ul className="flex flex-col gap-1 text-ui">
              {needed.models.map((item) => (
                <li key={item.id} className="flex flex-wrap justify-between gap-x-3">
                  <span className="min-w-0 break-all">{item.model}</span>
                  <span className="text-muted-foreground">{item.size_bytes === null ? "Size unknown" : formatBytes(item.size_bytes)}</span>
                </li>
              ))}
            </ul>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onCancel}>
                Cancel
              </Button>
              <Button type="button" onClick={onDownload}>
                Download
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
