import { useLlamacppRouter, useRestartLlamacppRouter, useStartLlamacppRouter, useStopLlamacppRouter } from "../api/llamacppRouterHooks";
import type { LlamacppRouterStatus } from "../api/llamacppRouter";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { CONFLICT_SENTENCES, conflictReason, statusLine } from "./llamacppRouterWords";
import { PanelDisclosure } from "./PanelDisclosure";
import { RouterModelTable } from "./RouterModelTable";
import { RouterRows } from "./RouterRows";
import { SettingBox } from "./SettingBox";
import { useScopes } from "./useScopes";

/** State line and Start, Stop and Restart. They show only while OMRS runs the router. */
function RouterState({ status }: { status: LlamacppRouterStatus }) {
  const start = useStartLlamacppRouter();
  const stop = useStopLlamacppRouter();
  const restart = useRestartLlamacppRouter();
  const scopes = useScopes();
  const busy = start.isPending || stop.isPending || restart.isPending;
  const live = status.state === "starting" || status.state === "running";
  // A button waits for the session read, so a person without `manage` never gets a live one.
  const mayManage = scopes.has("manage");
  const failure = [start, stop, restart].find((mutation) => mutation.isError);
  const conflict = failure === undefined ? null : conflictReason(failure.error);
  return (
    <SettingBox>
      <div role="status" className="text-ui">
        {statusLine(status)}
      </div>
      {status.mode === "managed" ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={!mayManage || busy || live} onClick={() => start.mutate()}>
            Start
          </Button>
          <Button size="sm" variant="outline" disabled={!mayManage || busy || !live} onClick={() => stop.mutate()}>
            Stop
          </Button>
          <Button size="sm" variant="outline" disabled={!mayManage || busy || status.state !== "running"} onClick={() => restart.mutate()}>
            Restart
          </Button>
          {live && status.pending_restart ? <span className="text-meta text-muted-foreground">Restart to apply</span> : null}
        </div>
      ) : null}
      {conflict !== null ? (
        <p role="alert" className="text-ui text-status-error-label">
          {CONFLICT_SENTENCES[conflict]}
        </p>
      ) : null}
      {failure !== undefined && conflict === null ? <ErrorNotice error={failure.error} onRetry={() => failure.reset()} /> : null}
    </SettingBox>
  );
}

/**
 * The Router block of the llama.cpp card: who runs llama.cpp, the address, the
 * program, the two limits, the state with Start, Stop and Restart, and the
 * model table. It starts closed with the state on its toggle row, and opens by
 * itself while the program is missing or the router failed.
 */
export function LlamacppRouterPanel() {
  const query = useLlamacppRouter();
  const status = query.data;
  if (status === undefined)
    return query.isError ? (
      <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
    ) : (
      <p role="status" className="text-meta text-muted-foreground">
        Loading the router.
      </p>
    );
  const needsProgram = status.mode === "managed" && status.program.source === "none";
  return (
    <PanelDisclosure titleId="llamacpp-router-title" title="Router" level={4} summary={statusLine(status)} attention={needsProgram || status.state === "failed"}>
      <RouterRows status={status} />
      <RouterState status={status} />
      <RouterModelTable status={status} />
    </PanelDisclosure>
  );
}
