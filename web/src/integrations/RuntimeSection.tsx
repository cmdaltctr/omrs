import type { RuntimeComponents, RuntimeItem, RuntimeStatus } from "../api/integrations";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { CopyCommand } from "./CopyCommand";
import { EntryList, EntryRow } from "./EntryList";
import { needsAttention, RUNTIME_FIELDS, SECTION_LABELS, type RuntimeSection as Section } from "./sections";
import { SectionFrame } from "./SectionFrame";
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
  return needsAttention(item) ? "error" : "neutral";
}

/** One part as a row: name and badge, purpose, reason and users on the left, the fix command on the right. */
function RuntimeRow({ item }: { item: RuntimeItem }) {
  return (
    <EntryRow
      title={item.name}
      badges={<Badge variant={variant(item)}>{LABELS[item.status]}</Badge>}
      purpose={item.purpose}
      details={
        <>
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
        </>
      }
      actions={item.fix !== null ? <CopyCommand command={item.fix} subject={item.name} label="Copy fix command for" /> : undefined}
    />
  );
}

const SUMMARIES: Record<Section, string> = {
  "ocr-engines": "Engines that read PDF pages without a usable text layer.",
  "model-files": "Model files read from the local cache.",
  "local-servers": "Servers at the configured addresses.",
};

/** These parts are not pip extras. Said once under each runtime section heading. */
const CHECKED = "The server checks these parts when the page loads and changes nothing.";

/**
 * The workers folder is a setting for the whole section, not one of its
 * parts, so it sits in its own card above the parts.
 */
function WorkersFolderCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Where the engines live</CardTitle>
        <CardDescription>The folder that holds the engines. The server checks it when you save.</CardDescription>
      </CardHeader>
      <CardContent>
        <WorkersFolderField />
      </CardContent>
    </Card>
  );
}

/**
 * One runtime section: OCR engines, model files or local servers. A heading
 * and summary over one card with a row per part. The page only shows them;
 * each fix is a copy command.
 */
export function RuntimeSection({ section, runtime }: { section: Section; runtime: RuntimeComponents }) {
  const title = SECTION_LABELS[section];
  const items: RuntimeItem[] = runtime[RUNTIME_FIELDS[section]];
  return (
    <SectionFrame id={`integrations-${section}`} title={title} lines={[`${SUMMARIES[section]} ${CHECKED}`]}>
      {section === "ocr-engines" ? <WorkersFolderCard /> : null}
      {items.length === 0 ? (
        <p className="text-meta text-muted-foreground">Nothing to show in this group.</p>
      ) : (
        <EntryList label={title}>
          {items.map((item) => (
            <RuntimeRow key={item.name} item={item} />
          ))}
        </EntryList>
      )}
    </SectionFrame>
  );
}
