import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import type { EditorInfo } from "../api/plugins";
import { experimentProjectsQuery } from "../api/queries";
import { ConfirmAction } from "./ConfirmAction";
import { useStopEditor } from "./mutations";

/** What Stop does to an editor, shown before the user confirms. */
export const STOP_WARNING = "Stopping ends this editor process. Notebook files are kept. Unsaved changes in the editor tab are lost.";

interface EditorListProps {
  editors: EditorInfo[];
  names: Record<string, string>;
}

/**
 * Editors this server started. Each runs in its own browser tab; this page
 * never embeds one. An editor that the Library opened shows its project and
 * experiment folder in place of a context.
 */
export function EditorList({ editors, names }: EditorListProps) {
  const stop = useStopEditor();
  const projects = useQuery({ ...experimentProjectsQuery(useApi()), enabled: editors.some((editor) => editor.project_id !== null) });
  const projectName = (id: string) => projects.data?.find((project) => project.project_id === id)?.name ?? id;
  if (editors.length === 0) return null;
  return (
    <ul aria-label="Running editors" className="flex flex-col gap-2">
      {editors.map((editor) => (
        <li key={editor.launch_id} className="flex flex-col gap-1 rounded-small border border-border p-3">
          <code dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
            {editor.notebook}
          </code>
          <span className="text-meta text-muted-foreground">
            {editor.project_id !== null ? (
              <>
                {editor.plugin}, project {projectName(editor.project_id)}, experiment{" "}
                <span dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
                  {editor.folder}
                </span>
                ,{" "}
              </>
            ) : (
              <>
                {editor.plugin}, context {editor.experiment_context ? (names[editor.experiment_context] ?? editor.experiment_context) : "none"},{" "}
              </>
            )}
            <span dir="ltr">{editor.url_without_token}</span>
          </span>
          <div>
            <ConfirmAction
              label={`Stop editor ${editor.launch_id}`}
              text="Stop"
              warning={STOP_WARNING}
              confirmLabel="Confirm stop"
              cancelLabel="Keep running"
              onConfirm={() => stop.mutateAsync(editor.launch_id)}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
