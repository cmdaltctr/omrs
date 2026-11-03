import type { PdfReaderItem } from "../api/integrations";
import { Badge } from "../components/ui/badge";
import { CopyCommand } from "./CopyCommand";
import { EntryList, EntryRow } from "./EntryList";
import { readerNeedsAttention, SECTION_LABELS } from "./sections";
import { SectionFrame } from "./SectionFrame";

const SUMMARY = "The readers that turn a PDF into text. The first installed reader in the list reads; a later reader retries when the readers before it return no text.";
/** Said once under the heading, as for the runtime sections. */
const CHECKED = "The server checks these readers when the page loads and changes nothing.";

/** Installed is green. A reader that a setting lists and that is missing is red; a missing reader nothing uses stays plain. */
function variant(reader: PdfReaderItem): "success" | "error" | "neutral" {
  if (reader.installed) return "success";
  return readerNeedsAttention(reader) ? "error" : "neutral";
}

function purpose(reader: PdfReaderItem): string {
  return reader.extra === null ? "Comes with the base install." : `Comes with the ${reader.extra} extra.`;
}

/** One reader as a row: name and badge, purpose and uses on the left, the copy command on the right. */
function ReaderRow({ reader }: { reader: PdfReaderItem }) {
  return (
    <EntryRow
      title={reader.name}
      badges={<Badge variant={variant(reader)}>{reader.installed ? "Installed" : "Not installed"}</Badge>}
      purpose={purpose(reader)}
      details={
        reader.used_by.length > 0 ? (
          <div className="flex flex-col text-meta text-muted-foreground [overflow-wrap:anywhere]">
            {reader.used_by.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>
        ) : (
          <p className="text-meta text-muted-foreground">Nothing uses it.</p>
        )
      }
      actions={reader.fix_command !== null ? <CopyCommand command={reader.fix_command} subject={reader.name} /> : undefined}
    />
  );
}

/** Every registered PDF reader, in registry order. The list is generic: a reader registered later shows with no change here. */
export function PdfReadersSection({ readers }: { readers: PdfReaderItem[] }) {
  const title = SECTION_LABELS["pdf-readers"];
  return (
    <SectionFrame id="integrations-pdf-readers" title={title} lines={[SUMMARY, CHECKED]}>
      <EntryList label={title}>
        {readers.map((reader) => (
          <ReaderRow key={reader.name} reader={reader} />
        ))}
      </EntryList>
    </SectionFrame>
  );
}
