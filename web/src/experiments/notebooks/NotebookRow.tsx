import { useState, type FormEvent } from "react";
import type { Notebook } from "../../api/experimentLibrary";
import { useDeleteNotebook, useRenameNotebook } from "../../api/experimentLibraryMutations";
import { Button } from "../../components/ui/button";
import { CardInset } from "../../components/ui/card";
import { formatRoute } from "../../lib/routes";
import { ConfirmAction } from "../ConfirmAction";
import { TextField } from "../fields";
import { plural } from "../library/labels";
import { refusalLine } from "../library/refusal";

/** One notebook: its name opens it. A user notebook also has Rename and Delete. */
export function NotebookRow({ notebook }: { notebook: Notebook }) {
  const rename = useRenameNotebook();
  const remove = useDeleteNotebook();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(notebook.name);
  const [error, setError] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (name.trim() === "") {
      setError("Enter a name.");
      return;
    }
    try {
      await rename.mutateAsync({ notebookId: notebook.notebook_id, name: name.trim() });
      setEditing(false);
      setError(null);
    } catch (failure) {
      setError(refusalLine(failure));
    }
  }

  return (
    <CardInset role="group" aria-label={`Notebook ${notebook.name}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <a
            href={formatRoute({ area: "experiments", notebookId: notebook.notebook_id })}
            className="text-ui font-medium break-words text-foreground underline-offset-4 hover:underline"
          >
            {notebook.name}
          </a>
          <p className="text-meta text-muted-foreground">{plural(notebook.entry_count, "experiment")}</p>
        </div>
        {notebook.kind === "user" && !editing ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" aria-label={`Rename ${notebook.name}`} onClick={() => setEditing(true)}>
              Rename
            </Button>
            <ConfirmAction
              label={`Delete ${notebook.name}`}
              text="Delete"
              warning="The notebook and its list of experiments go. No experiment file changes."
              confirmLabel="Confirm delete"
              cancelLabel="Keep notebook"
              onConfirm={() => remove.mutateAsync(notebook.notebook_id)}
            />
          </div>
        ) : null}
      </div>
      {editing ? (
        <form aria-label={`Rename ${notebook.name}`} onSubmit={(event) => void save(event)} className="flex flex-wrap items-end gap-2">
          <TextField label="New name" value={name} maxLength={80} error={error} onChange={setName} />
          <Button type="submit" size="sm" disabled={rename.isPending}>
            Save name
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setEditing(false);
              setName(notebook.name);
              setError(null);
            }}
          >
            Cancel
          </Button>
        </form>
      ) : null}
    </CardInset>
  );
}
