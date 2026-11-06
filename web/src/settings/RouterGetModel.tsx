import type { LlamacppRouterStatus, RouterModel } from "../api/llamacppRouter";
import { AlertNotice } from "../components/AlertNotice";
import { Button } from "../components/ui/button";
import { LlamacppUseModel } from "./LlamacppUseModel";
import { ModelDownloadProgress } from "./ModelDownloadProgress";
import { useCancelModelDownload, useModelDownload } from "./useModelDownload";
import { useGetModel } from "./useGetModel";

/**
 * "Get this model" for a router list entry that has no file: the button, then
 * progress with Cancel, a refusal in plain words and, when the file arrived,
 * Use this model for the entry. One download job runs at a time, so the
 * progress shows only while the job is about this entry.
 */
export function RouterGetModel({ entry, router }: { entry: RouterModel; router: LlamacppRouterStatus }) {
  const { get, pending, problem } = useGetModel();
  const cancel = useCancelModelDownload();
  const job = useModelDownload().data;
  const mine = job !== undefined && job.provider === "llamacpp" && job.model === entry.model ? job : null;
  if (entry.file !== null) return null;
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div>
        <Button type="button" size="sm" variant="outline" aria-label={`Get this model ${entry.model}`} disabled={pending || mine?.state === "running"} onClick={() => void get(entry.model)}>
          Get this model
        </Button>
      </div>
      {problem !== null ? <AlertNotice message={problem} /> : null}
      {mine !== null && mine.state !== "succeeded" ? <ModelDownloadProgress status={mine} cancelling={cancel.isPending} onCancel={() => cancel.mutate()} /> : null}
      {mine !== null && mine.state === "succeeded" ? <LlamacppUseModel status={mine} router={router} target={entry.id} /> : null}
    </div>
  );
}
