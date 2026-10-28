import type { ReactNode } from "react";
import type { RuntimeComponents, RuntimeItem, RuntimeStatus } from "../api/integrations";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardInset, CardTitle } from "../components/ui/card";
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

function RuntimeRow({ item }: { item: RuntimeItem }) {
  return (
    <CardInset role="listitem" className="min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="min-w-0 text-ui font-semibold [overflow-wrap:anywhere]">{item.name}</h3>
        <Badge variant={variant(item)}>{LABELS[item.status]}</Badge>
      </div>
      <p className="text-meta text-muted-foreground">{item.purpose}</p>
      {item.reason !== null ? <p className="text-ui [overflow-wrap:anywhere]">{item.reason}</p> : null}
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
      {item.fix !== null ? <CopyCommand command={item.fix} subject={item.name} label="Copy fix command for" /> : null}
    </CardInset>
  );
}

interface GroupProps {
  id: string;
  title: string;
  summary: string;
  items: RuntimeItem[];
  children?: ReactNode;
}

function Group({ id, title, summary, items, children }: GroupProps) {
  return (
    <Card role="region" aria-labelledby={id}>
      <CardHeader>
        <CardTitle id={id}>{title}</CardTitle>
        <CardDescription>{summary}</CardDescription>
      </CardHeader>
      <CardContent>
        {children}
        {items.length === 0 ? (
          <p className="text-meta text-muted-foreground">Nothing to show in this group.</p>
        ) : (
          <div role="list" aria-label={title} className="flex flex-col gap-2">
            {items.map((item) => (
              <RuntimeRow key={item.name} item={item} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** OCR engines, model files and local servers that settings depend on. The page only shows them; each fix is a copy command. */
export function RuntimeGroups({ runtime }: { runtime: RuntimeComponents }) {
  return (
    <section aria-labelledby="integrations-runtime" className="mt-6 flex flex-col gap-3">
      <h2 id="integrations-runtime" className="text-section-title font-semibold">
        Runtime components
      </h2>
      <p className="text-meta text-muted-foreground">These parts are not pip extras. The server checks them when the page loads and changes nothing.</p>
      <Group id="runtime-ocr-engines" title="OCR engines" summary="Engines that read PDF pages without a usable text layer." items={runtime.ocr_engines}>
        <WorkersFolderField />
      </Group>
      <Group id="runtime-model-files" title="Model files" summary="Model files read from the local cache." items={runtime.model_files} />
      <Group id="runtime-local-servers" title="Local servers" summary="Servers at the configured addresses." items={runtime.local_servers} />
    </section>
  );
}
