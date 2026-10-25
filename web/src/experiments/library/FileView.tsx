import { useQuery } from "@tanstack/react-query";
import { useApi } from "../../api/ApiProvider";
import { experimentFileQuery } from "../../api/queries";
import { ErrorNotice } from "../../components/ErrorNotice";
import { MarkdownText } from "./MarkdownText";

/** JSON shown with two-space indents; text that does not parse stays as it is. */
function pretty(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

interface FileViewProps {
  projectId: string;
  folder: string;
  name: string;
  fileNames: ReadonlySet<string>;
  onOpenFile: (name: string) => void;
}

/** One top-level file: Markdown rendered, any other text in a monospace block. */
export function FileView({ projectId, folder, name, fileNames, onOpenFile }: FileViewProps) {
  const file = useQuery(experimentFileQuery(useApi(), projectId, folder, name));
  if (file.isError) return <ErrorNotice error={file.error} onRetry={() => void file.refetch()} />;
  if (file.data === undefined) {
    return (
      <p role="status" className="text-meta text-muted-foreground">
        Loading {name}.
      </p>
    );
  }
  const { text, truncated } = file.data;
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {truncated ? <p className="text-meta text-muted-foreground">This file is larger than 1 MiB. Only the first 1 MiB is shown.</p> : null}
      {name.toLowerCase().endsWith(".md") ? (
        <MarkdownText text={text} fileNames={fileNames} onOpenFile={onOpenFile} />
      ) : (
        <pre dir="ltr" className="max-h-[70vh] overflow-auto rounded-control border border-border bg-muted p-3 font-mono text-code whitespace-pre-wrap [overflow-wrap:anywhere]">
          {name.toLowerCase().endsWith(".json") ? pretty(text) : text}
        </pre>
      )}
    </div>
  );
}
