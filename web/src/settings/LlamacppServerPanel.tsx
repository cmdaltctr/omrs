import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { SettingBox } from "./SettingBox";
import type { LlamacppServerStatus } from "../api/llamacppServer";
import { useRestartLlamacppServer, useStartLlamacppServer, useStopLlamacppServer } from "../api/llamacppServerHooks";
import { ChatModelRow } from "./ChatModelRow";
import { CALLOUTS } from "./chatServerWords";
import { LlamacppServerFields } from "./LlamacppServerFields";
import { PanelDisclosure } from "./PanelDisclosure";
import { CONFLICT_SENTENCES, conflictReason, SHARED_ADDRESS_WARNING, statusLine } from "./llamacppServerWords";
import { ServerCallout } from "./ServerCallout";

/**
 * The "Local server" block of the llama.cpp card, shown while OMRS runs the
 * Chat server: settings, the Chat model it loads, state and Start, Stop and Restart.
 * It starts closed with the state on its toggle row, and opens by itself while
 * the program is missing or the server failed.
 */
export function LlamacppServerPanel({ status }: { status: LlamacppServerStatus }) {
  const start = useStartLlamacppServer();
  const stop = useStopLlamacppServer();
  const restart = useRestartLlamacppServer();

  const busy = start.isPending || stop.isPending || restart.isPending;
  const live = status.state === "starting" || status.state === "running";
  const failure = [start, stop, restart].find((mutation) => mutation.isError);
  const conflict = failure === undefined ? null : conflictReason(failure.error);
  // The program callout repeats above the program path row until that path is usable.
  const needsProgram = status.saved.binary.value === "" || status.reason === "binary-invalid";
  // OMRS's own server loads the Chat model only while Chat uses llama.cpp.
  const chatModel = status.chat_model.provider === "llamacpp" ? status.chat_model.model : "";

  return (
    <PanelDisclosure
      titleId="llamacpp-server-title"
      title="Local server"
      level={5}
      summary={statusLine(status)}
      attention={needsProgram || status.state === "failed" || failure !== undefined}
    >
      <p className="text-meta text-muted-foreground">omrs starts and stops only this server. It never touches a server you started yourself.</p>
      {status.shared_with_classification ? <ServerCallout tone="warning" text={SHARED_ADDRESS_WARNING} /> : null}
      {needsProgram ? <ServerCallout text={CALLOUTS.managed} /> : null}
      <LlamacppServerFields saved={status.saved} />
      <ChatModelRow model={chatModel} />
      <SettingBox>
        <div role="status" className="text-ui">
          {statusLine(status)}
        </div>
        {live && status.pending_restart ? <p className="text-meta text-muted-foreground">Restart to apply</p> : null}
        <p className="text-meta text-muted-foreground">The embedding server is not managed here.</p>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={busy || live} onClick={() => start.mutate()}>
            Start
          </Button>
          <Button size="sm" variant="outline" disabled={busy || !live} onClick={() => stop.mutate()}>
            Stop
          </Button>
          <Button size="sm" variant="outline" disabled={busy || status.state !== "running"} onClick={() => restart.mutate()}>
            Restart
          </Button>
        </div>
      </SettingBox>
      {conflict !== null ? (
        <p role="alert" className="text-ui text-status-error-label">
          {CONFLICT_SENTENCES[conflict]}
        </p>
      ) : null}
      {failure !== undefined && conflict === null ? <ErrorNotice error={failure.error} onRetry={() => failure.reset()} /> : null}
    </PanelDisclosure>
  );
}
