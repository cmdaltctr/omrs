import { useCallback, useMemo, useState } from "react";
import type { ExperimentDetail } from "../../api/experimentLibrary";
import { Button } from "../../components/ui/button";
import { CardInset } from "../../components/ui/card";
import { Panel } from "../Panel";
import { FileView } from "./FileView";
import { formatSize } from "./labels";
import { FindingLine } from "./ProjectDetails";

const TABS = [
  { id: "protocol", label: "Protocol" },
  { id: "plan", label: "Plan" },
  { id: "report", label: "Report" },
  { id: "files", label: "Files" },
  { id: "checks", label: "Checks" },
] as const;

type TabId = (typeof TABS)[number]["id"];

/** The first of `candidates` that the folder holds and the app can open. */
function pick(names: ReadonlySet<string>, candidates: readonly string[]): string | null {
  return candidates.find((name) => names.has(name)) ?? null;
}

/** Protocol, Plan, Report, Files and Checks of one experiment. A relative link in a file switches the tab. */
export function ExperimentTabs({ detail }: { detail: ExperimentDetail }) {
  const { project, experiment, files, output } = detail;
  const viewable = useMemo(() => new Set(files.filter((file) => file.viewable).map((file) => file.name)), [files]);
  const tabFiles = useMemo<Record<"protocol" | "plan" | "report", string | null>>(
    () => ({
      protocol: pick(viewable, ["protocol.md"]),
      plan: pick(viewable, ["plan.json", "plan.md"]),
      // Older folders keep their report in results.md.
      report: pick(viewable, ["report.md", "results.md"]),
    }),
    [viewable],
  );
  const [tab, setTab] = useState<TabId>(tabFiles.protocol !== null ? "protocol" : "report");
  const [selected, setSelected] = useState<string | null>(null);

  const openFile = useCallback(
    (name: string) => {
      const owner = (["protocol", "plan", "report"] as const).find((id) => tabFiles[id] === name);
      if (owner !== undefined) setTab(owner);
      else {
        setSelected(name);
        setTab("files");
      }
    },
    [tabFiles],
  );

  const view = (name: string) => (
    <FileView key={name} projectId={project.project_id} folder={experiment.folder} name={name} fileNames={viewable} onOpenFile={openFile} />
  );
  const label = TABS.find((item) => item.id === tab)!.label;

  return (
    <div className="flex flex-col gap-4">
      <div role="group" aria-label="Experiment tabs" className="flex flex-wrap gap-2">
        {TABS.map(({ id, label: text }) => (
          <Button key={id} variant="chip" size="sm" aria-pressed={tab === id} onClick={() => setTab(id)}>
            {text}
            {id === "checks" && experiment.findings.length > 0 ? ` (${experiment.findings.length})` : ""}
          </Button>
        ))}
      </div>
      <Panel title={tab === "report" && tabFiles.report === "results.md" ? "Report (results.md)" : label}>
        {tab === "protocol" || tab === "plan" || tab === "report" ? (
          tabFiles[tab] !== null ? (
            view(tabFiles[tab]!)
          ) : (
            <p className="text-ui text-muted-foreground">This experiment has no {tab} file.</p>
          )
        ) : null}
        {tab === "files" ? (
          <>
            <ul aria-label="Files" className="flex flex-col gap-2">
              {files.map((file) => (
                <li key={file.name}>
                  <CardInset className="flex-row flex-wrap items-center justify-between gap-2">
                    {file.viewable ? (
                      <Button variant="chip" size="sm" dir="ltr" aria-pressed={selected === file.name} onClick={() => setSelected(file.name)}>
                        <span className="min-w-0 truncate">{file.name}</span>
                      </Button>
                    ) : (
                      <span dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
                        {file.name}
                      </span>
                    )}
                    <span className="text-meta text-muted-foreground">
                      {formatSize(file.size)}
                      {file.viewable ? "" : ". Not opened in the app"}
                    </span>
                  </CardInset>
                </li>
              ))}
            </ul>
            <CardInset>
              <h3 className="text-ui font-medium">output/</h3>
              {output === null ? (
                <p className="text-meta text-muted-foreground">This experiment has no output folder.</p>
              ) : output.length === 0 ? (
                <p className="text-meta text-muted-foreground">The output folder is empty.</p>
              ) : (
                <ul aria-label="Output" dir="ltr" className="flex flex-col gap-1 font-mono text-code">
                  {output.map((name) => (
                    <li key={name} className="[overflow-wrap:anywhere]">
                      {name}
                    </li>
                  ))}
                </ul>
              )}
            </CardInset>
            {selected !== null && viewable.has(selected) ? (
              <section aria-label={`File ${selected}`} className="flex flex-col gap-2 border-t border-border pt-3">
                <h3 dir="ltr" className="font-mono text-code font-medium">
                  {selected}
                </h3>
                {view(selected)}
              </section>
            ) : null}
          </>
        ) : null}
        {tab === "checks" ? (
          experiment.findings.length === 0 ? (
            <p className="text-ui text-muted-foreground">The checker found no problem in this experiment.</p>
          ) : (
            <ul aria-label="Checks" className="flex flex-col gap-2">
              {experiment.findings.map((finding, index) => (
                <FindingLine key={`${finding.code}-${index}`} finding={finding} />
              ))}
            </ul>
          )
        ) : null}
      </Panel>
    </div>
  );
}
