import { useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Square } from "lucide-react";
import { useState } from "react";
import { modelRuntimesKey, useStopModelRuntime } from "../api/modelRuntimesHooks";
import type { ModelRuntime } from "../api/modelRuntimes";
import { ApiError } from "../api/client";
import { AlertNotice } from "../components/AlertNotice";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { useReturnFocus } from "../studio/useReturnFocus";

/** Shown when the server refuses a stop with 409 `external-runtime`: the list was out of date. */
const EXTERNAL = "This runtime is an external server. OMRS does not stop it.";

function isExternalRefusal(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.kind !== "http" || error.status !== 409) return false;
  return (error.body as { reason?: unknown } | null | undefined)?.reason === "external-runtime";
}

/** What a stop costs the other process, by runtime: OCR falls back, the router's models stay unreachable until a start. */
function consequence(item: ModelRuntime): string {
  return item.role === "ocr" ? "OCR uses the fallback engine." : "Requests for the router's models fail until it starts again.";
}

/**
 * The Stop button of one managed runtime. When another OMRS process uses the
 * runtime, it asks first: a stop fails the requests in progress and then
 * costs that process what `consequence` says. This process alone does not ask.
 */
export function StopRuntime({ item, title }: { item: ModelRuntime; title: string }) {
  const [confirming, setConfirming] = useState(false);
  const stop = useStopModelRuntime();
  const queryClient = useQueryClient();
  const returnFocus = useReturnFocus();

  const send = () => {
    setConfirming(false);
    stop.mutate(item.id);
  };

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div>
        <Button type="button" variant="outline" size="sm" aria-label={`Stop ${title}`} disabled={stop.isPending} onClick={() => (item.other_clients === "some" ? setConfirming(true) : send())}>
          {stop.isPending ? <LoaderCircle aria-hidden="true" className="motion-safe:animate-spin" /> : <Square aria-hidden="true" />}
          Stop
        </Button>
      </div>
      {stop.isError ? (
        isExternalRefusal(stop.error) ? (
          <AlertNotice message={EXTERNAL}>
            <Button type="button" variant="outline" onClick={() => void queryClient.invalidateQueries({ queryKey: modelRuntimesKey }).then(() => stop.reset())}>
              Refresh the list
            </Button>
          </AlertNotice>
        ) : (
          <ErrorNotice error={stop.error} onRetry={() => stop.mutate(item.id)} />
        )
      ) : null}
      <Dialog open={confirming} onOpenChange={(next) => (next ? undefined : setConfirming(false))}>
        <DialogContent {...returnFocus}>
          <DialogHeader>
            <DialogTitle>{`Stop ${title}?`}</DialogTitle>
            <DialogDescription>{`Another OMRS process uses this runtime. Requests in progress fail. ${consequence(item)}`}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button type="button" variant="destructive" onClick={send}>
              Stop runtime
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
