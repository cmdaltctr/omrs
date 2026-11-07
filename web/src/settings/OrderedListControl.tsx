import { ArrowDown, ArrowUp, X } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";

/** One name the list can hold. A disabled option cannot be added; `note` says why a listed name cannot run. */
export interface ListOption {
  value: string;
  label: string;
  disabled: boolean;
  note: string | null;
  /** Where to fix a name that cannot run. */
  link: { href: string; text: string } | null;
}

interface OrderedListControlProps {
  /** The name of the list, such as "PDF readers". */
  label: string;
  /** One item of the list, such as "reader". Names the add choice and the empty-list line. */
  noun: string;
  value: string[];
  options: ListOption[];
  /** What the position does, for the row at `index`. */
  positionNote: (index: number) => string;
  onChange: (next: string[]) => void;
  /** Shows the list without a way to change it, as on a read-only graph. */
  disabled?: boolean;
  /** Extra content under the notes of the row for *name* at *index*, such as a setting that belongs to that name. */
  renderRow?: (name: string, index: number) => ReactNode;
}

const META = "text-meta text-muted-foreground";
/** 44 px targets on a narrow screen (omrs-design), 32 px beside a mouse. */
const ICON = "max-sm:size-11";

function moved(list: string[], from: number, to: number): string[] {
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item!);
  return next;
}

/**
 * An ordered list of names: move up, move down, remove, and add from the known
 * names. The list can never be emptied, because an empty list reads nothing.
 * Nothing is saved here; the caller keeps the draft.
 */
export function OrderedListControl({ label, noun, value, options, positionNote, onChange, disabled = false, renderRow }: OrderedListControlProps) {
  const known = new Map(options.map((option) => [option.value, option]));
  const addable = options.filter((option) => !value.includes(option.value));
  const last = value.length === 1;
  // A name that cannot be added yet points to where to fix it, once for each place.
  const fixLinks = [...new Map(addable.filter((option) => option.disabled && option.link !== null).map((option) => [option.link!.href, option.link!])).values()];
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <ol aria-label={label} className="flex min-w-0 flex-col gap-1.5">
        {value.map((name, index) => {
          const option = known.get(name);
          return (
            <li key={name} className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 rounded-control border border-border px-2.5 py-1.5">
              <span aria-hidden="true" className={`${META} tabular-nums`}>
                {index + 1}
              </span>
              <div className="flex min-w-0 flex-1 basis-40 flex-col gap-0.5">
                <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
                  {name}
                </code>
                <span className={META}>{positionNote(index)}</span>
                {option?.note ? <span className={META}>{option.note}</span> : null}
                {option?.note && option.link ? (
                  <a href={option.link.href} className="text-meta text-primary-label underline underline-offset-4">
                    {option.link.text}
                  </a>
                ) : null}
                {renderRow?.(name, index)}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button type="button" variant="ghost" size="icon-sm" className={ICON} aria-label={`Move ${name} up`} disabled={disabled || index === 0} onClick={() => onChange(moved(value, index, index - 1))}>
                  <ArrowUp aria-hidden="true" />
                </Button>
                <Button type="button" variant="ghost" size="icon-sm" className={ICON} aria-label={`Move ${name} down`} disabled={disabled || index === value.length - 1} onClick={() => onChange(moved(value, index, index + 1))}>
                  <ArrowDown aria-hidden="true" />
                </Button>
                <Button type="button" variant="ghost" size="icon-sm" className={ICON} aria-label={`Remove ${name}`} disabled={disabled || last} onClick={() => onChange(value.filter((entry) => entry !== name))}>
                  <X aria-hidden="true" />
                </Button>
              </div>
            </li>
          );
        })}
      </ol>
      {last ? <p className={META}>{`The list needs at least one ${noun}.`}</p> : null}
      {addable.length > 0 ? (
        // Controlled at "" so the choice shows its placeholder again after each add.
        <Select value="" disabled={disabled} onValueChange={(next) => onChange([...value, next])}>
          <SelectTrigger aria-label={`Add ${noun}`} className="max-w-xs">
            <SelectValue placeholder={`Add ${noun}`} />
          </SelectTrigger>
          <SelectContent>
            {addable.map((option) => (
              <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : null}
      {fixLinks.map((link) => (
        <a key={link.href} href={link.href} className="text-meta text-primary-label underline underline-offset-4">
          {link.text}
        </a>
      ))}
    </div>
  );
}
