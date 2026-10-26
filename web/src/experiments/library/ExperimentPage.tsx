import { useQuery } from "@tanstack/react-query";
import { useApi } from "../../api/ApiProvider";
import { ApiError } from "../../api/client";
import type { Experiment } from "../../api/experimentLibrary";
import { projectExperimentQuery } from "../../api/queries";
import { ErrorNotice } from "../../components/ErrorNotice";
import { NotFound } from "../../components/NotFound";
import { PageHeader } from "../../components/PageHeader";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { formatRoute } from "../../lib/routes";
import { AddToNotebook } from "./AddToNotebook";
import { StatusBadge } from "./ExperimentCard";
import { ExperimentTabs } from "./ExperimentTabs";
import { MarimoEditorStatus, OpenInMarimoButton, useMarimoLauncher } from "./OpenInMarimo";

const BACK = formatRoute({ area: "experiments", runId: null });

function RecordFields({ projectId, projectName, experiment }: { projectId: string; projectName: string; experiment: Experiment }) {
  const refs = experiment.refs;
  const refList = refs === null ? [] : [...refs.adrs, ...refs.changes, ...refs.tasks];
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={experiment.status} />
        {experiment.category !== null ? <Badge variant="hue">{experiment.category}</Badge> : null}
        {experiment.size !== null ? <Badge variant="neutral">{experiment.size}</Badge> : null}
        {experiment.migrated ? <Badge variant="neutral">Converted record</Badge> : null}
      </div>
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-ui sm:grid-cols-[max-content_minmax(0,1fr)]">
        <dt className="text-muted-foreground">Project</dt>
        <dd className="break-words">{projectName}</dd>
        <dt className="text-muted-foreground">Folder</dt>
        <dd dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
          {experiment.folder}
        </dd>
        <dt className="text-muted-foreground">Date</dt>
        <dd>{experiment.date}</dd>
        <dt className="text-muted-foreground">Finding</dt>
        <dd className="break-words">{experiment.finding}</dd>
        {experiment.superseded_by !== null ? (
          <>
            <dt className="text-muted-foreground">Superseded by</dt>
            <dd className="min-w-0">
              <a
                href={formatRoute({ area: "experiments", projectId, folder: experiment.superseded_by })}
                dir="ltr"
                className="font-mono text-code text-primary-label underline underline-offset-4 [overflow-wrap:anywhere]"
              >
                {experiment.superseded_by}
              </a>
            </dd>
          </>
        ) : null}
        {refList.length > 0 ? (
          <>
            <dt className="text-muted-foreground">References</dt>
            <dd dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
              {refList.join(", ")}
            </dd>
          </>
        ) : null}
      </dl>
    </Card>
  );
}

/**
 * One experiment at `#/experiments/library/<project>/<folder>`: the record,
 * its files in tabs, its checker findings, "Open in marimo" and the "Add to
 * notebook" menu. A folder the server does not find shows a way back.
 */
export function ExperimentPage({ projectId, folder }: { projectId: string; folder: string }) {
  const detail = useQuery(projectExperimentQuery(useApi(), projectId, folder));
  const marimo = useMarimoLauncher(projectId, folder);
  const missing = detail.error instanceof ApiError && detail.error.status === 404;
  const experiment = detail.data?.experiment;
  const title = experiment ? `${experiment.number}. ${experiment.title}` : folder;
  const back = (
    <Button asChild variant="outline">
      <a href={BACK}>Back to Experiments</a>
    </Button>
  );

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title={title}
        summary={detail.data ? `Experiment in ${detail.data.project.name}` : undefined}
        actions={
          <div className="flex w-full flex-wrap items-start gap-2 sm:w-auto">
            {detail.data ? <OpenInMarimoButton launcher={marimo} /> : null}
            {detail.data ? <AddToNotebook projectId={projectId} folder={folder} /> : null}
            {back}
          </div>
        }
      />
      {missing ? <NotFound what="experiment" name={folder} backHref={BACK} backLabel="Back to Experiments" /> : null}
      {detail.isError && !missing ? <ErrorNotice error={detail.error} onRetry={() => void detail.refetch()} /> : null}
      {detail.isPending ? (
        <p role="status" className="text-meta text-muted-foreground">
          Loading the experiment.
        </p>
      ) : null}
      {detail.data ? (
        <>
          <RecordFields projectId={projectId} projectName={detail.data.project.name} experiment={detail.data.experiment} />
          <MarimoEditorStatus launcher={marimo} />
          <ExperimentTabs detail={detail.data} />
        </>
      ) : null}
    </section>
  );
}
