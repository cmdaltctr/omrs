import { useQuery } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useApi } from "../../api/ApiProvider";
import type { Experiment } from "../../api/experimentLibrary";
import { useSaveExperimentFile } from "../../api/experimentLibraryMutations";
import { experimentFileQuery } from "../../api/queries";
import { AlertNotice } from "../../components/AlertNotice";
import { Button } from "../../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { Textarea } from "../../components/ui/textarea";
import { describeError } from "../../lib/errors";
import { Panel } from "../Panel";
import { FileView } from "./FileView";
import { saveRefusalLine, saveRefusalReason } from "./refusal";

/** Statuses after which the protocol and the report are part of the record. */
const FINISHED = new Set(["PASS", "FAIL", "INCONCLUSIVE", "MEASURED", "SUPERSEDED"]);
const SAVE_NOTE = "Saving changes the file on disk. Git keeps the old text, and the app records the save in edits.jsonl.";
/** How long "Saved." stays next to the title. */
const SAVED_MS = 4000;

const EDITED_FORMAT = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

/** "26 Oct 2026, 14:05" in local time, from the UTC time of an edit record. */
export function formatEdited(iso: string): string {
  return EDITED_FORMAT.format(new Date(iso));
}

/** The warning above the editor of a finished or converted experiment, or null (design D8). */
export function editWarning(experiment: Experiment): string | null {
  if (FINISHED.has(experiment.status)) {
    return `This experiment is finished (${experiment.status}). Its protocol and report are part of the record. ${SAVE_NOTE}`;
  }
  return experiment.migrated ? `This is a converted record. ${SAVE_NOTE}` : null;
}

interface DiscardDialogProps {
  /** The file with unsaved changes. Null keeps the dialog closed. */
  name: string | null;
  onKeep: () => void;
  onDiscard: () => void;
}

/** Asks before unsaved text is lost. Keep editing returns focus to the control that opened it. */
export function DiscardDialog({ name, onKeep, onDiscard }: DiscardDialogProps) {
  const opener = useRef<HTMLElement | null>(null);
  const kept = useRef(false);
  return (
    <Dialog open={name !== null} onOpenChange={(open) => (open ? undefined : onKeep())}>
      <DialogContent
        closeLabel="Close and keep editing"
        onOpenAutoFocus={() => {
          kept.current = true;
          opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          // After Discard the editor closes and moves focus itself.
          if (kept.current) opener.current?.focus();
        }}
      >
        <DialogHeader>
          <DialogTitle>{`Discard your changes to ${name ?? ""}?`}</DialogTitle>
          <DialogDescription>The text you typed since you opened the editor is lost.</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onKeep}>
            Keep editing
          </Button>
          <Button
            variant="destructive"
            onClick={() => {
              kept.current = false;
              onDiscard();
            }}
          >
            Discard
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface EditableFilePanelProps {
  title: string;
  projectId: string;
  experiment: Experiment;
  name: string;
  fileNames: ReadonlySet<string>;
  onOpenFile: (name: string) => void;
  /** Called with true while the editor holds unsaved text. */
  onDirtyChange: (dirty: boolean) => void;
  /** Runs `action` at once, or after the person agrees to discard unsaved text. */
  confirmDiscard: (action: () => void) => void;
}

interface Draft {
  text: string;
  /** The text when the editor opened or reloaded. */
  original: string;
  /** The revision the save sends back. */
  revision: string;
}

/**
 * The Protocol or Report tab: the rendered file, and an editor for a file the
 * server marks editable (design D8). Save sends the revision the editor
 * loaded; a file that changed on disk keeps the text and offers Reload.
 */
export function EditableFilePanel({ title, projectId, experiment, name, fileNames, onOpenFile, onDirtyChange, confirmDiscard }: EditableFilePanelProps) {
  const folder = experiment.folder;
  const file = useQuery(experimentFileQuery(useApi(), projectId, folder, name));
  const save = useSaveExperimentFile();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [notice, setNotice] = useState<{ line: string; reload: boolean } | null>(null);
  const [saved, setSaved] = useState(false);
  const editButton = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(false);
  const dirty = draft !== null && draft.text !== draft.original;

  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);

  useEffect(() => {
    if (!dirty) return;
    const onUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    // An in-app link changes the hash; ask first, like Cancel and a tab switch.
    const onClick = (event: MouseEvent) => {
      const link = event.target instanceof Element ? event.target.closest("a[href^='#']") : null;
      if (!(link instanceof HTMLAnchorElement)) return;
      event.preventDefault();
      const href = link.getAttribute("href")!;
      if (href === window.location.hash) return; // the page is already open
      confirmDiscard(() => {
        window.location.hash = href;
      });
    };
    window.addEventListener("beforeunload", onUnload);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [dirty, confirmDiscard]);

  useEffect(() => {
    if (!saved) return;
    const timer = setTimeout(() => setSaved(false), SAVED_MS);
    return () => clearTimeout(timer);
  }, [saved]);

  useEffect(() => {
    if (draft === null && returnFocus.current) {
      returnFocus.current = false;
      editButton.current?.focus();
    }
  }, [draft]);

  const close = useCallback(() => {
    returnFocus.current = true;
    setDraft(null);
    setNotice(null);
  }, []);

  function open() {
    const data = file.data;
    if (data === undefined || data.revision === null) return;
    setDraft({ text: data.text, original: data.text, revision: data.revision });
    setSaved(false);
  }

  function submit() {
    if (draft === null) return;
    save.mutate(
      { projectId, folder, name, text: draft.text, baseRevision: draft.revision },
      {
        onSuccess: () => {
          close();
          setSaved(true);
        },
        onError: (error) => setNotice({ line: saveRefusalLine(error), reload: saveRefusalReason(error) === "changed_on_disk" }),
      },
    );
  }

  async function reload() {
    const result = await file.refetch();
    if (result.data !== undefined && result.data.revision !== null) {
      setDraft({ text: result.data.text, original: result.data.text, revision: result.data.revision });
      setNotice(null);
    } else {
      setNotice({ line: describeError(result.error).message, reload: true });
    }
  }

  const editable = file.data?.editable === true && file.data.revision !== null;
  const lastEdited = file.data?.last_edited ?? null;
  const warning = editWarning(experiment);
  const actions = (
    <>
      {saved ? (
        <p role="status" className="text-meta text-muted-foreground">
          Saved.
        </p>
      ) : null}
      {draft === null && editable ? (
        <Button ref={editButton} variant="outline" size="sm" aria-label={`Edit ${name}`} onClick={open}>
          <Pencil aria-hidden="true" />
          Edit
        </Button>
      ) : null}
    </>
  );

  return (
    <Panel title={title} description={lastEdited === null ? undefined : `Last edited ${formatEdited(lastEdited.edited_at)}`} actions={actions}>
      {draft === null ? (
        <FileView projectId={projectId} folder={folder} name={name} fileNames={fileNames} onOpenFile={onOpenFile} />
      ) : (
        <div className="flex min-w-0 flex-col gap-3">
          {warning !== null ? (
            <p className="rounded-panel border border-status-warning bg-status-warning/10 px-4 py-3 text-ui text-status-warning-label">{warning}</p>
          ) : null}
          {notice !== null ? (
            <AlertNotice message={notice.line}>
              {notice.reload ? (
                <Button variant="outline" size="sm" onClick={() => void reload()}>
                  Reload
                </Button>
              ) : null}
            </AlertNotice>
          ) : null}
          <Textarea
            mono
            dir="ltr"
            aria-label={`Text of ${name}`}
            value={draft.text}
            onChange={(event) => setDraft({ ...draft, text: event.target.value })}
            autoFocus
          />
          <div className="flex flex-wrap gap-2">
            <Button onClick={submit} disabled={save.isPending}>
              Save
            </Button>
            <Button variant="outline" onClick={() => confirmDiscard(close)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Panel>
  );
}
