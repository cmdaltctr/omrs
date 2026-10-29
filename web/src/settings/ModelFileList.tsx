import { useState } from "react";
import { ApiError } from "../api/client";
import type { ModelFileEntry, ModelSource, StartModelDownload } from "../api/modelDownloads";
import { AlertNotice } from "../components/AlertNotice";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { formatBytes, REASON_SENTENCES } from "./modelDownloadWords";
import { useModelFiles } from "./useModelDownload";

interface ModelFileListProps {
  provider: string;
  /** The Hugging Face repo `org/name`. */
  repo: string;
  source: ModelSource;
  /** True while another download runs. */
  disabled: boolean;
  onStart: (request: StartModelDownload) => void;
}

function EntryRow({ entry, group, checked, onPick }: { entry: ModelFileEntry; group: string; checked: boolean; onPick: () => void }) {
  return (
    <label className="flex flex-wrap items-center gap-2 text-ui">
      <input type="radio" name={group} checked={checked} className="size-4 accent-primary" onChange={onPick} />
      <code className="text-code font-mono">{entry.label}</code>
      <span className="text-meta text-muted-foreground">{formatBytes(entry.size_bytes)}</span>
      {entry.recommended ? <Badge variant="accent">Recommended</Badge> : null}
      {entry.closest_to_full ? <Badge variant="info">closest to full quality</Badge> : null}
    </label>
  );
}

/** The quantisation labels of one repo with their sizes. The recommended label is preselected. */
export function ModelFileList({ provider, repo, source, disabled, onStart }: ModelFileListProps) {
  const query = useModelFiles(provider, repo);
  const [picked, setPicked] = useState<string | null>(null);
  const list = query.data;

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return notFound ? <AlertNotice message={REASON_SENTENCES["not-found"]} /> : <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (list === undefined) return <p className="text-meta text-muted-foreground">Reading the file list.</p>;
  if (list.reason === "network" || list.revision === null) return <p role="status" className="text-ui">{REASON_SENTENCES.network}</p>;

  const label = picked ?? list.entries.find((entry) => entry.recommended)?.label ?? list.entries[0]?.label;
  const start = () => {
    if (label === undefined) return;
    onStart(source === "huggingface-gguf" ? { provider, repo, revision: list.revision!, label } : { provider, repo, label });
  };

  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className="flex flex-wrap items-center gap-2 text-ui">
        <span>{"Files in "}</span>
        <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
          {repo}
        </code>
        {list.gated ? <Badge variant="warning">Gated</Badge> : null}
      </legend>
      {list.gated ? <p className="text-meta text-muted-foreground">This model needs a Hugging Face access token (HF_TOKEN) to download.</p> : null}
      {list.entries.map((entry) => (
        <EntryRow key={entry.label} entry={entry} group={`quant-${provider}-${repo}`} checked={entry.label === label} onPick={() => setPicked(entry.label)} />
      ))}
      <div>
        <Button type="button" size="sm" disabled={disabled || label === undefined} onClick={start}>
          Download
        </Button>
      </div>
    </fieldset>
  );
}
