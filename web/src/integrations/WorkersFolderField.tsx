import { useState } from "react";
import { ErrorNotice } from "../components/ErrorNotice";
import { RestartDialog } from "../settings/RestartDialog";
import { SettingRow } from "../settings/SettingRow";
import { useConfiguration, useSaveConfiguration } from "../settings/useConfiguration";

const KEY = "ocr_workers_dir";
const LABEL = "OCR workers folder";
const LOCKED = "Remove OCR_WORKERS_DIR from the environment or .env to change it here.";

/**
 * The OCR workers folder in force, with Edit. Save writes `ocr_workers_dir`
 * through the settings write route; the server checks the folder first. The
 * folder applies at the next launch, so a save offers the restart action.
 */
export function WorkersFolderField() {
  const query = useConfiguration();
  const save = useSaveConfiguration();
  const [restart, setRestart] = useState<string | null>(null);
  const state = query.data;
  const row = state?.settings.find((setting) => setting.key === KEY);

  if (state === undefined || row === undefined) {
    return query.isError ? <ErrorNotice error={query.error} onRetry={() => void query.refetch()} /> : null;
  }
  const locked = row.source === "env" || row.source === "dotenv";
  const pending = row.restart_pending;

  function write(value: string | null, done: () => void) {
    if (state === undefined) return;
    save.mutate(
      { revision: state.revision, changes: { [KEY]: value } },
      {
        onSuccess: () => {
          done();
          setRestart(LABEL);
        },
      },
    );
  }

  return (
    <div className="mb-3 flex flex-col gap-1.5">
      <SettingRow
        label={LABEL}
        value={typeof row.value === "string" ? row.value : ""}
        source={row.source}
        readOnlyReason={locked ? LOCKED : row.editable ? null : row.read_only_reason}
        pending={save.isPending}
        error={save.isError ? save.error : null}
        onSave={(text, done) => write(text.trim(), done)}
        onClear={(done) => write(null, done)}
        onRetry={() => save.reset()}
      />
      {pending ? <p className="text-meta text-muted-foreground">The saved folder applies at the next launch. Restart the server to use it.</p> : null}
      <RestartDialog change={restart} onLater={() => setRestart(null)} />
    </div>
  );
}
