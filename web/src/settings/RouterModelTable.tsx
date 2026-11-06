import { useState } from "react";
import type { LlamacppRouterStatus, RouterModel } from "../api/llamacppRouter";
import { useDeleteRouterModel } from "../api/llamacppRouterHooks";
import { Button } from "../components/ui/button";
import { ErrorNotice } from "../components/ErrorNotice";
import { CONFLICT_SENTENCES, conflictReason, isSharedEntry, SHARED_ROW_WARNING } from "./llamacppRouterWords";
import { formatCount } from "./validation";
import { Cell, FileCell, RoleLinks, StateCell } from "./RouterModelRow";
import { RouterGetModel } from "./RouterGetModel";
import { RouterModelEdit } from "./RouterModelEdit";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";
const GRID = "grid grid-cols-1 gap-x-4 gap-y-2 @2xl:grid-cols-[minmax(0,1.2fr)_minmax(0,2.4fr)_minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1.4fr)]";

/** One list entry: its cells, then Edit, Get this model and Remove, and the edit form below. */
function ModelRow({ entry, router, managed }: { entry: RouterModel; router: LlamacppRouterStatus; managed: boolean }) {
  const [editing, setEditing] = useState(false);
  const remove = useDeleteRouterModel();
  const conflict = remove.isError ? conflictReason(remove.error) : null;
  return (
    <div role="row" className={`${GRID} min-w-0 border-b border-border py-3 last:border-b-0`}>
      <Cell label="Roles">
        <RoleLinks roles={entry.roles} />
        {isSharedEntry(entry) ? <p className="text-meta text-status-warning-label">{SHARED_ROW_WARNING}</p> : null}
      </Cell>
      <Cell label="Model">
        <code dir="ltr" className={CODE}>
          {entry.model}
        </code>
        <FileCell entry={entry} />
      </Cell>
      <Cell label="Context size (tokens)">
        <span className="text-ui">{entry.ctx_size === null ? "Not set" : formatCount(entry.ctx_size)}</span>
      </Cell>
      <Cell label="State">
        <StateCell entry={entry} />
      </Cell>
      <Cell label="Actions">
        {managed ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" variant="outline" aria-label={`Edit ${entry.model}`} onClick={() => setEditing(true)}>
              Edit
            </Button>
            {entry.roles.length === 0 ? (
              <Button type="button" size="sm" variant="outline" aria-label={`Remove ${entry.model}`} disabled={remove.isPending} onClick={() => remove.mutate(entry.id)}>
                Remove
              </Button>
            ) : null}
          </div>
        ) : null}
        {managed ? <RouterGetModel entry={entry} router={router} /> : null}
      </Cell>
      {editing ? (
        <div className="min-w-0 @2xl:col-span-full">
          <RouterModelEdit entry={entry} onClose={() => setEditing(false)} />
        </div>
      ) : null}
      {conflict !== null ? (
        <p role="alert" className="text-ui text-status-error-label @2xl:col-span-full">
          {CONFLICT_SENTENCES[conflict]}
        </p>
      ) : null}
      {remove.isError && conflict === null ? (
        <div className="@2xl:col-span-full">
          <ErrorNotice error={remove.error} onRetry={() => remove.reset()} />
        </div>
      ) : null}
    </div>
  );
}

/**
 * The `llamacpp_models` list as a table, one row per entry. A row stacks its
 * fields below the container width of 672 px, so it fits a phone. In `external`
 * mode OMRS reads no file or preset, so a row offers no control.
 */
export function RouterModelTable({ status }: { status: LlamacppRouterStatus }) {
  const managed = status.mode === "managed";
  return (
    <div role="table" aria-label="Router models" className="@container flex min-w-0 flex-col rounded-control border border-border px-3">
      <div role="rowgroup" className="sr-only @2xl:not-sr-only">
        <div role="row" className={`${GRID} border-b border-border py-2 text-meta font-semibold text-muted-foreground`}>
          <div role="columnheader">Roles</div>
          <div role="columnheader">Model</div>
          <div role="columnheader">Context size (tokens)</div>
          <div role="columnheader">State</div>
          <div role="columnheader">Actions</div>
        </div>
      </div>
      <div role="rowgroup">
        {status.models.map((entry) => (
          <ModelRow key={entry.id} entry={entry} router={status} managed={managed} />
        ))}
      </div>
    </div>
  );
}
