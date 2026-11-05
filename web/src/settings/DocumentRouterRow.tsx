import { useId, useState, type FormEvent } from "react";
import type { DecisionModelItem, DocumentRouterItem } from "../api/routerMaps";
import { useDeleteDocumentRouter, useRenameDocumentRouter } from "../api/routerMapsHooks";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { DocumentRouterForm } from "./DocumentRouterForm";
import { EXPERIMENTAL, offMachineWarning, routerDraftOf, willNotRunText } from "./routerWords";
import { SaveErrorNotice } from "./SaveErrorNotice";
import { SettingBox } from "./SettingBox";

const META = "text-meta text-muted-foreground";

interface DocumentRouterRowProps {
  item: DocumentRouterItem;
  models: DecisionModelItem[];
  /** What is open on this row: the edit form, the rename field, or nothing. */
  open: "edit" | "rename" | null;
  onOpen: (open: "edit" | "rename" | null) => void;
}

/** The rename field. The server keeps every source digest, because the name is not part of the index identity. */
function RenameForm({ name, onClose }: { name: string; onClose: () => void }) {
  const rename = useRenameDocumentRouter();
  const id = useId();
  const [text, setText] = useState(name);
  const next = text.trim();
  function submit(event: FormEvent) {
    event.preventDefault();
    if (next !== "" && next !== name) rename.mutate({ name, newName: next }, { onSuccess: onClose });
  }
  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-1.5">
      <Label htmlFor={id}>New name</Label>
      <Input id={id} dir="ltr" autoComplete="off" spellCheck={false} className="max-w-xs" value={text} onChange={(event) => setText(event.target.value)} />
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={next === "" || next === name || rename.isPending}>
          Save name
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onClose}>
          Cancel
        </Button>
      </div>
      {rename.isError ? <SaveErrorNotice error={rename.error} onRetry={() => rename.reset()} /> : null}
    </form>
  );
}

/** One router: badges, decision model, question, threshold and limits, off-machine warning, run state, users; Edit, Rename and Delete. */
export function DocumentRouterRow({ item, models, open, onOpen }: DocumentRouterRowProps) {
  const remove = useDeleteDocumentRouter();
  const model = models.find((entry) => entry.name === item.model);
  const titleId = `document-router-${item.name}`;

  return (
    <SettingBox role="listitem" aria-labelledby={titleId}>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <p id={titleId} className="text-ui font-semibold [overflow-wrap:anywhere]">
          {item.name}
        </p>
        {item.host ? <Badge variant="accent">Host router</Badge> : null}
        <Badge variant={item.hosted ? "warning" : "success"}>{item.hosted ? "Hosted" : "Local"}</Badge>
        {item.images ? <Badge variant="info">Images</Badge> : null}
        {item.experimental ? <Badge variant="warning">{EXPERIMENTAL}</Badge> : null}
        {!item.will_run ? <Badge variant="error">Will not run</Badge> : null}
      </div>
      <p className={META}>
        {"Decision model: "}
        <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
          {item.model}
        </code>
      </p>
      <p className="text-ui whitespace-normal [overflow-wrap:anywhere]">{item.question}</p>
      <p className={META}>{`Threshold: ${item.threshold} · Characters sent: ${item.max_chars}`}</p>
      {item.hosted && model !== undefined ? <p className="text-ui text-status-warning-label">{offMachineWarning(model, item.images)}</p> : null}
      {!item.will_run ? <p className="text-ui">{willNotRunText(item)}</p> : null}
      {item.used_by.length > 0 ? <p className={META}>{`Used by profile: ${item.used_by.join(", ")}`}</p> : null}
      {open === "edit" ? <DocumentRouterForm initial={routerDraftOf(item)} models={models} creating={false} fromTemplate={false} onClose={() => onOpen(null)} /> : null}
      {open === "rename" ? <RenameForm name={item.name} onClose={() => onOpen(null)} /> : null}
      {open === null ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" aria-label={`Edit ${item.name}`} onClick={() => onOpen("edit")}>
            Edit
          </Button>
          <Button type="button" variant="outline" size="sm" aria-label={`Rename ${item.name}`} onClick={() => onOpen("rename")}>
            Rename
          </Button>
          <Button type="button" variant="outline" size="sm" aria-label={`Delete ${item.name}`} disabled={remove.isPending} onClick={() => remove.mutate(item.name)}>
            Delete
          </Button>
        </div>
      ) : null}
      {remove.isError ? <SaveErrorNotice error={remove.error} onRetry={() => remove.reset()} /> : null}
    </SettingBox>
  );
}
