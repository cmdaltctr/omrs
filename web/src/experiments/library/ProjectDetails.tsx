import type { Finding, Project, Reserved } from "../../api/experimentLibrary";
import { useRemoveExperimentProject } from "../../api/experimentLibraryMutations";
import { Badge } from "../../components/ui/badge";
import { CardInset } from "../../components/ui/card";
import { ConfirmAction } from "../ConfirmAction";
import { SEVERITY_VARIANTS } from "./labels";

/**
 * A finding as one line: its severity as a badge, its code and the checker's
 * message. `showFolder` names the folder first, for a project-level finding
 * about a folder whose record did not load.
 */
export function FindingLine({ finding, showFolder = false }: { finding: Finding; showFolder?: boolean }) {
  return (
    <li className="flex flex-wrap items-baseline gap-2 text-ui">
      <Badge variant={SEVERITY_VARIANTS[finding.severity] ?? "neutral"}>{finding.severity}</Badge>
      <code dir="ltr" className="font-mono text-code text-muted-foreground">
        {finding.code}
      </code>
      <span className="min-w-0 break-words">
        {showFolder && finding.folder !== null ? (
          <>
            Folder{" "}
            <code dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
              {finding.folder}
            </code>
            :{" "}
          </>
        ) : null}
        {finding.message}
      </span>
    </li>
  );
}

interface ProjectDetailsProps {
  project: Project;
  /** Undefined while the listing loads or when the folder is unavailable. */
  reserved?: readonly Reserved[];
  findings?: readonly Finding[];
  onRemoved: () => void;
}

/** One project's folder, reserved numbers and project-level findings, with the action that removes it from the list. */
export function ProjectDetails({ project, reserved = [], findings = [], onRemoved }: ProjectDetailsProps) {
  const remove = useRemoveExperimentProject();
  return (
    <div className="flex flex-col gap-2">
      <CardInset>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="min-w-0 text-meta text-muted-foreground">
            Folder{" "}
            <code dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
              {project.root}
            </code>
          </p>
          <ConfirmAction
            label={`Remove project ${project.name}`}
            text="Remove project"
            warning="The project leaves the list and its notebook entries go. The files on disk are not touched."
            confirmLabel="Confirm remove"
            cancelLabel="Keep project"
            onConfirm={async () => {
              await remove.mutateAsync(project.project_id);
              onRemoved();
            }}
          />
        </div>
        {!project.available ? (
          <p className="flex flex-wrap items-center gap-2 text-ui">
            <Badge variant="warning">Unavailable</Badge>
            The folder is not there any more. Check the path, or remove the project.
          </p>
        ) : null}
      </CardInset>
      {reserved.length > 0 ? (
        <CardInset>
          <h3 className="text-ui font-medium">Reserved numbers</h3>
          <ul className="flex flex-col gap-1 text-ui">
            {reserved.map((item) => (
              <li key={item.number} className="break-words">
                <span className="font-mono text-code">{item.number}</span> {item.reason}
              </li>
            ))}
          </ul>
        </CardInset>
      ) : null}
      {findings.length > 0 ? (
        <CardInset>
          <h3 className="text-ui font-medium">Project checks</h3>
          <ul aria-label="Project checks" className="flex flex-col gap-1">
            {findings.map((finding, index) => (
              <FindingLine key={`${finding.code}-${index}`} finding={finding} showFolder />
            ))}
          </ul>
        </CardInset>
      ) : null}
    </div>
  );
}
