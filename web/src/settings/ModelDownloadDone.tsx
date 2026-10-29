import { useLlamacppServer } from "../api/llamacppServerHooks";
import type { ModelDownloadStatus } from "../api/modelDownloads";
import { CardInset } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { LlamacppUseModel } from "./LlamacppUseModel";
import { ModelListLine } from "./ModelListLine";
import { EXTERNAL_SERVER_NOTE } from "./modelDownloadWords";
import { useProviderModels } from "./useModelDownload";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";

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
      <ModelListLine query={models} holder="Ollama" value={value} />
    </>
  );
}

/** A server that omrs does not run: name the folder, tell the person what to do, and read the server's list on request. */
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
      <div>
        <Button type="button" size="sm" variant="outline" disabled={models.isFetching} onClick={() => void models.refetch()}>
          Refresh models
        </Button>
      </div>
      <ModelListLine query={models} holder="Your server" value={value} />
    </>
  );
}

function LlamacppDone({ status, value }: { status: ModelDownloadStatus; value: string }) {
  const query = useLlamacppServer();
  const server = query.data;
  // Until the server state is read, the line alone shows. Then the choice cannot flip under the person's cursor.
  if (query.isPending) return <Downloaded status={status} />;
  // Only a server that omrs runs takes a saved model. Any other state is treated as the user's own server.
  if (server === undefined || (server.state !== "running" && server.state !== "starting")) return <ExternalServerDone status={status} value={value} />;
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
