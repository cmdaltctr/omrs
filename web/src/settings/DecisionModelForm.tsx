import { useId, useState, type FormEvent, type ReactNode } from "react";
import type { DecisionKind, DecisionKindOption } from "../api/routerMaps";
import { useSaveDecisionModel } from "../api/routerMapsHooks";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { entryOf, isKeyReference, KEY_RETYPE, KEY_RULE, KIND_LABELS, NOT_YET_TESTED, type DecisionDraft } from "./decisionModelWords";
import { SaveErrorNotice } from "./SaveErrorNotice";

const META = "text-meta text-muted-foreground";

type TextField = "name" | "address" | "model" | "key" | "model_file" | "projector_file" | "model_sha256" | "projector_sha256";

interface DecisionModelFormProps {
  initial: DecisionDraft;
  kinds: DecisionKindOption[];
  /** True for a new entry: the name can be typed. */
  creating: boolean;
  /** The entry being edited holds a key reference that the list does not return. */
  keySaved: boolean;
  onClose: () => void;
}

function Field({ label, children, note }: { label: string; children: (id: string) => ReactNode; note?: ReactNode }) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children(id)}
      {note}
    </div>
  );
}

/** The fields of one decision model. Only Save writes; the key field takes a reference only. */
export function DecisionModelForm({ initial, kinds, creating, keySaved, onClose }: DecisionModelFormProps) {
  const save = useSaveDecisionModel();
  const keyNote = useId();
  const [draft, setDraft] = useState(initial);
  const set = <K extends keyof DecisionDraft>(key: K, value: DecisionDraft[K]) => setDraft((current) => ({ ...current, [key]: value }));
  const keyOk = isKeyReference(draft.key);
  const ready = draft.name.trim() !== "" && draft.address.trim() !== "" && draft.model.trim() !== "" && keyOk;
  const managed = draft.kind === "llamacpp" && draft.server === "managed";

  function submit(event: FormEvent) {
    event.preventDefault();
    if (ready) save.mutate({ name: draft.name.trim(), entry: entryOf(draft) }, { onSuccess: onClose });
  }

  const text = (field: TextField, label: string, note?: ReactNode) => (
    <Field label={label} note={note}>
      {(id) => <Input id={id} dir="ltr" autoComplete="off" spellCheck={false} value={draft[field]} aria-describedby={field === "key" ? keyNote : undefined} aria-invalid={field === "key" && !keyOk ? true : undefined} onChange={(event) => set(field, event.target.value)} />}
    </Field>
  );

  return (
    <form aria-label={creating ? "New decision model" : `Edit ${initial.name}`} onSubmit={submit} noValidate className="flex min-w-0 flex-col gap-3">
      {creating ? text("name", "Name") : null}
      <Field label="Kind">
        {(id) => (
          <Select value={draft.kind} onValueChange={(value) => set("kind", value as DecisionKind)}>
            <SelectTrigger id={id} aria-label="Kind" className="max-w-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {kinds.map((kind) => (
                <SelectItem key={kind.name} value={kind.name}>
                  {kind.not_yet_tested ? `${KIND_LABELS[kind.name]} (${NOT_YET_TESTED})` : KIND_LABELS[kind.name]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </Field>
      {text("address", "Address")}
      {text("model", "Model")}
      <label className="flex items-center gap-2 text-ui">
        <input type="checkbox" checked={draft.images} className="size-4 accent-primary" onChange={(event) => set("images", event.target.checked)} />
        Sees page images
      </label>
      {text(
        "key",
        "Key reference",
        <div id={keyNote} className="flex flex-col gap-0.5">
          <p className={keyOk ? META : "text-meta text-status-error-label"}>{KEY_RULE}</p>
          {keySaved ? <p className={META}>{KEY_RETYPE}</p> : null}
        </div>,
      )}
      {draft.kind === "llamacpp" ? (
        <Field label="Server">
          {(id) => (
            <Select value={draft.server} onValueChange={(value) => set("server", value as DecisionDraft["server"])}>
              <SelectTrigger id={id} aria-label="Server" className="max-w-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="unset">Not set</SelectItem>
                <SelectItem value="external">My own server</SelectItem>
                <SelectItem value="managed">Managed by OMRS</SelectItem>
              </SelectContent>
            </Select>
          )}
        </Field>
      ) : null}
      {managed ? (
        <>
          {text("model_file", "Model file")}
          {text("projector_file", "Projector file")}
          {text("model_sha256", "Model file SHA-256")}
          {text("projector_sha256", "Projector file SHA-256")}
        </>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={!ready || save.isPending}>
          Save
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onClose}>
          Cancel
        </Button>
      </div>
      {save.isError ? <SaveErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
    </form>
  );
}
