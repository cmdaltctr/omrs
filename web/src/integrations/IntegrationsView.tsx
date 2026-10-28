import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useApi } from "../api/ApiProvider";
import type { IntegrationList } from "../api/integrations";
import { integrationsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { MasonryColumns } from "../components/MasonryColumns";
import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { useRoute } from "../lib/RouteProvider";
import { IntegrationCard, integrationCardId } from "./IntegrationCard";
import { RuntimeGroup } from "./RuntimeGroups";
import {
  attentionCount,
  isRuntimeSection,
  SECTION_LABELS,
  sectionFor,
  sectionsFor,
  type IntegrationSection,
} from "./sections";
import { ToolCard } from "./ToolCard";
import { useIntegrationInstall } from "./useIntegrationInstall";

/** True when the server can install an entry from this page. */
function canInstall(list: IntegrationList): boolean {
  if (list.integrations.some((integration) => integration.installable)) return true;
  return (
    list.install_type === "uv-tool" &&
    !list.integrations.some((integration) => integration.install_reason === "uv-not-found")
  );
}

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

const SUMMARY = "Optional extras and tools, and the local parts that your settings depend on.";

function availabilityNote(list: IntegrationList | undefined): string {
  const lead = "Availability reflects the running launch of the server.";
  if (list === undefined) return lead;
  return canInstall(list)
    ? `${lead} Install adds the packages to the server. A restart makes them available.`
    : `${lead} This server cannot install extras from the app. To add an extra, run its command in a terminal outside the app, then restart the server.`;
}

/** The chip row. A runtime section that holds red parts shows how many on its chip. */
function SectionChips({
  sections,
  current,
  list,
  onSelect,
}: {
  sections: IntegrationSection[];
  current: IntegrationSection;
  list: IntegrationList | undefined;
  onSelect: (next: IntegrationSection) => void;
}) {
  return (
    <div role="group" aria-label="Sections" className="flex flex-wrap gap-2">
      {sections.map((section) => {
        const label = SECTION_LABELS[section];
        const count = attentionCount(section, list);
        return (
          <Button
            key={section}
            variant="chip"
            aria-pressed={current === section}
            aria-label={count > 0 ? `${label}, ${count} needs attention` : label}
            onClick={() => onSelect(section)}
          >
            {label}
            {count > 0 ? (
              <Badge variant="error" aria-hidden="true" className="tabular-nums">
                {count}
              </Badge>
            ) : null}
          </Button>
        );
      })}
    </div>
  );
}

/** Heading, summary and availability note over one list of cards: the Extras and Tools sections. */
function CardSection({
  id,
  title,
  summary,
  note,
  children,
}: {
  id: string;
  title: string;
  summary: string;
  note: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <div>
        <h2 id={id} className="text-section-title font-semibold">
          {title}
        </h2>
        <p className="text-meta text-muted-foreground">{summary}</p>
        <p role="note" className="text-meta text-muted-foreground">
          {note}
        </p>
      </div>
      {children}
    </section>
  );
}

/**
 * Integrations, one section at a time. The address names the section
 * (`#/integrations/<section>`); `#/integrations` shows Extras. A link to an
 * entry (`#/integrations/anthropic`) opens that entry's section and focuses it.
 */
export function IntegrationsView({ entry = null }: { entry?: string | null }) {
  const query = useQuery(integrationsQuery(useApi()));
  const { navigate } = useRoute();
  const list = query.data;
  const control = useIntegrationInstall(list);
  const section = sectionFor(entry, list);
  const sections = sectionsFor(list);
  useFocusEntry(entry !== null && entry !== section ? entry : null, list !== undefined);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Integrations" summary={SUMMARY} />
      <SectionChips
        sections={sections}
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
        <CardSection
          id="integrations-extras"
          title="Extras"
          summary="Python package extras that add backends, readers and providers to the server."
          note={availabilityNote(list)}
        >
          {/* Masonry, not a grid: a card with an install message is tall, and a
              grid row would leave a gap beside the short cards next to it. */}
          <div role="list" aria-label="Integrations">
            <MasonryColumns>
              {list.integrations.map((integration) => (
                <div key={integration.id} role="listitem" className="min-w-0">
                  <IntegrationCard integration={integration} installType={list.install_type} control={control} />
                </div>
              ))}
            </MasonryColumns>
          </div>
        </CardSection>
      ) : section === "tools" ? (
        // A tool goes into its own uv tool environment, apart from the server's extras (ADR-101).
        <CardSection
          id="integrations-tools"
          title="Tools"
          summary="Programs that run beside OMRS, each in its own uv tool environment."
          note={availabilityNote(list)}
        >
          <div role="list" aria-label="External tools">
            <MasonryColumns>
              {list.tools.map((tool) => (
                <div key={tool.id} role="listitem" className="min-w-0">
                  <ToolCard tool={tool} control={control} />
                </div>
              ))}
            </MasonryColumns>
          </div>
        </CardSection>
      ) : isRuntimeSection(section) && list.runtime !== undefined ? (
        <RuntimeGroup section={section} runtime={list.runtime} />
      ) : (
        <p className="text-meta text-muted-foreground">This server does not report this section.</p>
      )}
    </div>
  );
}
