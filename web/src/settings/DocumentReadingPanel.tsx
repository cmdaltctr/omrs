import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { documentRoutersQuery } from "../api/routerMapsHooks";
import type { DocumentReadingKey, DocumentReadingSetting, DocumentReadingState } from "../api/settingsDocumentReading";
import { formatRoute } from "../lib/routes";
import { PageRoutingPanel } from "../pageRouting/PageRoutingPanel";
import type { PanelKey } from "../pageRouting/pageRoutingWords";
import { isListKind, listOptions, READING_ROWS, readingChoices } from "./documentReadingWords";
import { LocalOcrBackendsRow } from "./LocalOcrBackendsRow";
import { PdfReaderInstall } from "./PdfReaderInstall";
import { ReadingSettingRow } from "./ReadingSettingRow";

const META = "text-meta text-muted-foreground";
/** The id of the Router card title in `DocumentRoutersCard`. The step 3 link scrolls to it. */
const ROUTER_CARD = "reading-router";

/** Called with the state the server returned after a save, the saved row's key and the keys of its row. */
export type ReadingSaved = (state: DocumentReadingState, key: DocumentReadingKey, rowKeys?: readonly DocumentReadingKey[]) => void;

/** The lines a row shows under its value: the reader the engine resolved, when it is not the first in the list. */
function rowNotes(setting: DocumentReadingSetting, state: DocumentReadingState): string[] {
  if (setting.key === "pdf_readers" && Array.isArray(setting.value) && state.pdf_reader_in_use !== null && state.pdf_reader_in_use !== setting.value[0]) return [`In use: ${state.pdf_reader_in_use}`];
  return [];
}

/** Where the OCR engines live, or why none can run. */
function WorkersFolder({ dir }: { dir: string | null }) {
  if (dir === null) return <p className={`pt-2 ${META}`}>OCR_WORKERS_DIR is not set, so no OCR engine can run.</p>;
  return (
    <p className={`pt-2 ${META}`}>
      {"OCR engines folder: "}
      <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
        {dir}
      </code>
    </p>
  );
}

/** Scrolls to the Router card, where the named routers are defined. The address stays on Document reading. */
function RouterLink() {
  return (
    <p className={`pt-2 ${META}`}>
      <a
        href={formatRoute({ area: "settings", section: "document-reading" })}
        className="underline underline-offset-4"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById(ROUTER_CARD)?.scrollIntoView({ block: "start" });
        }}
      >
        Define routers in the Router section
      </a>
    </p>
  );
}

/**
 * The Page routing panel in Settings (change page-routing-panel, design D1 and D6):
 * one `ReadingSettingRow` for each key, in the step where the key acts. The panel
 * lays the rows out; this component says which row each key gets.
 */
export function DocumentReadingPanel({ state, onSaved }: { state: DocumentReadingState; onSaved: ReadingSaved }) {
  const routers = useQuery(documentRoutersQuery(useApi()));
  const routerNames = (routers.data?.routers ?? []).map((router) => router.name);
  const find = (key: DocumentReadingKey) => state.settings.find((setting) => setting.key === key);

  function renderRow(key: PanelKey) {
    const setting = find(key);
    const words = READING_ROWS[key];
    if (setting === undefined || words === undefined) return null;
    // The backends row edits the cuts map with the list, so it takes the cuts setting too.
    const cuts = key === "ocr_local_backends" ? find("ocr_local_cuts") : undefined;
    if (cuts !== undefined) return <LocalOcrBackendsRow list={setting} cuts={cuts} state={state} onSaved={(next) => onSaved(next, key, [key, cuts.key])} />;
    return (
      <ReadingSettingRow
        setting={setting}
        words={words}
        choices={readingChoices(words.kind, routerNames, setting.default)}
        options={isListKind(words.kind) ? listOptions(words.kind, state) : []}
        notes={rowNotes(setting, state)}
        onSaved={(next) => onSaved(next, key)}
      />
    );
  }

  function renderExtra(step: number) {
    if (step === 1) return <PdfReaderInstall readers={state.pdf_readers} />;
    if (step === 3) return <RouterLink />;
    if (step === 5) return <WorkersFolder dir={state.ocr.workers_dir} />;
    return null;
  }

  return (
    <PageRoutingPanel
      renderRow={renderRow}
      // The cut boxes sit inside the backends row, because one Save writes the list and the cuts together.
      renderCuts={() => null}
      renderExtra={renderExtra}
      ocrFallbackEnabled={find("ocr_fallback_enabled")?.value !== false}
    />
  );
}
