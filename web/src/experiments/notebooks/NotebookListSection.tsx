import { useQuery } from "@tanstack/react-query";
import { BookPlus, Notebook as NotebookIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useApi } from "../../api/ApiProvider";
import { useCreateNotebook } from "../../api/experimentLibraryMutations";
import { notebooksQuery } from "../../api/queries";
import { EmptyState } from "../../components/EmptyState";
import { ErrorNotice } from "../../components/ErrorNotice";
import { Button } from "../../components/ui/button";
import { TextField } from "../fields";
import { refusalLine } from "../library/refusal";
import { Panel } from "../Panel";
import { NotebookRow } from "./NotebookRow";

function CreateNotebookForm() {
  const create = useCreateNotebook();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setDone(null);
    if (name.trim() === "") {
      setError("Enter a name.");
      return;
    }
    setError(null);
    try {
      const created = await create.mutateAsync(name.trim());
      setDone(`Created ${created.name}.`);
      setName("");
    } catch (failure) {
      setError(refusalLine(failure));
    }
  }

  return (
    <form aria-label="Create a notebook" onSubmit={(event) => void submit(event)} className="flex flex-wrap items-end gap-3">
      <TextField label="Notebook name" value={name} maxLength={80} placeholder="Paper 1" error={error} onChange={setName} />
      <Button type="submit" disabled={create.isPending}>
        <BookPlus aria-hidden="true" />
        Create notebook
      </Button>
      {done !== null ? (
        <p role="status" className="basis-full text-meta text-muted-foreground">
          {done}
        </p>
      ) : null}
    </form>
  );
}

/** Project notebooks, made for each project, and the user's own notebooks with create, rename and delete. */
export function NotebookListSection() {
  const notebooks = useQuery(notebooksQuery(useApi()));
  const all = notebooks.data ?? [];
  const projects = all.filter((notebook) => notebook.kind === "project");
  const own = all.filter((notebook) => notebook.kind === "user");

  return (
    <div className="flex flex-col gap-4">
      <Panel title="Your notebooks" description="A notebook groups experiments from any project. Deleting a notebook changes no experiment file.">
        <CreateNotebookForm />
        {notebooks.isError ? <ErrorNotice error={notebooks.error} onRetry={() => void notebooks.refetch()} /> : null}
        {notebooks.isPending ? (
          <p role="status" className="text-meta text-muted-foreground">
            Loading notebooks.
          </p>
        ) : null}
        {notebooks.data && own.length === 0 ? <EmptyState icon={NotebookIcon} message="You have no notebook yet. Name one above to start." /> : null}
        {own.length > 0 ? (
          <ul aria-label="Your notebooks" className="grid grid-cols-1 items-start gap-2 md:grid-cols-2">
            {own.map((notebook) => (
              <li key={notebook.notebook_id} className="min-w-0">
                <NotebookRow notebook={notebook} />
              </li>
            ))}
          </ul>
        ) : null}
      </Panel>
      {projects.length > 0 ? (
        <Panel title="Project notebooks" description="Each project is a notebook of all its experiments. It cannot be renamed or deleted here.">
          <ul aria-label="Project notebooks" className="grid grid-cols-1 items-start gap-2 md:grid-cols-2">
            {projects.map((notebook) => (
              <li key={notebook.notebook_id} className="min-w-0">
                <NotebookRow notebook={notebook} />
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}
    </div>
  );
}
