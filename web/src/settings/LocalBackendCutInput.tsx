import { useId, useState, type ChangeEvent } from "react";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { CUT_WORDS } from "./documentReadingWords";

interface LocalBackendCutInputProps {
  /** The backend this cut belongs to. It names the input for assistive technology. */
  backend: string;
  /** The cut now set, or `null` for none. */
  value: number | null;
  /** What an empty input shows, such as "Default 0.92". */
  placeholder: string;
  /** Shows the cut without a way to change it. */
  readOnly?: boolean;
  /** Called with a good number, or `null` when the input is emptied. Not called for a bad value. */
  onChange: (value: number | null) => void;
  /** Called when the text is not a number from 0 to 1. */
  onInvalid?: () => void;
}

/** A cut is a number from 0 to 1. Empty text means no cut. `undefined` marks a bad value. */
function parseCut(text: string, badInput: boolean): number | null | undefined {
  if (badInput) return undefined;
  if (text.trim() === "") return null;
  const cut = Number(text);
  return Number.isFinite(cut) && cut >= 0 && cut <= 1 ? cut : undefined;
}

/**
 * The confidence cut of one local OCR backend: a number input from 0 to 1. An
 * empty input means "use the default" and shows it. The input keeps the typed
 * text; the caller gets a number only when the text is a good cut.
 */
export function LocalBackendCutInput({ backend, value, placeholder, readOnly = false, onChange, onInvalid }: LocalBackendCutInputProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const [text, setText] = useState(value === null ? "" : String(value));
  const [invalid, setInvalid] = useState(false);

  function update(event: ChangeEvent<HTMLInputElement>) {
    // A number input reports "" for text like "1e", and flags it as bad input.
    const next = event.target.value;
    setText(next);
    const cut = parseCut(next, event.target.validity.badInput);
    setInvalid(cut === undefined);
    if (cut === undefined) onInvalid?.();
    else onChange(cut);
  }

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
      <Label htmlFor={id} className="text-meta font-normal text-muted-foreground">
        {CUT_WORDS.label}
      </Label>
      <Input
        id={id}
        type="number"
        inputMode="decimal"
        min={0}
        max={1}
        step={0.01}
        value={text}
        placeholder={placeholder}
        readOnly={readOnly}
        aria-label={CUT_WORDS.nameFor(backend)}
        aria-invalid={invalid}
        aria-describedby={invalid ? errorId : undefined}
        className="w-28"
        onChange={update}
      />
      {invalid ? (
        <p id={errorId} className="text-meta text-status-error-label">
          {CUT_WORDS.invalid}
        </p>
      ) : null}
    </div>
  );
}
