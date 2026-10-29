import type { RuntimeComponents, RuntimeItem, RuntimeStatus } from "../api/integrations";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardInset, CardTitle } from "../components/ui/card";
import { CardTitleRow } from "./CardTitleRow";
import { MasonryColumns } from "../components/MasonryColumns";
import { CopyCommand } from "./CopyCommand";
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

/** One part as its own card, like an integration card: name and badge, purpose, then reason, users and fix in mini cards. */
function RuntimeCard({ item }: { item: RuntimeItem }) {
  return (
    <Card role="listitem" className="min-w-0">
      <CardHeader>
        <CardTitleRow title={item.name}>
          <Badge variant={variant(item)}>{LABELS[item.status]}</Badge>
        </CardTitleRow>
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

const SUMMARIES: Record<Section, string> = {
  "ocr-engines": "Engines that read PDF pages without a usable text layer.",
  "model-files": "Model files read from the local cache.",
  "local-servers": "Servers at the configured addresses.",
};

/** These parts are not pip extras. Said once under each runtime section heading. */
const CHECKED = "The server checks these parts when the page loads and changes nothing.";

/**
 * The workers folder is a setting for the whole section, not one of its
 * parts, so it sits above the part cards. In the masonry, a tall settings card
 * pushed the engines out of their order.
 */
function WorkersFolderCard() {
  return (
    <Card className="max-w-xl">
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
 * and summary over masonry columns of cards, one card per part. The page only
 * shows them; each fix is a copy command.
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
        <div role="list" aria-label={title}>
          <MasonryColumns>
            {items.map((item) => (
              <RuntimeCard key={item.name} item={item} />
            ))}
          </MasonryColumns>
        </div>
      )}
    </SectionFrame>
  );
}
