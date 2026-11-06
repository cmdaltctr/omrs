import { useId, useState } from "react";
import type { RouterModel } from "../api/llamacppRouter";
import { useSaveRouterModel } from "../api/llamacppRouterHooks";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { type Draft, openDraft, presetOf, problems } from "./routerDraft";
import { PRESET_FIELDS, type PresetField } from "./routerPresetFields";
import { SaveErrorNotice } from "./SaveErrorNotice";

/** Radix needs a value for the "Not set" item. A draft holds `""` for it. */
const UNSET = "__unset__";

function options(field: PresetField): readonly string[] {
  if (field.kind === "bool") return field.trueOnly ? ["true"] : ["true", "false"];
  return field.choices ?? [];
}

/** One preset control: a number box, or a pick from the values the preset accepts. */
function PresetControl({ field, text, refusal, onChange }: { field: PresetField; text: string; refusal: string | undefined; onChange: (text: string) => void }) {
  const id = useId();
  const typed = field.kind === "int" || field.kind === "gpu-layers";
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>{field.label}</Label>
      {typed ? (
        <Input id={id} dir="ltr" autoComplete="off" spellCheck={false} type={field.kind === "int" ? "number" : "text"} aria-invalid={refusal !== undefined} aria-describedby={refusal === undefined ? undefined : `${id}-refusal`} value={text} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <Select value={text === "" ? UNSET : text} onValueChange={(next) => onChange(next === UNSET ? "" : next)}>
          <SelectTrigger id={id}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={UNSET}>Not set</SelectItem>
            {options(field).map((choice) => (
              <SelectItem key={choice} value={choice}>
                {choice}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {refusal !== undefined ? (
        <p id={`${id}-refusal`} className="text-meta text-status-error-label">
          {refusal}
        </p>
      ) : null}
    </div>
  );
}

/** The edit form of one entry: a control for each allow-listed preset value. Save sends the whole preset. */
export function RouterModelEdit({ entry, onClose }: { entry: RouterModel; onClose: () => void }) {
  const save = useSaveRouterModel();
  const [draft, setDraft] = useState<Draft>(() => openDraft(entry));
  const [refused, setRefused] = useState<Record<string, string>>({});

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const found = problems(draft);
    setRefused(found);
    if (Object.keys(found).length > 0) return;
    save.mutate({ id: entry.id, change: { preset: presetOf(draft) } }, { onSuccess: onClose });
  }

  return (
    <form onSubmit={submit} noValidate aria-label={`Edit ${entry.model}`} className="flex min-w-0 flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 @lg:grid-cols-2 @3xl:grid-cols-3">
        {PRESET_FIELDS.map((field) => (
          <PresetControl key={field.key} field={field} text={draft[field.key] ?? ""} refusal={refused[field.key]} onChange={(text) => setDraft({ ...draft, [field.key]: text })} />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={save.isPending}>
          Save model
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onClose}>
          Cancel
        </Button>
      </div>
      {save.isError ? <SaveErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
    </form>
  );
}
