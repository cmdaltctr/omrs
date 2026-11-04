import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { useModelRuntimes } from "../api/modelRuntimesHooks";
import { sessionQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { formatRoute } from "../lib/routes";
import { ServerCallout } from "../settings/ServerCallout";
import { EntryList } from "./EntryList";
import { ModelRuntimeRow } from "./ModelRuntimeRow";
import { SectionFrame } from "./SectionFrame";

const PROVIDERS = formatRoute({ area: "settings", section: "providers" });
const SUMMARY = "The local model servers that Chat, embeddings and OCR use. OMRS starts and stops a managed server. It never stops an external one.";

/**
 * Model runtimes: one row for each local runtime in force. The list comes
 * from `GET /v1/runtimes`. A managed runtime that runs has a Stop button for
 * a session with `manage`; the button waits for the session read, so a
 * session without the scope never sees a live control.
 */
export function ModelRuntimesSection() {
  const runtimes = useModelRuntimes();
  const session = useQuery(sessionQuery(useApi()));
  const mayManage = session.data?.scopes.includes("manage") === true;
  const list = runtimes.data;
  return (
    <SectionFrame id="integrations-model-runtimes" title="Model runtimes" lines={[SUMMARY]}>
      <ServerCallout
        text={
          <>
            Who runs the Chat server is chosen on the llama.cpp card in{" "}
            <a href={PROVIDERS} className="underline underline-offset-4">
              Settings › Providers
            </a>
            , where you can also start OMRS&apos;s own server. The embeddings and OCR runtimes are set in the environment, .env or omrs.jsonc.
          </>
        }
      />
      {list === undefined ? (
        runtimes.isError ? (
          <ErrorNotice error={runtimes.error} onRetry={() => void runtimes.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading model runtimes.
          </p>
        )
      ) : list.length === 0 ? (
        <p className="text-meta text-muted-foreground">No local model runtime is in force.</p>
      ) : (
        <EntryList label="Model runtimes">
          {list.map((item) => (
            <ModelRuntimeRow key={item.id} item={item} mayManage={mayManage} />
          ))}
        </EntryList>
      )}
    </SectionFrame>
  );
}
