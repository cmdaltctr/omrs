import { useState, type FormEvent } from "react";
import type { DocumentReadingSetting, DocumentReadingState } from "../api/settingsDocumentReading";
import { useSaveDocumentReading } from "../api/settingsMutations";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { sourceText } from "./connectionWords";
import { draftOf, draftValue, isListKind, listNotes, readerListWarning, readingText, sameDraft, type ReadingChoice, type ReadingDraft, type ReadingRowWords } from "./documentReadingWords";
import type { ListOption } from "./OrderedListControl";
import { ReadingControl } from "./ReadingControl";
import { SaveErrorNotice } from "./SaveErrorNotice";
import { SettingBox, useDenseRows } from "./SettingBox";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";
const META = "text-meta text-muted-foreground";

interface ReadingSettingRowProps {
  setting: DocumentReadingSetting;
  words: ReadingRowWords;
  choices: ReadingChoice[];
  /** The names a list row can hold. Other rows have none. */
  options: ListOption[];
  /** Extra lines for this row, such as the reader in use. */
  notes: string[];
  /** Called with the state the server returned after a good save. */
  onSaved: (state: DocumentReadingState) => void;
}

/**
 * One document reading key: the value in force, its source, the default, and
 * the value saved for the next launch with "Restart to apply" when it differs.
 * Edit opens the control filled with the value the next launch will use. A key
 * from the environment or `.env` has no Edit and names the variable to remove.
 */
export function ReadingSettingRow({ setting, words, choices, options, notes, onSaved }: ReadingSettingRowProps) {
  const save = useSaveDocumentReading();
  const [draft, setDraft] = useState<ReadingDraft | null>(null);
  const { label, kind } = words;
  const next = setting.saved ?? setting.value;
  const start = draftOf(next, kind);
  const list = isListKind(kind) && Array.isArray(next) ? next : null;

  function close() {
    setDraft(null);
    save.reset();
  }

  function send(value: DocumentReadingSetting["value"] | null) {
    save.mutate(
      { [setting.key]: value },
      {
        onSuccess: (state) => {
          close();
          onSaved(state);
        },
      },
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (draft === null || sameDraft(draft, start)) return;
    send(draftValue(kind, draft));
  }

  const dense = useDenseRows();
  const value = (
    <code dir="ltr" className={CODE}>
      {readingText(setting.value, kind)}
    </code>
  );
  const sourceLine = (
    <>
      {sourceText(setting.source)}
      {" · Default: "}
      <span dir="ltr">{readingText(setting.default, kind)}</span>
    </>
  );
  const editButton = (variant: "ghost" | "outline") => (
    <Button type="button" variant={variant} size="sm" aria-label={`Edit ${label}`} onClick={() => setDraft(start)}>
      Edit
    </Button>
  );
  const pending = setting.restart_pending ? (
    <div className="flex flex-wrap items-center gap-2">
      <p className="text-ui">
        {"Saved for the next launch: "}
        <code dir="ltr" className={CODE}>
          {readingText(setting.saved, kind)}
        </code>
      </p>
      <Badge variant="warning">Restart to apply</Badge>
    </div>
  ) : null;
  const extras = (
    <>
      {draft === null && list !== null ? listNotes(list, options).map((note) => <p key={note} className={META}>{note}</p>) : null}
      {draft === null && list !== null && kind === "readers" && readerListWarning(list) !== null ? <p className={META}>{readerListWarning(list)}</p> : null}
      {notes.map((note) => (
        <p key={note} className="text-ui">
          {note}
        </p>
      ))}
      {setting.locked ? <p className={META}>{setting.lock_reason ?? "Read-only here."}</p> : null}
    </>
  );

  return (
    <SettingBox role="group" aria-label={label}>
      {dense && draft === null ? (
        // A compact row: label, value with source and default, help, then Edit on the right.
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <p className={META}>{label}</p>
            <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
              {value}
              <span aria-hidden="true" className={META}>
                ·
              </span>
              <span className={META}>{sourceLine}</span>
            </div>
            <p className={META}>{words.help}</p>
            {pending}
            {extras}
          </div>
          {!setting.locked ? editButton("ghost") : null}
        </div>
      ) : (
        <>
          <p className={META}>{label}</p>
          {draft === null ? value : null}
          <p className={META}>{words.help}</p>
          <p className={META}>{sourceLine}</p>
          {pending}
          {extras}
          {draft === null && !setting.locked ? <div>{editButton("outline")}</div> : null}
        </>
      )}
      {draft !== null ? (
        <form onSubmit={submit} noValidate className="flex flex-col gap-1.5">
          <ReadingControl label={label} kind={kind} draft={draft} choices={choices} options={options} onChange={setDraft} />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" disabled={sameDraft(draft, start) || save.isPending}>
              Save
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={close}>
              Cancel
            </Button>
            {setting.saved !== null ? (
              <Button type="button" variant="outline" size="sm" disabled={save.isPending} onClick={() => send(null)}>
                Use default
              </Button>
            ) : null}
          </div>
        </form>
      ) : null}
      {save.isError ? <SaveErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
    </SettingBox>
  );
}
