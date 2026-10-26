import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import type { Experiment } from "../../api/experimentLibrary";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "../../components/ui/card";
import { formatRoute } from "../../lib/routes";
import { findingCounts, plural, statusVariant } from "./labels";

/** The record status as a badge: the colour follows design D8, the text is the status. */
export function StatusBadge({ status }: { status: string }) {
  return <Badge variant={statusVariant(status)}>{status}</Badge>;
}

interface ExperimentCardProps {
  projectId: string;
  experiment: Experiment;
  /** Shown when the card can come from more than one project. */
  projectName?: string;
  /** Extra controls under the finding, such as Remove in a notebook. */
  actions?: ReactNode;
}

/** One experiment: status, category, number, title, date, finding and checker counts. The title and the Open button open its page. */
export function ExperimentCard({ projectId, experiment, projectName, actions }: ExperimentCardProps) {
  const { errors, warnings } = findingCounts(experiment.findings);
  const meta = [`Experiment ${experiment.number}`, experiment.date, projectName].filter(Boolean).join(" · ");
  const href = formatRoute({ area: "experiments", projectId, folder: experiment.folder });
  return (
    <Card role="group" aria-label={`Experiment ${experiment.folder}`} className="h-full">
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={experiment.status} />
          {experiment.category !== null ? <Badge variant="hue">{experiment.category}</Badge> : null}
        </div>
        <CardTitle className="break-words">
          <a
            href={href}
            className="text-foreground underline-offset-4 hover:underline"
          >
            {experiment.title}
          </a>
        </CardTitle>
        <CardDescription className="break-words">{meta}</CardDescription>
      </CardHeader>
      <p className="text-ui break-words">{experiment.finding}</p>
      {errors + warnings > 0 ? (
        <div className="flex flex-wrap gap-2" aria-label="Checker findings" role="group">
          {errors > 0 ? <Badge variant="error">{plural(errors, "error")}</Badge> : null}
          {warnings > 0 ? <Badge variant="warning">{plural(warnings, "warning")}</Badge> : null}
        </div>
      ) : null}
      <CardFooter className="mt-auto flex-wrap items-start">
        <Button asChild size="sm">
          <a href={href} aria-label={`Open ${experiment.title}`}>
            Open
            <ArrowRight aria-hidden="true" />
          </a>
        </Button>
        {actions}
      </CardFooter>
    </Card>
  );
}
