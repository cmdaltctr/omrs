import { AlertNotice } from "../components/AlertNotice";
import { Button } from "../components/ui/button";
import type { ModelDownloadStatus } from "../api/modelDownloads";
import { ALREADY_CACHED_LINE, bytesLine, CANCELLED_LINE, percentDone, REASON_SENTENCES, SIZE_UNKNOWN_LINE } from "./modelDownloadWords";

interface ModelDownloadProgressProps {
  status: ModelDownloadStatus;
  onCancel: () => void;
  /** True while the cancel request is in flight. */
  cancelling: boolean;
}

/** The running download (bar, bytes, Cancel), or the one line that tells how a finished one ended. */
export function ModelDownloadProgress({ status, onCancel, cancelling }: ModelDownloadProgressProps) {
  const model = status.model ?? "the model";

  if (status.state === "failed") {
    return <AlertNotice message={REASON_SENTENCES[status.reason ?? "failed"]} />;
  }
  if (status.state === "cancelled") {
    return (
      <p role="status" className="text-ui">
        {CANCELLED_LINE}
      </p>
    );
  }
  if (status.state !== "running") return null;

  const percent = percentDone(status);
  return (
    <div className="flex flex-col gap-2">
      <p className="text-ui">
        {"Downloading "}
        <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
          {model}
        </code>
      </p>
      <div
        role="progressbar"
        aria-label="Download progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent ?? undefined}
        className="h-2 w-full overflow-hidden rounded-small border border-border-hover bg-border"
      >
        <div className="h-full bg-primary-tint-active transition-[width] duration-300 motion-reduce:transition-none" style={{ width: `${percent ?? 0}%` }} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-meta text-muted-foreground">{status.bytes_total === null ? SIZE_UNKNOWN_LINE : status.bytes_total === 0 ? ALREADY_CACHED_LINE : bytesLine(status.bytes_done, status.bytes_total)}</p>
        <Button type="button" size="sm" variant="outline" disabled={cancelling} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
