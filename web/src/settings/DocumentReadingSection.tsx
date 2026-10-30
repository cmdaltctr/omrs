import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useApi } from "../api/ApiProvider";
import { documentReadingQuery } from "../api/queries";
import type { DocumentReadingKey, DocumentReadingSetting, DocumentReadingState } from "../api/settingsDocumentReading";
import { ErrorNotice } from "../components/ErrorNotice";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { READING_ROWS, readingChoices } from "./documentReadingWords";
import { ReadingSettingRow } from "./ReadingSettingRow";
import { RestartDialog } from "./RestartDialog";
import { DenseSettingRows } from "./SettingBox";

export const IDENTITY_NOTE = "These settings are part of the index identity. After a restart, the next ingest can read existing files again.";

const PDF_KEYS: readonly DocumentReadingKey[] = ["pdf_reader"];

interface RestartRequest {
  change: string;
  plural: boolean;
}

/** The lines a row shows under its value: the reader the engine resolved. */
function rowNotes(setting: DocumentReadingSetting, state: DocumentReadingState): string[] {
  if (setting.key === "pdf_reader" && state.pdf_reader_in_use !== null && state.pdf_reader_in_use !== setting.value) return [`In use: ${state.pdf_reader_in_use}`];
  return [];
}

/** After a save, the restart prompt for what waits: the saved key alone, or the section when other keys wait too. */
function restartFor(state: DocumentReadingState, key: DocumentReadingKey): RestartRequest | null {
  const waiting = state.settings.filter((setting) => setting.restart_pending);
  if (waiting.length === 0) return null;
  if (waiting.length === 1 && waiting[0]?.key === key) return { change: READING_ROWS[key].label, plural: false };
  return { change: "Document reading settings", plural: true };
}

/** The OCR blocks in their columns: when to use OCR and maths pages left, engines right. */
const OCR_BLOCKS: { title: string; keys: readonly DocumentReadingKey[] }[][] = [
  [
    { title: "When to use OCR", keys: ["ocr_fallback_enabled", "ocr_fallback_min_confidence", "ocr_fallback_page_fraction", "ocr_routing_unit"] },
    { title: "Maths pages", keys: ["ocr_maths_routing_enabled", "ocr_maths_page_fraction"] },
  ],
  [{ title: "Engines", keys: ["ocr_engine_primary", "ocr_engine_fallback"] }],
];

type Saved = (state: DocumentReadingState, key: DocumentReadingKey) => void;

function ReadingRows({ state, keys, onSaved }: { state: DocumentReadingState; keys: readonly DocumentReadingKey[]; onSaved: Saved }) {
  return state.settings
    .filter((setting) => keys.includes(setting.key))
    .sort((a, b) => keys.indexOf(a.key) - keys.indexOf(b.key))
    .map((setting) => (
      <ReadingSettingRow
        key={setting.key}
        setting={setting}
        words={READING_ROWS[setting.key]}
        choices={readingChoices(READING_ROWS[setting.key].kind, state)}
        notes={rowNotes(setting, state)}
        onSaved={(next) => onSaved(next, setting.key)}
      />
    ));
}

/** Where the OCR engines live, or why none can run. */
function WorkersFolder({ dir }: { dir: string | null }) {
  if (dir === null) return <p className="pt-2 text-meta text-muted-foreground">OCR_WORKERS_DIR is not set, so no OCR engine can run.</p>;
  return (
    <p className="pt-2 text-meta text-muted-foreground">
      {"OCR engines folder: "}
      <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
        {dir}
      </code>
    </p>
  );
}

function OcrBlock({ title, children }: { title: string; children: ReactNode }) {
  const id = `reading-${title.toLowerCase().replaceAll(" ", "-")}`;
  return (
    <div role="group" aria-labelledby={id} className="flex min-w-0 flex-col">
      <h4 id={id} className="pb-1 text-ui font-semibold">
        {title}
      </h4>
      {children}
    </div>
  );
}

/** The OCR card: titled blocks, in two columns from 768 px of card width. */
function OcrCard({ state, onSaved }: { state: DocumentReadingState; onSaved: Saved }) {
  return (
    <Card role="region" aria-labelledby="reading-ocr" className="@container">
      <CardHeader>
        <CardTitle id="reading-ocr">OCR</CardTitle>
      </CardHeader>
      <div data-slot="reading-columns" className="grid min-w-0 grid-cols-1 gap-x-6 gap-y-4 @3xl:grid-cols-2">
        {OCR_BLOCKS.map((column, index) => (
          <div key={index} className="flex min-w-0 flex-col gap-4">
            {column.map(({ title, keys }) => (
              <OcrBlock key={title} title={title}>
                <ReadingRows state={state} keys={keys} onSaved={onSaved} />
                {title === "Engines" ? <WorkersFolder dir={state.ocr.workers_dir} /> : null}
              </OcrBlock>
            ))}
          </div>
        ))}
      </div>
    </Card>
  );
}

/** The PDF reader and the OCR settings, saved to `omrs.jsonc` for the next launch of `omrs web`. */
export function DocumentReadingSection() {
  const query = useQuery(documentReadingQuery(useApi()));
  const [restart, setRestart] = useState<RestartRequest | null>(null);
  const state = query.data;
  const saved = (next: DocumentReadingState, key: DocumentReadingKey) => setRestart(restartFor(next, key));

  return (
    <section aria-labelledby="settings-document-reading" className="flex flex-col gap-4">
      <h2 id="settings-document-reading" className="text-section-title font-semibold">
        Document reading
      </h2>
      <ul className="list-disc ps-5 text-meta text-muted-foreground">
        <li>These settings apply after a restart of omrs web. Saving does not change the reading in force.</li>
        <li>{IDENTITY_NOTE}</li>
        <li>A Read document step in a pipeline can choose its own reader.</li>
      </ul>
      {state === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading.
          </p>
        )
      ) : (
        <>
          <DenseSettingRows>
            <Card role="region" aria-labelledby="reading-pdf">
              <CardHeader>
                <CardTitle id="reading-pdf">PDF reading</CardTitle>
              </CardHeader>
              <div className="flex min-w-0 flex-col">
                <ReadingRows state={state} keys={PDF_KEYS} onSaved={saved} />
              </div>
            </Card>
            <OcrCard state={state} onSaved={saved} />
          </DenseSettingRows>
        </>
      )}
      <RestartDialog change={restart?.change ?? null} plural={restart?.plural} note={IDENTITY_NOTE} onLater={() => setRestart(null)} />
    </section>
  );
}
