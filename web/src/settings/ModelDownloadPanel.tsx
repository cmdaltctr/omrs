import { useState } from "react";
import { ApiError } from "../api/client";
import type { ModelSearchResult, ModelSource, StartModelDownload } from "../api/modelDownloads";
import { AlertNotice } from "../components/AlertNotice";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { ModelDownloadDone } from "./ModelDownloadDone";
import { ModelDownloadProgress } from "./ModelDownloadProgress";
import { ModelFileList } from "./ModelFileList";
import { ModelSearchField } from "./ModelSearchField";
import { reasonFromBody, REASON_SENTENCES } from "./modelDownloadWords";
import { useCancelModelDownload, useModelDownload, useStartModelDownload } from "./useModelDownload";

const INTRO: Record<ModelSource, string> = {
  "huggingface-gguf": "Search Hugging Face for a GGUF model. The file goes to the Hugging Face cache on this machine.",
  "ollama-pull": "Search the Ollama library and Hugging Face. Ollama keeps the model in its own store.",
};

/** The Hugging Face repo `org/name` of a result, or `null` for a built-in Ollama name that is pulled by name. */
function repoOf(result: ModelSearchResult): string | null {
  if (result.source === "ollama-library") return null;
  return result.id.replace(/^hf\.co\//, "");
}

/** The "Get a model" block of a provider card: search, pick a file, download, then the next step. */
export function ModelDownloadPanel({ provider, source }: { provider: string; source: ModelSource }) {
  const titleId = `get-model-${provider}`;
  const status = useModelDownload();
  const start = useStartModelDownload();
  const cancel = useCancelModelDownload();
  const [chosen, setChosen] = useState<ModelSearchResult | null>(null);
  const current = status.data;
  const running = current?.state === "running";
  // The job is one for the whole server. This card shows it only when it belongs to this provider.
  const mine = current !== undefined && current.provider === provider ? current : null;
  const repo = chosen === null ? null : repoOf(chosen);
  const begin = (request: StartModelDownload) => start.mutate(request);
  const refusal = start.error instanceof ApiError ? reasonFromBody(start.error.body) : null;

  return (
    <div role="group" aria-labelledby={titleId} className="flex min-w-0 flex-col gap-2">
      <h4 id={titleId} className="text-ui font-semibold">
        Get a model
      </h4>
      <p className="text-meta text-muted-foreground">{INTRO[source]}</p>
      <ModelSearchField provider={provider} selectedId={chosen?.id ?? null} onChoose={setChosen} />
      {chosen !== null && repo !== null ? <ModelFileList key={repo} provider={provider} repo={repo} source={source} disabled={running || start.isPending} onStart={begin} /> : null}
      {chosen !== null && repo === null ? (
        <div className="flex flex-wrap items-center gap-2">
          <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
            {chosen.id}
          </code>
          <span className="text-meta text-muted-foreground">Ollama pulls the latest tag of this name.</span>
          <Button type="button" size="sm" disabled={running || start.isPending} onClick={() => begin({ provider, name: chosen.id })}>
            Download
          </Button>
        </div>
      ) : null}
      {current?.state === "running" && mine === null ? <p className="text-meta text-muted-foreground">{REASON_SENTENCES.busy}</p> : null}
      {start.isError && refusal !== null ? <AlertNotice message={REASON_SENTENCES[refusal]} /> : null}
      {start.isError && refusal === null ? <ErrorNotice error={start.error} onRetry={() => start.reset()} /> : null}
      {status.isError ? <ErrorNotice error={status.error} onRetry={() => void status.refetch()} /> : null}
      {mine !== null ? <ModelDownloadProgress status={mine} cancelling={cancel.isPending} onCancel={() => cancel.mutate()} /> : null}
      {mine !== null ? <ModelDownloadDone status={mine} /> : null}
    </div>
  );
}
