import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { documentReadingQuery } from "../api/queries";
import type { DocumentReadingKey, DocumentReadingState } from "../api/settingsDocumentReading";
import { ErrorNotice } from "../components/ErrorNotice";
import { DocumentReadingPanel, type ReadingSaved } from "./DocumentReadingPanel";
import { DocumentRoutersCard } from "./DocumentRoutersCard";
import { READING_ROWS } from "./documentReadingWords";
import { RestartDialog } from "./RestartDialog";
import { DenseSettingRows } from "./SettingBox";


export const IDENTITY_NOTE = "These settings are part of the index identity. After a restart, the next ingest can read existing files again.";

interface RestartRequest {
  change: string;
  plural: boolean;
}

/** After a save, the restart prompt for what waits: the row that was saved, or the section when other keys wait too. A row can hold more than one key. */
function restartFor(state: DocumentReadingState, key: DocumentReadingKey, rowKeys: readonly DocumentReadingKey[]): RestartRequest | null {
  const waiting = state.settings.filter((setting) => setting.restart_pending);
  if (waiting.length === 0) return null;
  if (waiting.every((setting) => rowKeys.includes(setting.key))) return { change: READING_ROWS[key]?.label ?? key, plural: false };
  return { change: "Document reading settings", plural: true };
}

/** The Page routing panel and the Router card, saved to `omrs.jsonc` for the next launch of `omrs web`. */
export function DocumentReadingSection() {
  const query = useQuery(documentReadingQuery(useApi()));
  const [restart, setRestart] = useState<RestartRequest | null>(null);
  const state = query.data;
  const saved: ReadingSaved = (next, key, rowKeys = [key]) => setRestart(restartFor(next, key, rowKeys));

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
        <DenseSettingRows>
          <DocumentReadingPanel state={state} onSaved={saved} />
          <DocumentRoutersCard />
        </DenseSettingRows>
      )}
      <RestartDialog change={restart?.change ?? null} plural={restart?.plural} note={IDENTITY_NOTE} onLater={() => setRestart(null)} />
    </section>
  );
}
