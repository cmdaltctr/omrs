import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { useRestartLlamacppServer } from "../api/llamacppServerHooks";
import type { LlamacppServerStatus } from "../api/llamacppServer";
import { sessionQuery } from "../api/queries";
import { useSetChatSettings } from "../api/settingsMutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { NEEDS_CREDENTIALS } from "./LlamacppServerFields";
import { NEED_RESTART_LINE } from "./modelDownloadWords";

/**
 * Use this model, while OMRS runs the Chat server. It saves the model value as
 * the llama.cpp Chat model through the Chat save, which OMRS's own server
 * loads, then offers the existing Restart. While OMRS runs the server that
 * save needs the `credentials` scope, so a session without it sees the refusal
 * and no request goes out.
 */
export function LlamacppUseModel({ modelValue, server }: { modelValue: string; server: LlamacppServerStatus }) {
  const save = useSetChatSettings();
  const restart = useRestartLlamacppServer();
  const session = useQuery(sessionQuery(useApi()));
  // The button waits for the session read, so a person without the scope never gets a live button.
  const hasCredentials = session.data?.scopes.includes("credentials") === true;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" disabled={!hasCredentials || save.isPending} onClick={() => save.mutate({ provider: "llamacpp", model: modelValue })}>
          Use this model
        </Button>
        {!session.isPending && !hasCredentials ? <p className="text-meta text-muted-foreground">{NEEDS_CREDENTIALS}</p> : null}
      </div>
      {save.isError ? <ErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
      {save.isSuccess ? (
        <div className="flex flex-wrap items-center gap-2">
          <p role="status" className="text-ui">
            {NEED_RESTART_LINE}
          </p>
          <Button type="button" size="sm" variant="outline" disabled={server.state !== "running" || restart.isPending} onClick={() => restart.mutate(undefined, { onSuccess: () => save.reset() })}>
            Restart server to load it
          </Button>
        </div>
      ) : null}
      {restart.isError ? <ErrorNotice error={restart.error} onRetry={() => restart.reset()} /> : null}
    </div>
  );
}
