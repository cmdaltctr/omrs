import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { getLlamacppRouterDownloads, type RouterDownloadsNeeded } from "../api/llamacppRouter";
import { useStartLlamacppRouter } from "../api/llamacppRouterHooks";
import { RouterStartDialog } from "./RouterStartDialog";

/**
 * The Start button's action. It first asks the server which listed models have no file. With none missing it
 * starts the router; otherwise it opens one dialog with the models and the size, and starts only after Download.
 * The server reads the model host for the sizes only when this runs, never at a status read.
 *
 * It has the shape of a mutation (`mutate`, `isPending`, `isError`, `error`, `reset`), plus the `dialog` element
 * that the caller renders once.
 */
export function useRouterStartFlow() {
  const api = useApi();
  const start = useStartLlamacppRouter();
  const [needed, setNeeded] = useState<RouterDownloadsNeeded | null>(null);
  const check = useMutation({
    mutationFn: () => getLlamacppRouterDownloads(api),
    onSuccess: (found) => (found.models.length === 0 ? start.mutate() : setNeeded(found)),
  });
  return {
    mutate: () => {
      start.reset();
      check.mutate();
    },
    isPending: check.isPending || start.isPending,
    isError: check.isError || start.isError,
    error: check.isError ? check.error : start.error,
    reset: () => {
      check.reset();
      start.reset();
    },
    dialog: (
      <RouterStartDialog
        needed={needed}
        onDownload={() => {
          setNeeded(null);
          start.mutate();
        }}
        onCancel={() => setNeeded(null)}
      />
    ),
  };
}
