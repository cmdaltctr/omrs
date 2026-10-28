import type { ReactNode } from "react";
import type { RuntimeComponents, RuntimeItem, RuntimeStatus } from "../api/integrations";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardInset, CardTitle } from "../components/ui/card";
import { MasonryColumns } from "../components/MasonryColumns";
import { CopyCommand } from "./CopyCommand";
import { WorkersFolderField } from "./WorkersFolderField";

const LABELS: Record<RuntimeStatus, string> = {
  ready: "Ready",
  missing: "Missing",
  "not-configured": "Not set up",
  "not-running": "Not running",
  unknown: "Unknown",
};

/** Ready is green. A row that a setting in force needs and that is not ready is red; any other row stays plain. */
function variant(item: RuntimeItem): "success" | "error" | "neutral" {
  if (item.status === "ready") return "success";
  return item.used_by.length > 0 ? "error" : "neutral";
}

/** One part as its own card, like an integration card: name and badge, purpose, then reason, users and fix in mini cards. */
function RuntimeCard({ item }: { item: RuntimeItem }) {
  return (
    <Card role="listitem" className="min-w-0">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          {/* An h3 tag with level 4: the card sits under its group heading. */}
          <CardTitle aria-level={4} className="min-w-0 [overflow-wrap:anywhere]">
            {item.name}
          </CardTitle>
          <Badge variant={variant(item)}>{LABELS[item.status]}</Badge>
        </div>
        <CardDescription>{item.purpose}</CardDescription>
      </CardHeader>
      <CardContent>
        {item.reason !== null ? (
          <CardInset>
            <p className="text-ui [overflow-wrap:anywhere]">{item.reason}</p>
          </CardInset>
        ) : null}
        <CardInset>
          {item.used_by.length > 0 ? (
            <p className="text-meta text-muted-foreground [overflow-wrap:anywhere]">
              {"Used by "}
              {item.used_by.map((key, index) => (
                <span key={key}>
                  {index > 0 ? ", " : null}
                  <code className="text-code">{key}</code>
                </span>
              ))}
            </p>
          ) : (
            <p className="text-meta text-muted-foreground">No setting in force uses it.</p>
          )}
        </CardInset>
        {item.fix !== null ? <CopyCommand command={item.fix} subject={item.name} label="Copy fix command for" /> : null}
      </CardContent>
    </Card>
  );
}

interface GroupProps {
  id: string;
  title: string;
  summary: string;
  items: RuntimeItem[];
  /** An extra card placed first in the group's columns. */
  lead?: ReactNode;
}

/** A group heading over masonry columns of cards, as in the integration and tool lists. */
function Group({ id, title, summary, items, lead }: GroupProps) {
  return (
    <section role="region" aria-labelledby={id} className="flex flex-col gap-2">
      <h3 id={id} className="text-subsection-title font-semibold">
        {title}
      </h3>
      <p className="text-meta text-muted-foreground">{summary}</p>
      {items.length === 0 && lead === undefined ? (
        <p className="text-meta text-muted-foreground">Nothing to show in this group.</p>
      ) : (
        <div role="list" aria-label={title}>
          <MasonryColumns>
            {lead !== undefined ? <div key="lead" role="listitem" className="min-w-0">
                {lead}
              </div> : null}
            {items.map((item) => (
              <RuntimeCard key={item.name} item={item} />
            ))}
          </MasonryColumns>
        </div>
      )}
    </section>
  );
}

/** OCR engines, model files and local servers that settings depend on. The page only shows them; each fix is a copy command. */
export function RuntimeGroups({ runtime }: { runtime: RuntimeComponents }) {
  return (
    <section aria-labelledby="integrations-runtime" className="mt-6 flex flex-col gap-4">
      <h2 id="integrations-runtime" className="text-section-title font-semibold">
        Runtime components
      </h2>
      <p className="text-meta text-muted-foreground">These parts are not pip extras. The server checks them when the page loads and changes nothing.</p>
      <Group
        id="runtime-ocr-engines"
        title="OCR engines"
        summary="Engines that read PDF pages without a usable text layer."
        items={runtime.ocr_engines}
        lead={
          <Card>
            <CardHeader>
              <CardTitle aria-level={4}>Where the engines live</CardTitle>
              <CardDescription>The folder that holds the engines. The server checks it when you save.</CardDescription>
            </CardHeader>
            <CardContent>
              <WorkersFolderField />
            </CardContent>
          </Card>
        }
      />
      <Group id="runtime-model-files" title="Model files" summary="Model files read from the local cache." items={runtime.model_files} />
      <Group id="runtime-local-servers" title="Local servers" summary="Servers at the configured addresses." items={runtime.local_servers} />
    </section>
  );
}
