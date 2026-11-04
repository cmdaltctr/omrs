import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useApi } from "../api/ApiProvider";
import { integrationsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { PageHeader } from "../components/PageHeader";
import { useRoute } from "../lib/RouteProvider";
import { formatRoute } from "../lib/routes";
import { ServerCallout } from "../settings/ServerCallout";
import { ExtrasSection } from "./ExtrasSection";
import { integrationCardId } from "./IntegrationCard";
import { ModelRuntimesSection } from "./ModelRuntimesSection";
import { PdfReadersSection } from "./PdfReadersSection";
import { ReadingPartsSection } from "./ReadingPartsSection";
import { RuntimeSection } from "./RuntimeSection";
import { SectionChips } from "./SectionChips";
import { isRuntimeSection, sectionFor, sectionsFor } from "./sections";
import { ToolsSection } from "./ToolsSection";
import { useIntegrationInstall } from "./useIntegrationInstall";

const SUMMARY = "Optional extras and tools, and the local parts that your settings depend on.";
/** Says what the page does and where the other settings are. `info`, not `warning`: it states a fact, not a risk. */
const PAGE_ROLE = (
  <>
    This page shows what is installed and running. You can install or remove extras and tools here.{" "}
    <a href={formatRoute({ area: "settings", section: null })} className="underline underline-offset-4">
      Settings
    </a>{" "}
    holds the rest, such as how OMRS reads documents and which models it uses.
  </>
);

/**
 * Moves focus to the entry a link names, such as `#/integrations/anthropic`.
 * The focus waits one task, because the shell focuses the page heading after
 * a move between areas, and that runs after this view's effects.
 */
function useFocusEntry(entry: string | null, loaded: boolean) {
  useEffect(() => {
    if (entry === null || !loaded) return;
    const timer = window.setTimeout(() => {
      const card = document.getElementById(integrationCardId(entry));
      card?.scrollIntoView({ block: "nearest" });
      card?.focus();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [entry, loaded]);
}

/**
 * Integrations, one section at a time, as in Settings. The address names the
 * section (`#/integrations/<section>`); `#/integrations` shows Extras. A link
 * to an entry (`#/integrations/anthropic`) opens that entry's section and
 * focuses it. Each section lives in its own file.
 */
export function IntegrationsView({ entry = null }: { entry?: string | null }) {
  const query = useQuery(integrationsQuery(useApi()));
  const { navigate } = useRoute();
  const list = query.data;
  const control = useIntegrationInstall(list);
  const section = sectionFor(entry, list);
  useFocusEntry(entry !== null && entry !== section ? entry : null, list !== undefined);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Integrations" summary={SUMMARY} />
      <ServerCallout text={PAGE_ROLE} />
      <SectionChips
        sections={sectionsFor(list)}
        current={section}
        list={list}
        onSelect={(next) => navigate({ area: "integrations", entry: next })}
      />
      {list === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading integrations.
          </p>
        )
      ) : section === "extras" ? (
        <ExtrasSection list={list} control={control} />
      ) : section === "tools" ? (
        <ToolsSection list={list} control={control} />
      ) : section === "pdf-readers" ? (
        <PdfReadersSection readers={list.pdf_readers ?? []} />
      ) : section === "reading-parts" && list.reading_parts !== undefined ? (
        <ReadingPartsSection parts={list.reading_parts} />
      ) : section === "model-runtimes" ? (
        <ModelRuntimesSection />
      ) : isRuntimeSection(section) && list.runtime !== undefined ? (
        <RuntimeSection section={section} runtime={list.runtime} />
      ) : null}
    </div>
  );
}
