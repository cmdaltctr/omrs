import type { RouterModel, RouterRole } from "../api/llamacppRouter";
import { Badge } from "../components/ui/badge";
import { formatRoute } from "../lib/routes";
import { MODEL_STATE_NAMES, ROLE_NAMES } from "./llamacppRouterWords";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";
const LINK = "text-primary-label underline underline-offset-4";
const META = "text-meta text-muted-foreground";

/** Where the setting that gives each role lives. */
const ROLE_PLACES: Record<RouterRole, ReturnType<typeof formatRoute>> = {
  embeddings: formatRoute({ area: "settings", section: "configuration" }),
  classification: formatRoute({ area: "settings", section: "configuration" }),
  chat: formatRoute({ area: "settings", section: "chat" }),
  judge: formatRoute({ area: "settings", section: "chat" }),
  decision: formatRoute({ area: "settings", section: "providers" }),
};

const STATE_VARIANTS = { "not-downloaded": "neutral", unloaded: "neutral", loading: "info", loaded: "success", failed: "error" } as const;

/** Each role of the entry as a link to the setting that gives it. */
export function RoleLinks({ roles }: { roles: RouterRole[] }) {
  if (roles.length === 0) return <span className={META}>No role</span>;
  return (
    <span className="flex flex-wrap gap-x-2 gap-y-0.5">
      {roles.map((role) => (
        <a key={role} href={ROLE_PLACES[role]} className={LINK}>
          {ROLE_NAMES[role]}
        </a>
      ))}
    </span>
  );
}

/** A table cell that names its column when the row stacks (below the container width of 672 px). */
export function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="cell" className="flex min-w-0 flex-col gap-0.5">
      <span aria-hidden="true" className={`${META} @2xl:hidden`}>
        {label}
      </span>
      {children}
    </div>
  );
}

export function FileCell({ entry }: { entry: RouterModel }) {
  if (entry.file === null) return <span className="text-ui">No file yet</span>;
  return (
    <code dir="ltr" title={entry.file} className={CODE}>
      {entry.file.split("/").pop()}
    </code>
  );
}

export function StateCell({ entry }: { entry: RouterModel }) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={STATE_VARIANTS[entry.state]}>{MODEL_STATE_NAMES[entry.state]}</Badge>
        {entry.reload_pending ? <span className={META}>Reload pending</span> : null}
      </div>
      {entry.reason_text !== null ? <p className="text-ui [overflow-wrap:anywhere]">{entry.reason_text}</p> : null}
      {entry.note !== null ? <p className={META}>{entry.note}</p> : null}
    </>
  );
}
