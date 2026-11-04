import type { DiscoveredPartHealth, LocalOcrBackendHealth, PageRuleHealth, ReadingPartsHealth } from "../api/integrations";
import { Badge } from "../components/ui/badge";
import { EntryList, EntryRow } from "./EntryList";
import { SECTION_LABELS } from "./sections";
import { SectionFrame } from "./SectionFrame";

const SUMMARY = "The parts that read PDF pages: the local OCR backends in the order Settings lists them, the page rules, and the parts that installed packages add.";
const CHECKED = "The server checks these parts when the page loads and changes nothing.";
const META = "text-meta text-muted-foreground [overflow-wrap:anywhere]";

const KIND_WORDS: Record<DiscoveredPartHealth["kind"], string> = {
  pdf_reader: "PDF reader",
  local_ocr_backend: "Local OCR backend",
  page_rule: "Page rule",
};

function sourceLine(source: string): string {
  return source === "built-in" ? "Comes with OMRS." : `Added by ${source}.`;
}

function backendBadge(backend: LocalOcrBackendHealth) {
  if (backend.off_reason !== null) return <Badge variant="error">Switched off</Badge>;
  if (!backend.installed) return <Badge variant="error">Not installed</Badge>;
  if (backend.model_present === false) return <Badge variant="error">Model missing</Badge>;
  return <Badge variant="success">Ready</Badge>;
}

/** One listed backend: the state, why it is off, its cut and whether its model files are on disk. */
function BackendRow({ backend, index }: { backend: LocalOcrBackendHealth; index: number }) {
  const position = index === 0 ? "Reads flagged pages first." : "Reads the pages the backends above could not read well.";
  return (
    <EntryRow
      title={backend.label}
      badges={backendBadge(backend)}
      purpose={`${position} ${sourceLine(backend.source)}`}
      details={
        <div className={`flex flex-col ${META}`}>
          {backend.off_reason !== null ? <p>{`Switched off until the server restarts: ${backend.off_reason}`}</p> : null}
          {backend.effective_cut !== null ? <p>{`Confidence cut: ${backend.effective_cut}`}</p> : null}
          {backend.model_present === null ? null : <p>{backend.model_present ? "Model files are on this machine." : "Model files are not on this machine."}</p>}
          <p>
            {"Name: "}
            <code dir="ltr" className="text-code font-mono">
              {backend.name}
            </code>
          </p>
        </div>
      }
    />
  );
}

function RuleRow({ rule }: { rule: PageRuleHealth }) {
  return (
    <EntryRow
      title={rule.label}
      badges={<Badge variant={rule.enabled ? "success" : "neutral"}>{rule.enabled ? "On" : "Off"}</Badge>}
      purpose={sourceLine(rule.source)}
      details={<p className={META}>{`Version ${rule.version}`}</p>}
    />
  );
}

function DiscoveredRow({ part }: { part: DiscoveredPartHealth }) {
  const from = [part.distribution, part.version].filter((word) => word !== null).join(" ");
  return (
    <EntryRow
      title={part.name ?? part.distribution ?? "Unknown part"}
      badges={part.problem === null ? <Badge variant="success">Loaded</Badge> : <Badge variant="error">Broken</Badge>}
      purpose={`${KIND_WORDS[part.kind]} from ${from || "an unknown package"}.`}
      details={part.problem !== null ? <p className={META}>{part.problem}</p> : undefined}
    />
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <h3 className="text-ui font-semibold">{title}</h3>
      {children}
    </div>
  );
}

/** The health of each reading part, from the part descriptors. Every list is generic: a part added later shows with no change here. */
export function ReadingPartsSection({ parts }: { parts: ReadingPartsHealth }) {
  return (
    <SectionFrame id="integrations-reading-parts" title={SECTION_LABELS["reading-parts"]} lines={[SUMMARY, CHECKED]}>
      <Group title="Local OCR backends">
        <EntryList label="Local OCR backends">
          {parts.local_ocr_backends.map((backend, index) => (
            <BackendRow key={backend.name} backend={backend} index={index} />
          ))}
        </EntryList>
      </Group>
      <Group title="Page rules">
        <EntryList label="Page rules">
          {parts.page_rules.map((rule) => (
            <RuleRow key={rule.name} rule={rule} />
          ))}
        </EntryList>
      </Group>
      <Group title="Discovered parts">
        {parts.discovered_parts.length === 0 ? (
          <p className={META}>No installed package adds a reading part.</p>
        ) : (
          <EntryList label="Discovered parts">
            {parts.discovered_parts.map((part, index) => (
              <DiscoveredRow key={`${part.distribution ?? ""}-${part.name ?? index}`} part={part} />
            ))}
          </EntryList>
        )}
      </Group>
    </SectionFrame>
  );
}
