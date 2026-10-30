import { useQuery } from "@tanstack/react-query";
import { useId } from "react";
import { useApi } from "../api/ApiProvider";
import type { ChatServerChoice as Choice, LlamacppServerStatus } from "../api/llamacppServer";
import { useSaveLlamacppServer } from "../api/llamacppServerHooks";
import { sessionQuery } from "../api/queries";
import { CardInset } from "../components/ui/card";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { CALLOUTS, CHAT_SERVER_LABEL, CHOICE_NAMES } from "./chatServerWords";
import { sourceText } from "./connectionWords";
import { NEEDS_CREDENTIALS } from "./LlamacppServerFields";
import { CONFLICT_SENTENCES, conflictReason } from "./llamacppServerWords";
import { SaveErrorNotice } from "./SaveErrorNotice";
import { ServerCallout } from "./ServerCallout";

const META = "text-meta text-muted-foreground";
const CHOICES: Choice[] = ["external", "managed"];

/**
 * Who runs the llama.cpp Chat server, with the callout of the choice in force.
 * Picking an option saves it at once. A value from the environment or `.env`,
 * or a session without the `credentials` scope, makes the choice read-only.
 */
export function ChatServerChoice({ status }: { status: LlamacppServerStatus }) {
  const id = useId();
  const save = useSaveLlamacppServer();
  const session = useQuery(sessionQuery(useApi()));
  const field = status.saved.chat_server;
  const saved: Choice = field.value === "managed" ? "managed" : "external";
  // While a save is in flight the select shows the picked option; a refused save falls back to the saved one.
  const value = (save.isPending ? save.variables?.chat_server : null) ?? saved;
  // The select waits for the session read, so a person without the scope never gets a live control.
  const hasCredentials = session.data?.scopes.includes("credentials") === true;
  const reason = field.locked ? (field.lock_reason ?? "Read-only") : !session.isPending && !hasCredentials ? NEEDS_CREDENTIALS : null;
  const conflict = save.isError ? conflictReason(save.error) : null;

  return (
    <CardInset>
      <Label htmlFor={id}>{CHAT_SERVER_LABEL}</Label>
      <Select value={value} disabled={field.locked || !hasCredentials || save.isPending} onValueChange={(next) => save.mutate({ chat_server: next as Choice })}>
        <SelectTrigger id={id} className="max-w-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {CHOICES.map((choice) => (
            <SelectItem key={choice} value={choice}>
              {CHOICE_NAMES[choice]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className={META}>{sourceText(field.source)}</p>
      {reason !== null ? <p className={META}>{reason}</p> : null}
      <ServerCallout text={CALLOUTS[value]} />
      {conflict !== null ? (
        <p role="alert" className="text-ui text-status-error-label">
          {CONFLICT_SENTENCES[conflict]}
        </p>
      ) : null}
      {save.isError && conflict === null ? <SaveErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
    </CardInset>
  );
}
