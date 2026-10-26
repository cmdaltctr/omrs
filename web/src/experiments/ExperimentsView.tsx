import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { experimentsQuery, pluginsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/button";
import type { ExperimentsRoute } from "../lib/routes";
import { areaById } from "../lib/views";
import { FoldersSection } from "./FoldersSection";
import { ExperimentPage } from "./library/ExperimentPage";
import { NO_FILTERS, type LibraryFilters } from "./library/labels";
import { LibrarySection } from "./library/LibrarySection";
import { NotebookListSection } from "./notebooks/NotebookListSection";
import { NotebookPage } from "./notebooks/NotebookPage";
import { NotebooksSection } from "./NotebooksSection";
import { RunPage } from "./runs/RunPage";
import { RunsSection } from "./runs/RunsSection";
import { TrustNotice } from "./TrustNotice";

const SECTIONS = [
  { id: "library", label: "Library" },
  { id: "notebooks", label: "Notebooks" },
  { id: "sandboxes", label: "Sandboxes" },
  { id: "code-editor", label: "Code editor" },
  { id: "runs", label: "Runs" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

/**
 * The experiment library, notebooks, sandbox contexts, the code editor and
 * pipeline runs. A run, experiment or notebook in the route opens its page;
 * otherwise one chip-switched section shows. The view stays mounted while the
 * route changes inside Experiments, so the section and the library filters
 * are kept when the user comes back from a page. `#/experiments/code-editor`
 * opens the Code editor section.
 */
export function ExperimentsView({ route }: { route: ExperimentsRoute }) {
  const api = useApi();
  const experiments = useQuery(experimentsQuery(api));
  const plugins = useQuery(pluginsQuery(api));
  const linked = "section" in route ? route.section : null;
  const [section, setSection] = useState<SectionId>(linked ?? "library");
  // A link to a section switches to it, also when the view is already mounted.
  const [lastLinked, setLastLinked] = useState(linked);
  if (linked !== lastLinked) {
    setLastLinked(linked);
    if (linked !== null) setSection(linked);
  }
  const [filters, setFilters] = useState<LibraryFilters>(NO_FILTERS);
  const trustNotice = experiments.data?.trust_notice ?? plugins.data?.trust_notice ?? null;

  if ("notebookId" in route) return <NotebookPage key={route.notebookId} notebookId={route.notebookId} />;
  if ("folder" in route) return <ExperimentPage key={`${route.projectId}/${route.folder}`} projectId={route.projectId} folder={route.folder} />;
  if ("runId" in route && route.runId !== null) return <RunPage runId={route.runId} />;

  return (
    <section className="flex flex-col gap-4">
      <PageHeader title="Experiments" summary={areaById("experiments").summary} />
      <TrustNotice text={trustNotice} />
      <div role="group" aria-label="Sections" className="flex flex-wrap gap-2">
        {SECTIONS.map(({ id, label }) => (
          <Button key={id} variant="chip" aria-pressed={section === id} onClick={() => setSection(id)}>
            {label}
          </Button>
        ))}
      </div>
      {section === "library" ? <LibrarySection filters={filters} onFiltersChange={setFilters} /> : null}
      {section === "notebooks" ? <NotebookListSection /> : null}
      {section === "sandboxes" ? (
        experiments.isError ? (
          <ErrorNotice error={experiments.error} onRetry={() => void experiments.refetch()} />
        ) : experiments.data === undefined ? (
          <p role="status" className="text-meta text-muted-foreground">
            Loading experiments.
          </p>
        ) : (
          <FoldersSection list={experiments.data} />
        )
      ) : null}
      {section === "code-editor" ? <NotebooksSection experiments={experiments.data} /> : null}
      {section === "runs" ? <RunsSection experiments={experiments.data} /> : null}
    </section>
  );
}
