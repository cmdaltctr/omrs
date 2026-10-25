import { useQuery } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import type { ReactNode } from "react";
import { useApi } from "../../api/ApiProvider";
import { ApiError } from "../../api/client";
import type { Notebook, NotebookEntry } from "../../api/experimentLibrary";
import { useRemoveNotebookEntry } from "../../api/experimentLibraryMutations";
import { notebookQuery } from "../../api/queries";
import { EmptyState } from "../../components/EmptyState";
import { ErrorNotice } from "../../components/ErrorNotice";
import { NotFound } from "../../components/NotFound";
import { PageHeader } from "../../components/PageHeader";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { formatRoute } from "../../lib/routes";
import { ConfirmAction } from "../ConfirmAction";
import { ExperimentCard } from "../library/ExperimentCard";

const BACK = formatRoute({ area: "experiments", runId: null });

function RemoveEntry({ notebook, entry }: { notebook: Notebook; entry: NotebookEntry }) {
  const remove = useRemoveNotebookEntry();
  return (
    <ConfirmAction
      label={`Remove ${entry.folder} from ${notebook.name}`}
      text="Remove"
      warning="The experiment leaves this notebook. Its folder is not touched."
      confirmLabel="Confirm remove"
      cancelLabel="Keep it"
      onConfirm={() => remove.mutateAsync({ notebookId: notebook.notebook_id, projectId: entry.project_id, folder: entry.folder })}
    />
  );
}

/** An entry whose folder the scan no longer finds. It stays until the user removes it. */
function MissingEntry({ entry, action }: { entry: NotebookEntry; action: ReactNode }) {
  return (
    <Card role="group" aria-label={`Experiment ${entry.folder}`} className="h-full">
      <CardHeader className="gap-2">
        <Badge variant="warning">Missing</Badge>
        <CardTitle dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
          {entry.folder}
        </CardTitle>
        <CardDescription>{entry.project_name}</CardDescription>
      </CardHeader>
      <p className="text-ui">This folder is no longer in the project. It may have been renamed or removed.</p>
      {action}
    </Card>
  );
}

/** One notebook at `#/experiments/notebooks/<id>`: its entries as cards, with Remove on a user notebook. */
export function NotebookPage({ notebookId }: { notebookId: string }) {
  const detail = useQuery(notebookQuery(useApi(), notebookId));
  const missing = detail.error instanceof ApiError && detail.error.status === 404;
  const notebook = detail.data?.notebook;
  const editable = notebook?.kind === "user";

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title={notebook?.name ?? "Notebook"}
        summary={notebook ? (editable ? "Your notebook" : "Project notebook: every experiment in the project") : undefined}
        actions={
          <Button asChild variant="outline">
            <a href={BACK}>Back to Experiments</a>
          </Button>
        }
      />
      {missing ? <NotFound what="notebook" name={notebookId} backHref={BACK} backLabel="Back to Experiments" /> : null}
      {detail.isError && !missing ? <ErrorNotice error={detail.error} onRetry={() => void detail.refetch()} /> : null}
      {detail.isPending ? (
        <p role="status" className="text-meta text-muted-foreground">
          Loading the notebook.
        </p>
      ) : null}
      {detail.data && detail.data.entries.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          message={editable ? "This notebook is empty. Open an experiment in the Library and choose Add to notebook." : "This project has no experiments yet."}
          action={
            <Button asChild variant="outline">
              <a href={BACK}>Open the Library</a>
            </Button>
          }
        />
      ) : null}
      {detail.data && notebook && detail.data.entries.length > 0 ? (
        <ul aria-label="Notebook entries" className="grid grid-cols-1 items-start gap-3 md:grid-cols-2 xl:grid-cols-3">
          {detail.data.entries.map((entry) => {
            const action = editable ? <RemoveEntry notebook={notebook} entry={entry} /> : undefined;
            return (
              <li key={`${entry.project_id}/${entry.folder}`} className="min-w-0">
                {entry.missing || entry.experiment === null ? (
                  <MissingEntry entry={entry} action={action} />
                ) : (
                  <ExperimentCard projectId={entry.project_id} experiment={entry.experiment} projectName={entry.project_name} actions={action} />
                )}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
