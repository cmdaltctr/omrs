import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { isListKind, LIST_WORDS, readerListWarning, type ReadingChoice, type ReadingDraft, type ReadingKind } from "./documentReadingWords";
import { OrderedListControl, type ListOption } from "./OrderedListControl";

const META = "text-meta text-muted-foreground";

interface ReadingControlProps {
  label: string;
  kind: ReadingKind;
  /** The editor value: the names of a list, `true` or `false` for a switch, a name otherwise. */
  draft: ReadingDraft;
  /** The select choices: routing units or script modes. Lists and switches have none. */
  choices: ReadingChoice[];
  /** The names a list can hold. */
  options: ListOption[];
  onChange: (draft: ReadingDraft) => void;
}

/** The control that edits one document reading value. The row shows the visible label; the control carries it as its name. Nothing is saved until the row's Save. */
export function ReadingControl({ label, kind, draft, choices, options, onChange }: ReadingControlProps) {
  if (isListKind(kind) && typeof draft !== "string") {
    const words = LIST_WORDS[kind];
    const warning = kind === "readers" ? readerListWarning(draft) : null;
    return (
      <div className="flex flex-col gap-1.5">
        <OrderedListControl label={label} noun={words.noun} value={draft} options={options} positionNote={words.position} onChange={onChange} />
        {warning !== null ? <p className={META}>{warning}</p> : null}
      </div>
    );
  }

  if (kind === "switch") {
    const on = draft === "true";
    return (
      <div className="flex flex-col gap-1.5">
        <div>
          <Button type="button" variant="outline" role="switch" aria-checked={on} aria-label={label} onClick={() => onChange(on ? "false" : "true")}>
            {on ? "On" : "Off"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <Select value={String(draft)} onValueChange={onChange}>
        <SelectTrigger aria-label={label} className="max-w-xs">
          <SelectValue placeholder="Choose one" />
        </SelectTrigger>
        <SelectContent>
          {choices.map((choice) => (
            <SelectItem key={choice.value} value={choice.value} disabled={choice.disabled}>
              {choice.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
