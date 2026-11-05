import { useId, useState, type FormEvent, type ReactNode } from "react";
import type { DecisionModelItem } from "../api/routerMaps";
import { useSaveDocumentRouter } from "../api/routerMapsHooks";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import { ROUTER_COST } from "./documentReadingWords";
import { maxCharsOf, offMachineWarning, OPT_IN_LABEL, routerEntryOf, thresholdOf, THRESHOLD_NOTE, type RouterDraft, RESERVED_NAME } from "./routerWords";
import { SaveErrorNotice } from "./SaveErrorNotice";

const META = "text-meta text-muted-foreground";

interface DocumentRouterFormProps {
  initial: RouterDraft;
  models: DecisionModelItem[];
  /** True for a new router: the name can be typed. */
  creating: boolean;
  /** True when the form opened from the Experiment 43 template: the threshold shows its note. */
  fromTemplate: boolean;
  onClose: () => void;
}

function Field({ label, children, note }: { label: string; children: (id: string) => ReactNode; note?: string }) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children(id)}
      {note !== undefined ? <p className={META}>{note}</p> : null}
    </div>
  );
}

function Check({ checked, onChange, children }: { checked: boolean; onChange: (checked: boolean) => void; children: string }) {
  return (
    <label className="flex items-center gap-2 text-ui">
      <input type="checkbox" checked={checked} className="size-4 accent-primary" onChange={(event) => onChange(event.target.checked)} />
      {children}
    </label>
  );
}

/** The fields of one router. A hosted model adds the off-machine warning and the opt-in, off by default. Only Save writes. */
export function DocumentRouterForm({ initial, models, creating, fromTemplate, onClose }: DocumentRouterFormProps) {
  const save = useSaveDocumentRouter();
  const [draft, setDraft] = useState(initial);
  const set = <K extends keyof RouterDraft>(key: K, value: RouterDraft[K]) => setDraft((current) => ({ ...current, [key]: value }));
  const model = models.find((item) => item.name === draft.model);
  const hosted = model?.hosted === true;
  const entry = routerEntryOf(draft, hosted);
  const reserved = draft.name.trim() === "none";
  const ready = entry !== null && draft.name.trim() !== "" && !reserved;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (ready) save.mutate({ name: draft.name.trim(), entry }, { onSuccess: onClose });
  }

  return (
    <form aria-label={creating ? "New router" : `Edit ${initial.name}`} onSubmit={submit} noValidate className="flex min-w-0 flex-col gap-3">
      <p className={META}>{ROUTER_COST}</p>
      {creating ? <Field label="Name">{(id) => <Input id={id} dir="ltr" autoComplete="off" spellCheck={false} className="max-w-xs" value={draft.name} aria-invalid={reserved ? true : undefined} onChange={(event) => set("name", event.target.value)} />}</Field> : null}
      {creating && reserved ? <p className="text-meta text-status-error-label">{RESERVED_NAME}</p> : null}
      <Field label="Decision model">
        {(id) => (
          <Select value={draft.model} onValueChange={(value) => set("model", value)}>
            <SelectTrigger id={id} aria-label="Decision model" className="max-w-xs">
              <SelectValue placeholder="Choose a decision model" />
            </SelectTrigger>
            <SelectContent>
              {models.map((item) => (
                <SelectItem key={item.name} value={item.name}>
                  {item.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </Field>
      <Field label="Question" note='A "yes" keeps the page text. A "no" sends the page to OCR.'>
        {(id) => <Textarea id={id} rows={3} className="max-w-prose" value={draft.question} onChange={(event) => set("question", event.target.value)} />}
      </Field>
      <Field label="Threshold" note={fromTemplate ? THRESHOLD_NOTE : "A page with a yes score below the threshold goes to OCR. Use a value from 0 to 1."}>
        {(id) => <Input id={id} type="number" min={0} max={1} step="any" className="max-w-32" aria-invalid={thresholdOf(draft.threshold) === null ? true : undefined} value={draft.threshold} onChange={(event) => set("threshold", event.target.value)} />}
      </Field>
      <Check checked={draft.images} onChange={(checked) => set("images", checked)}>
        Sees the page image
      </Check>
      <Field label="Characters sent" note="The most page characters sent with each question.">
        {(id) => <Input id={id} type="number" min={1} step={1} className="max-w-32" aria-invalid={maxCharsOf(draft.max_chars) === null ? true : undefined} value={draft.max_chars} onChange={(event) => set("max_chars", event.target.value)} />}
      </Field>
      {hosted && model !== undefined ? (
        <div className="flex flex-col gap-1.5 rounded-control border border-status-warning bg-status-warning/10 p-3">
          <p className="text-ui text-status-warning-label">{offMachineWarning(model, draft.images)}</p>
          <Check checked={draft.send_off_machine} onChange={(checked) => set("send_off_machine", checked)}>
            {OPT_IN_LABEL}
          </Check>
          {!draft.send_off_machine ? <p className={META}>The router will not run until you tick this box.</p> : null}
        </div>
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
