import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useApi } from "../api/ApiProvider";
import type { Integration, IntegrationList } from "../api/integrations";
import type { ReaderOption } from "../api/settingsDocumentReading";
import { integrationsQuery, queryKeys } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { CopyCommand } from "../integrations/CopyCommand";
import { InstallControls, installPhase } from "../integrations/InstallControls";
import { useIntegrationInstall, type InstallControl } from "../integrations/useIntegrationInstall";
import { OPTIONAL_READERS } from "../pageRouting/pageRoutingWords";
import { INSTALL_REASON_LINES } from "./documentReadingWords";

const META = "text-meta text-muted-foreground";

/** The catalogue entry of the extra that holds `reader`, found through the `extra` of its reader item. */
function entryOf(list: IntegrationList, reader: string): Integration | undefined {
  const extra = list.pdf_readers?.find((item) => item.name === reader)?.extra ?? null;
  return extra === null ? undefined : list.integrations.find((entry) => entry.extra === extra);
}

interface OptionalReaderProps {
  reader: ReaderOption;
  entry: Integration;
  control: InstallControl;
}

/**
 * The Install control of one optional reader (design D8). It reuses `InstallControls`
 * for the button, the running line, the failure output, the refusal and the restart
 * action. An entry the app cannot install shows its reason and the copy command.
 */
function OptionalReader({ reader, entry, control }: OptionalReaderProps) {
  const queryClient = useQueryClient();
  const phase = installPhase(entry, control);
  // The job ended and waits for a restart: read the readers block again, so the choice shows what the server now reports.
  useEffect(() => {
    if (phase === "restart") void queryClient.invalidateQueries({ queryKey: queryKeys.documentReading() });
  }, [phase, queryClient]);

  if (phase === "restart") {
    return (
      <div className="flex min-w-0 flex-col gap-1.5 pt-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="warning">Restart to apply</Badge>
          {reader.available ? null : <p className={META}>Installed. Restart OMRS to use it.</p>}
        </div>
        <InstallControls integration={entry} control={control} />
      </div>
    );
  }
  if (reader.available) return null;
  if (phase === "none") {
    return (
      <div className="flex min-w-0 flex-col gap-1.5 pt-2">
        {entry.install_reason === null ? null : <p className={META}>{INSTALL_REASON_LINES[entry.install_reason]}</p>}
        {entry.install_command === null ? null : <CopyCommand command={entry.install_command} subject={entry.name} />}
      </div>
    );
  }
  return (
    <div className="flex min-w-0 flex-col gap-1.5 pt-2">
      <InstallControls integration={entry} control={control} />
    </div>
  );
}

/** Under the PDF readers row: the Install control of each optional reader that is not installed, or waits for a restart. */
export function PdfReaderInstall({ readers }: { readers: ReaderOption[] }) {
  const api = useApi();
  const list = useQuery(integrationsQuery(api));
  const control = useIntegrationInstall(list.data);
  const optional = readers.filter((reader) => (OPTIONAL_READERS as readonly string[]).includes(reader.name));
  if (optional.length === 0) return null;
  if (list.isError) return <ErrorNotice error={list.error} onRetry={() => void list.refetch()} />;
  const data = list.data;
  if (data === undefined) return null;
  return (
    <>
      {optional.map((reader) => {
        const entry = entryOf(data, reader.name);
        return entry === undefined ? null : <OptionalReader key={reader.name} reader={reader} entry={entry} control={control} />;
      })}
    </>
  );
}
