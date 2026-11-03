import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import type { ReadingChoice, ReadingKind } from "./documentReadingWords";

const META = "text-meta text-muted-foreground";

interface ReadingControlProps {
  label: string;
  kind: ReadingKind;
  /** The editor text: a name, or `true` / `false` for a switch. */
  draft: string;
  choices: ReadingChoice[];
  onChange: (text: string) => void;
}

/** The control that edits one document reading value. The row shows the visible label; the control carries it as its name. Nothing is saved until the row's Save. */
export function ReadingControl({ label, kind, draft, choices, onChange }: ReadingControlProps) {
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

  const selected = choices.find((choice) => choice.value === draft);
  const blocked = choices.filter((choice) => choice.disabled);
  return (
    <div className="flex flex-col gap-1.5">
      {choices.length === 0 ? (
        <p className="text-ui">No OCR engine is known. Set OCR_WORKERS_DIR to the ocr-workers folder and provision an engine.</p>
      ) : (
        <Select value={draft} onValueChange={onChange}>
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
      )}
      {kind === "engine" && selected?.reason ? <p className={META}>{`${selected.value}: ${selected.reason}`}</p> : null}
      {blocked.map((choice) => (
        <p key={choice.value} className={META}>{`${choice.value} is not available. ${choice.reason ?? ""}`.trim()}</p>
      ))}
    </div>
  );
}
