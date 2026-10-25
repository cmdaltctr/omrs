import { useQuery } from "@tanstack/react-query";
import { BookPlus, ChevronDown } from "lucide-react";
import { useState } from "react";
import { useApi } from "../../api/ApiProvider";
import { useAddNotebookEntry } from "../../api/experimentLibraryMutations";
import { notebooksQuery } from "../../api/queries";
import { Button } from "../../components/ui/button";
import { Popover } from "../../components/ui/popover";
import { describeError } from "../../lib/errors";

/** A menu of the user's notebooks. Choosing one adds this experiment to it. */
export function AddToNotebook({ projectId, folder }: { projectId: string; folder: string }) {
  const notebooks = useQuery(notebooksQuery(useApi()));
  const add = useAddNotebookEntry();
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const own = (notebooks.data ?? []).filter((notebook) => notebook.kind === "user");

  async function addTo(notebookId: string, name: string) {
    setMessage(null);
    try {
      await add.mutateAsync({ notebookId, projectId, folder });
      setMessage({ text: `Added to ${name}.`, failed: false });
    } catch (failure) {
      setMessage({ text: describeError(failure).message, failed: true });
    }
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <Popover
        width={256}
        trigger={(props) => (
          <Button variant="outline" {...props}>
            <BookPlus aria-hidden="true" />
            Add to notebook
            <ChevronDown aria-hidden="true" />
          </Button>
        )}
      >
        {({ close }) =>
          notebooks.isError ? (
            <p className="text-meta">Could not load the notebooks.</p>
          ) : own.length === 0 ? (
            <p className="text-meta">You have no notebook yet. Create one in the Notebooks section.</p>
          ) : (
            <ul aria-label="Your notebooks" className="flex flex-col gap-1">
              {own.map((notebook) => (
                <li key={notebook.notebook_id}>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start"
                    disabled={add.isPending}
                    onClick={() => {
                      close();
                      void addTo(notebook.notebook_id, notebook.name);
                    }}
                  >
                    <span className="min-w-0 truncate">{notebook.name}</span>
                  </Button>
                </li>
              ))}
            </ul>
          )
        }
      </Popover>
      {message !== null ? (
        <p role={message.failed ? "alert" : "status"} className={message.failed ? "text-meta text-status-error-label" : "text-meta text-muted-foreground"}>
          {message.text}
        </p>
      ) : null}
    </div>
  );
}
