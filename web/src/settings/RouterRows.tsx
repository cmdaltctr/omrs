import { useId } from "react";
import type { LlamacppRouterStatus, RouterField, RouterMode } from "../api/llamacppRouter";
import { useSaveLlamacppRouter } from "../api/llamacppRouterHooks";
import { formatRoute } from "../lib/routes";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { sourceText } from "./connectionWords";
import { CONFLICT_SENTENCES, conflictReason, EXTERNAL_NOTE, LIMIT_HELP, MODE_LABEL, MODE_NAMES, NEEDS_CREDENTIALS } from "./llamacppRouterWords";
import { SaveErrorNotice } from "./SaveErrorNotice";
import { ServerCallout } from "./ServerCallout";
import { SettingBox } from "./SettingBox";
import { SettingRow } from "./SettingRow";
import { formatCount, wholeNumberIn } from "./validation";
import { useScopes } from "./useScopes";

const META = "text-meta text-muted-foreground";
const CODE = "text-code font-mono [overflow-wrap:anywhere]";
const MODES: RouterMode[] = ["managed", "external"];
const INTEGRATIONS_CARD = formatRoute({ area: "integrations", entry: "llamacpp" });

/** The reason a locked field gives, or `null`. */
const lockText = (field: RouterField) => (field.locked ? (field.lock_reason ?? "Read-only") : null);

type FieldName = "binary" | "router_url" | "models_max" | "memory_margin_mib";

/** One router field as a setting row. Use default sends `null`, which clears the saved value. */
function FieldRow({ field, name, readOnlyReason = null, note = null }: { field: RouterField; name: FieldName; readOnlyReason?: string | null; note?: string | null }) {
  const save = useSaveLlamacppRouter();
  const isNumber = field.kind === "int";
  const rule = field.min !== null && field.max !== null ? `Enter ${formatCount(field.min)} to ${formatCount(field.max)}.` : "Enter a whole number.";
  return (
    <SettingRow
      label={field.label}
      value={String(field.value)}
      shownValue={isNumber ? formatCount(Number(field.value)) : undefined}
      source={field.source}
      readOnlyReason={lockText(field) ?? readOnlyReason}
      note={note}
      inputType={isNumber ? "number" : "text"}
      min={field.min}
      max={field.max}
      validate={isNumber ? wholeNumberIn(field.min, field.max, rule) : undefined}
      pending={save.isPending}
      error={save.isError ? save.error : null}
      onSave={(text, done) => save.mutate({ [name]: isNumber ? Number(text) : text }, { onSuccess: done })}
      onClear={(done) => save.mutate({ [name]: null }, { onSuccess: done })}
      onRetry={() => save.reset()}
    />
  );
}

/** Who runs llama.cpp. Picking an option saves it at once; changing the mode needs `credentials`. */
function ModeRow({ status }: { status: LlamacppRouterStatus }) {
  const id = useId();
  const save = useSaveLlamacppRouter();
  const scopes = useScopes();
  const field = status.saved.router_server;
  const value = (save.isPending ? save.variables?.router_server : null) ?? status.mode;
  const missingScope = scopes.known && !scopes.has("credentials");
  const reason = lockText(field) ?? (missingScope ? NEEDS_CREDENTIALS : null);
  const conflict = save.isError ? conflictReason(save.error) : null;
  return (
    <SettingBox>
      <Label htmlFor={id}>{MODE_LABEL}</Label>
      <Select value={value} disabled={reason !== null || save.isPending} onValueChange={(next) => save.mutate({ router_server: next as RouterMode })}>
        <SelectTrigger id={id} className="max-w-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {MODES.map((mode) => (
            <SelectItem key={mode} value={mode}>
              {MODE_NAMES[mode]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className={META}>{sourceText(field.source)}</p>
      {reason !== null ? <p className={META}>{reason}</p> : null}
      {conflict !== null ? <p role="alert" className="text-ui text-status-error-label">{CONFLICT_SENTENCES[conflict]}</p> : null}
      {save.isError && conflict === null ? <SaveErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
    </SettingBox>
  );
}

/** The program in force, and where to get one when there is none. */
function ProgramNote({ status }: { status: LlamacppRouterStatus }) {
  const { path, source } = status.program;
  if (source === "none")
    return (
      <p className={META}>
        {"No program yet. "}
        <a href={INTEGRATIONS_CARD} className="text-primary-label underline underline-offset-4">
          Get llama.cpp
        </a>
        {" on the Integrations page, or set the program path."}
      </p>
    );
  return (
    <p className={META}>
      {"Program in force: "}
      <code dir="ltr" className={CODE}>
        {path}
      </code>
      {source === "provisioned" ? " (provisioned build)" : " (your path)"}
    </p>
  );
}

/** The mode, the router address, the program and the two router limits. The model table sits below them. */
export function RouterRows({ status }: { status: LlamacppRouterStatus }) {
  const scopes = useScopes();
  const { saved } = status;
  const noCredentials = scopes.known && !scopes.has("credentials") ? NEEDS_CREDENTIALS : null;
  const defaultOf = (field: RouterField, help: string) => `Default ${formatCount(Number(field.default))}. ${help}`;
  return (
    <>
      <ModeRow status={status} />
      <FieldRow field={saved.router_url} name="router_url" />
      {status.mode === "managed" ? (
        <>
          <FieldRow field={saved.binary} name="binary" readOnlyReason={noCredentials} />
          <ProgramNote status={status} />
          <FieldRow field={saved.models_max} name="models_max" note={defaultOf(saved.models_max, LIMIT_HELP.models_max)} />
          <FieldRow field={saved.memory_margin_mib} name="memory_margin_mib" note={defaultOf(saved.memory_margin_mib, LIMIT_HELP.memory_margin_mib)} />
        </>
      ) : (
        <ServerCallout text={EXTERNAL_NOTE} />
      )}
    </>
  );
}
