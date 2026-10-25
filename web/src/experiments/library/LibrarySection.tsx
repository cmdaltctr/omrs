import { useQueries, useQuery } from "@tanstack/react-query";
import { FilePlus, FlaskConical, FolderPlus, SearchX } from "lucide-react";
import { useState } from "react";
import { useApi } from "../../api/ApiProvider";
import type { Project } from "../../api/experimentLibrary";
import { experimentProjectsQuery, projectExperimentsQuery } from "../../api/queries";
import { EmptyState } from "../../components/EmptyState";
import { ErrorNotice } from "../../components/ErrorNotice";
import { Button } from "../../components/ui/button";
import { Panel } from "../Panel";
import { AddProjectForm } from "./AddProjectForm";
import { ExperimentCard } from "./ExperimentCard";
import { ALL_PROJECTS, matches, NO_FILTERS, plural, type LibraryFilters } from "./labels";
import { LibraryControls } from "./LibraryControls";
import { NewExperimentForm } from "./NewExperimentForm";
import { ProjectDetails } from "./ProjectDetails";

interface LibrarySectionProps {
  filters: LibraryFilters;
  onFiltersChange: (filters: LibraryFilters) => void;
}

/**
 * The experiments of one project or of all projects, as cards, with the
 * project picker, filters, search and the forms that add a project and
 * create an experiment.
 */
export function LibrarySection({ filters, onFiltersChange }: LibrarySectionProps) {
  const api = useApi();
  const projects = useQuery(experimentProjectsQuery(api));
  const [form, setForm] = useState<"project" | "experiment" | null>(null);
  const all = projects.data ?? [];
  const selected = all.find((item) => item.project_id === filters.project) ?? null;
  const shown = selected !== null ? [selected] : all;
  const readable = shown.filter((item) => item.available);
  const available = all.filter((item) => item.available);
  const listings = useQueries({ queries: readable.map((item) => projectExperimentsQuery(api, item.project_id)) });

  if (projects.isError) return <ErrorNotice error={projects.error} onRetry={() => void projects.refetch()} />;
  if (projects.data === undefined) {
    return (
      <p role="status" className="text-meta text-muted-foreground">
        Loading projects.
      </p>
    );
  }

  const failed = listings.find((listing) => listing.isError);
  const loading = listings.some((listing) => listing.data === undefined && !listing.isError);
  const cards = listings.flatMap((listing, index) => {
    const owner = readable[index]!;
    return (listing.data?.experiments ?? []).filter((item) => matches(item, filters)).map((experiment) => ({ owner, experiment }));
  });
  const total = listings.reduce((sum, listing) => sum + (listing.data?.experiments.length ?? 0), 0);
  const onlyListing = selected !== null ? listings[0]?.data : undefined;
  const choose = (project: Project | null) => onFiltersChange({ ...filters, project: project?.project_id ?? ALL_PROJECTS });

  return (
    <div className="flex flex-col gap-4">
      {form === "project" ? (
        <AddProjectForm
          onCancel={() => setForm(null)}
          onAdded={(project) => {
            setForm(null);
            choose(project);
          }}
        />
      ) : null}
      {form === "experiment" && available.length > 0 ? (
        <NewExperimentForm projects={available} initialProject={selected?.project_id ?? null} onCancel={() => setForm(null)} />
      ) : null}
      <Panel title="Library" description="Experiments read from each project's experiments folder each time you open the list.">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setForm("project")}>
            <FolderPlus aria-hidden="true" />
            Add project
          </Button>
          {available.length > 0 ? (
            <Button variant="outline" onClick={() => setForm("experiment")}>
              <FilePlus aria-hidden="true" />
              New experiment
            </Button>
          ) : null}
        </div>
        {all.length > 0 ? <LibraryControls projects={all} filters={filters} onChange={onFiltersChange} /> : null}
        {selected !== null ? (
          <ProjectDetails project={selected} reserved={onlyListing?.reserved} findings={onlyListing?.findings} onRemoved={() => choose(null)} />
        ) : (
          shown
            .filter((item) => !item.available)
            .map((item) => <ProjectDetails key={item.project_id} project={item} onRemoved={() => undefined} />)
        )}
      </Panel>
      {all.length === 0 ? (
        <EmptyState
          icon={FolderPlus}
          message="No experiment project yet. Add a folder that holds an experiments directory."
          action={<Button onClick={() => setForm("project")}>Add project</Button>}
        />
      ) : null}
      {failed !== undefined ? <ErrorNotice error={failed.error} onRetry={() => void failed.refetch()} /> : null}
      {loading ? (
        <p role="status" className="text-meta text-muted-foreground">
          Loading experiments.
        </p>
      ) : null}
      {!loading && readable.length > 0 && total === 0 ? (
        <EmptyState icon={FlaskConical} message="No experiment folder exists in this project yet." />
      ) : null}
      {!loading && total > 0 && cards.length === 0 ? (
        <EmptyState
          icon={SearchX}
          message="No experiment matches these filters."
          action={
            <Button variant="outline" onClick={() => onFiltersChange({ ...NO_FILTERS, project: filters.project })}>
              Clear filters
            </Button>
          }
        />
      ) : null}
      {cards.length > 0 ? (
        <>
          <p role="status" className="text-meta text-muted-foreground">
            Showing {plural(cards.length, "experiment")} of {total}.
          </p>
          <ul aria-label="Experiments" className="grid grid-cols-1 items-start gap-3 md:grid-cols-2 xl:grid-cols-3">
            {cards.map(({ owner, experiment }) => (
              <li key={`${owner.project_id}/${experiment.folder}`} className="min-w-0">
                <ExperimentCard projectId={owner.project_id} experiment={experiment} projectName={selected === null && all.length > 1 ? owner.name : undefined} />
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
