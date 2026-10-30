import { useLlamacppServer } from "../api/llamacppServerHooks";
import type { ModelDownloadStatus } from "../api/modelDownloads";
import { CardInset } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { LlamacppUseModel } from "./LlamacppUseModel";
import { ModelListLine } from "./ModelListLine";
import { ErrorNotice } from "../components/ErrorNotice";
import { EXTERNAL_SERVER_NOTE, LLAMACPP_LIST_WORDS, OLLAMA_LIST_WORDS } from "./modelDownloadWords";
import { useProviderModels } from "./useModelDownload";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";

function RefreshModels({ models }: { models: ReturnType<typeof useProviderModels> }) {
  return (
    <div>
      <Button type="button" size="sm" variant="outline" disabled={models.isFetching} onClick={() => void models.refetch()}>
        Refresh models
      </Button>
    </div>
  );
}

function Downloaded({ status }: { status: ModelDownloadStatus }) {
  return (
    <p role="status" className="text-ui">
      {"Downloaded "}
      <code dir="ltr" className={CODE}>
        {status.model}
      </code>
      {"."}
    </p>
  );
}

/** Ollama keeps the model in its own store. The page reads Ollama's list again and says whether it holds the model. */
function OllamaDone({ status, value }: { status: ModelDownloadStatus; value: string }) {
  const models = useProviderModels("ollama", true);
  return (
    <>
      <Downloaded status={status} />
      <ModelListLine query={models} words={OLLAMA_LIST_WORDS} value={value} />
      <RefreshModels models={models} />
    </>
  );
}

/** A Chat server the user runs: name the folder, tell the person what to do, and read the server's list on request. */
function ExternalServerDone({ status, value }: { status: ModelDownloadStatus; value: string }) {
  const models = useProviderModels("llamacpp", false);
  return (
    <>
      <Downloaded status={status} />
      {status.cache_folder !== null ? (
        <p className="text-ui">
          {"The file is in "}
          <code dir="ltr" className={CODE}>
            {status.cache_folder}
          </code>
          {". If your server reads another cache folder, point it at this one."}
        </p>
      ) : null}
      <p className="text-ui">{EXTERNAL_SERVER_NOTE}</p>
      <RefreshModels models={models} />
      <ModelListLine query={models} words={LLAMACPP_LIST_WORDS} value={value} />
    </>
  );
}

function LlamacppDone({ status, value }: { status: ModelDownloadStatus; value: string }) {
  const query = useLlamacppServer();
  const server = query.data;
  // Until the server status is read, the line alone shows. Then the choice cannot flip under the person's cursor.
  if (query.isPending) return <Downloaded status={status} />;
  // A failed read says nothing about who runs the server, so show the error, not the own-server steps.
  if (query.isError)
    return (
      <>
        <Downloaded status={status} />
        <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
      </>
    );
  // The saved Chat server choice decides, not the server state: the state is `stopped` after every launch.
  if (server === undefined || server.saved.chat_server.value !== "managed") return <ExternalServerDone status={status} value={value} />;
  return (
    <>
      <Downloaded status={status} />
      <LlamacppUseModel modelValue={value} server={server} />
    </>
  );
}

/** What a finished download offers next. A provider other than Ollama and llama.cpp shows only the line. */
export function ModelDownloadDone({ status }: { status: ModelDownloadStatus }) {
  const value = status.model_value;
  if (status.state !== "succeeded" || value === null) return null;
  return (
    <CardInset>
      {status.provider === "ollama" ? <OllamaDone status={status} value={value} /> : null}
      {status.provider === "llamacpp" ? <LlamacppDone status={status} value={value} /> : null}
    </CardInset>
  );
}
