import { useState, type FormEvent } from "react";
import type { DocumentReadingSetting, DocumentReadingState, DocumentReadingValues } from "../api/settingsDocumentReading";
import { useSaveDocumentReading } from "../api/settingsMutations";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { sourceText } from "./connectionWords";
import { CUT_WORDS, cutsOf, cutsText, LIST_WORDS, listNotes, listOptions, READING_ROWS, readingText, sameCuts, type Cuts } from "./documentReadingWords";
import { LocalBackendCutInput } from "./LocalBackendCutInput";
import { OrderedListControl } from "./OrderedListControl";
import { SaveErrorNotice } from "./SaveErrorNotice";
import { SettingBox } from "./SettingBox";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";
const META = "text-meta text-muted-foreground";
const LABEL = READING_ROWS.ocr_local_backends!.label;

interface Draft {
  list: string[];
  cuts: Cuts;
  /** Backends whose cut input holds text that is not a good cut. */
  bad: ReadonlySet<string>;
}

interface LocalOcrBackendsRowProps {
  /** The `ocr_local_backends` setting. */
  list: DocumentReadingSetting;
  /** The `ocr_local_cuts` setting. */
  cuts: DocumentReadingSetting;
  state: DocumentReadingState;
  /** Called with the state the server returned after a save. */
  onSaved: (state: DocumentReadingState) => void;
}

/**
 * The local OCR backends and the confidence cut of each one. Edit opens the
 * ordered list with a cut input in each row, and one Save writes the list and
 * the cuts in one request. A cut for a backend that is not listed stays in the
 * map. A key that the environment locks stays out of the request. The notice
 * for the retired `ocr_local_min_confidence` key sits on top.
 */
export function LocalOcrBackendsRow({ list, cuts, state, onSaved }: LocalOcrBackendsRowProps) {
  const save = useSaveDocumentReading();
  const [draft, setDraft] = useState<Draft | null>(null);
  const startList = (list.saved ?? list.value) as string[];
  const startCuts = cutsOf(cuts.saved ?? cuts.value);
  const options = listOptions("backends", state);
  const placeholder = (name: string) => CUT_WORDS.defaultText(state.local_ocr_backends.find((option) => option.name === name)?.default_cut);
  const retired = state.retired_keys.includes(CUT_WORDS.retiredKey);
  const dirty = draft !== null && (draft.list.join("\n") !== startList.join("\n") || !sameCuts(draft.cuts, startCuts));
  const waiting = [list.restart_pending ? readingText(list.saved, "backends") : null, cuts.restart_pending ? cutsText(cutsOf(cuts.saved)) : null].filter((part) => part !== null);

  function close() {
    setDraft(null);
    save.reset();
  }

  function send(values: DocumentReadingValues) {
    save.mutate(values, {
      onSuccess: (next) => {
        close();
        onSaved(next);
      },
    });
  }

  /** The values to send. A locked key stays out, so the server never sees a write to it. */
  function values(next: { list: string[] | null; cuts: Cuts | null }): DocumentReadingValues {
    return {
      ...(list.locked ? {} : { ocr_local_backends: next.list }),
      ...(cuts.locked ? {} : { ocr_local_cuts: next.cuts !== null && Object.keys(next.cuts).length === 0 ? null : next.cuts }),
    };
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (draft === null || !dirty || draft.bad.size > 0) return;
    send(values(draft));
  }

  function setCut(name: string, cut: number | null) {
    setDraft((current) => {
      if (current === null) return current;
      const next = { ...current.cuts };
      if (cut === null) delete next[name];
      else next[name] = cut;
      const bad = new Set(current.bad);
      bad.delete(name);
      return { ...current, cuts: next, bad };
    });
  }

  function markBad(name: string) {
    setDraft((current) => (current === null ? current : { ...current, bad: new Set(current.bad).add(name) }));
  }

  const cutInput = (name: string, shown: Cuts, editable: boolean) => (
    <LocalBackendCutInput
      key={name}
      backend={name}
      value={shown[name] ?? null}
      placeholder={placeholder(name)}
      readOnly={!editable || cuts.locked}
      onChange={(cut) => setCut(name, cut)}
      onInvalid={() => markBad(name)}
    />
  );

  return (
    <SettingBox role="group" aria-label={LABEL}>
      {retired ? (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-ui">{CUT_WORDS.retiredNotice}</p>
          <Button type="button" variant="outline" size="sm" disabled={save.isPending} onClick={() => save.mutate({ ocr_local_cuts: cuts.saved ?? null })}>
            {CUT_WORDS.removeRetired}
          </Button>
        </div>
      ) : null}
      <div className="flex min-w-0 items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <p className={META}>{LABEL}</p>
          <p className={META}>{READING_ROWS.ocr_local_backends!.help}</p>
          <p className={META}>{CUT_WORDS.help}</p>
          <p className={META}>
            {sourceText(list.source)}
            {" · Default: "}
            <span dir="ltr">{readingText(list.default, "backends")}</span>
          </p>
          {waiting.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-ui">
                {"Saved for the next launch: "}
                <code dir="ltr" className={CODE}>
                  {waiting.join("; ")}
                </code>
              </p>
              <Badge variant="warning">Restart to apply</Badge>
            </div>
          ) : null}
          {draft === null ? listNotes(list.value as string[], options).map((note) => <p key={note} className={META}>{note}</p>) : null}
          {list.locked ? <p className={META}>{list.lock_reason ?? "Read-only here."}</p> : null}
          {cuts.locked ? <p className={META}>{cuts.lock_reason ?? "Read-only here."}</p> : null}
        </div>
        {draft === null && !(list.locked && cuts.locked) ? (
          <Button type="button" variant="ghost" size="sm" aria-label={`Edit ${LABEL}`} onClick={() => setDraft({ list: startList, cuts: startCuts, bad: new Set() })}>
            Edit
          </Button>
        ) : null}
      </div>
      {draft === null ? (
        <ol aria-label={LABEL} className="flex min-w-0 flex-col gap-1.5">
          {(list.value as string[]).map((name) => (
            <li key={name} className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
              <code dir="ltr" className={CODE}>
                {name}
              </code>
              {cutInput(name, cutsOf(cuts.value), false)}
            </li>
          ))}
        </ol>
      ) : (
        <form onSubmit={submit} noValidate className="flex flex-col gap-1.5">
          <OrderedListControl
            label={LABEL}
            noun={LIST_WORDS.backends.noun}
            value={draft.list}
            options={options}
            positionNote={LIST_WORDS.backends.position}
            disabled={list.locked}
            onChange={(next) => setDraft({ ...draft, list: next })}
            renderRow={(name) => cutInput(name, draft.cuts, true)}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" disabled={!dirty || draft.bad.size > 0 || save.isPending}>
              Save
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={close}>
              Cancel
            </Button>
            {list.saved !== null || cuts.saved !== null ? (
              <Button type="button" variant="outline" size="sm" disabled={save.isPending} onClick={() => send(values({ list: null, cuts: null }))}>
                Use default
              </Button>
            ) : null}
          </div>
        </form>
      )}
      {save.isError ? <SaveErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
    </SettingBox>
  );
}
