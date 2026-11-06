import type { ModelRuntime, ModelRuntimeState, RuntimeModel } from "../api/modelRuntimes";
import { Badge } from "../components/ui/badge";
import { MODEL_STATE_NAMES, ROLE_NAMES } from "../settings/llamacppRouterWords";
import { formatBytes } from "../settings/modelDownloadWords";
import { EntryRow } from "./EntryList";
import { StopRuntime } from "./StopRuntime";

const STATE_LABELS: Record<ModelRuntimeState, string> = { running: "Running", starting: "Starting", stopped: "Stopped", failed: "Failed" };

const STATE_VARIANTS: Record<ModelRuntimeState, "success" | "info" | "neutral" | "error"> = {
  running: "success",
  starting: "info",
  stopped: "neutral",
  failed: "error",
};

const PURPOSES = {
  router: "Serves embeddings, classification and Chat for OMRS.",
  ocr: "Reads pages for an OCR engine.",
} as const;

/** Said on an external OCR row, because OMRS cannot check the model files of a server it did not start. */
export const EXTERNAL_OCR_NOTE = "External server. Model files are not checked.";

/** Said on a running managed row that no other OMRS process holds open. */
export const NO_CLIENT_NOTE = "Running, no OMRS process uses it";

/** `llama.cpp router` or `OCR: <engine folder name>`. */
export function runtimeTitle(item: ModelRuntime): string {
  return item.role === "router" ? "llama.cpp router" : `OCR: ${item.id.replace(/^ocr-/, "")}`;
}

/** The models of the router under its row, each with its roles, state and memory. */
function ModelLines({ models }: { models: RuntimeModel[] }) {
  if (models.length === 0) return null;
  return (
    <div role="group" aria-label="Models" className="flex min-w-0 flex-col gap-1.5 border-s border-border ps-3">
      {models.map((entry) => (
        <div key={entry.model} className="flex min-w-0 flex-col gap-0.5">
          <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
            {entry.model}
          </code>
          <p className="text-meta text-muted-foreground [overflow-wrap:anywhere]">
            {[entry.roles.length === 0 ? "No role" : entry.roles.map((role) => ROLE_NAMES[role]).join(", "), MODEL_STATE_NAMES[entry.state], entry.memory_bytes === null ? null : formatBytes(entry.memory_bytes)]
              .filter((part) => part !== null)
              .join(", ")}
          </p>
        </div>
      ))}
    </div>
  );
}

/** Stop shows for a managed runtime that runs or starts, and only when the session may manage. */
function canStop(item: ModelRuntime, mayManage: boolean): boolean {
  return mayManage && item.mode === "managed" && (item.state === "running" || item.state === "starting");
}

/** One runtime as a row: title with mode and status badges, role line, reason, notes, address, memory and users; Stop on the right. */
export function ModelRuntimeRow({ item, mayManage }: { item: ModelRuntime; mayManage: boolean }) {
  const title = runtimeTitle(item);
  const externalOcr = item.role === "ocr" && item.mode === "external" && !item.files_checked;
  const unused = item.mode === "managed" && item.state === "running" && item.clients === "none";
  return (
    <EntryRow
      title={title}
      badges={
        <>
          <Badge>{item.mode === "managed" ? "Managed" : "External"}</Badge>
          <Badge variant={STATE_VARIANTS[item.state]}>{STATE_LABELS[item.state]}</Badge>
        </>
      }
      purpose={PURPOSES[item.role]}
      details={
        <>
          {item.reason_text !== null ? <p className="text-ui [overflow-wrap:anywhere]">{item.reason_text}</p> : null}
          {externalOcr ? <p className="text-meta text-muted-foreground">{EXTERNAL_OCR_NOTE}</p> : null}
          {unused ? <p className="text-meta text-muted-foreground">{NO_CLIENT_NOTE}</p> : null}
          {item.address !== null || item.memory_bytes !== null ? (
            <p className="text-meta text-muted-foreground [overflow-wrap:anywhere]">
              {item.address !== null ? (
                <>
                  {"Address "}
                  <code className="text-code">{item.address}</code>
                </>
              ) : null}
              {item.address !== null && item.memory_bytes !== null ? ", " : null}
              {item.memory_bytes !== null ? `Memory ${formatBytes(item.memory_bytes)}` : null}
            </p>
          ) : null}
          <ModelLines models={item.models} />
          {item.used_by.length > 0 ? (
            <p className="text-meta text-muted-foreground [overflow-wrap:anywhere]">
              {"Used by "}
              {item.used_by.map((key, index) => (
                <span key={key}>
                  {index > 0 ? ", " : null}
                  <code className="text-code">{key}</code>
                </span>
              ))}
            </p>
          ) : (
            <p className="text-meta text-muted-foreground">No setting in force uses it.</p>
          )}
        </>
      }
      actions={canStop(item, mayManage) ? <StopRuntime item={item} title={title} /> : undefined}
    />
  );
}
