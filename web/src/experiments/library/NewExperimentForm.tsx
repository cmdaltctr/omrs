import { FilePlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { CreatedExperiment, Project } from "../../api/experimentLibrary";
import { useCreateLibraryExperiment } from "../../api/experimentLibraryMutations";
import { Button } from "../../components/ui/button";
import { formatRoute } from "../../lib/routes";
import { SelectField, TextField } from "../fields";
import { Panel } from "../Panel";
import { CATEGORIES, indexOutcome, SIZES } from "./labels";
import { refusalLine } from "./refusal";

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const NUMBER = /^\d+(?:\.\d+)*$/;

interface NewExperimentFormProps {
  /** The projects whose folder is there. */
  projects: readonly Project[];
  /** The project chosen in the library, if any. */
  initialProject: string | null;
  onCancel: () => void;
}

/** Creates an experiment folder in one project, dated today, with the files its size needs. */
export function NewExperimentForm({ projects, initialProject, onCancel }: NewExperimentFormProps) {
  const create = useCreateLibraryExperiment();
  const [projectId, setProjectId] = useState(initialProject ?? projects[0]?.project_id ?? "");
  const project = projects.find((item) => item.project_id === projectId) ?? projects[0];
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<string>(CATEGORIES[0]);
  const [size, setSize] = useState<string>("Standard");
  const [followUp, setFollowUp] = useState("");
  const [problems, setProblems] = useState<{ slug?: string; title?: string; followUp?: string; form?: string }>({});
  const [created, setCreated] = useState<(CreatedExperiment & { projectId: string }) | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setCreated(null);
    const found = {
      ...(SLUG.test(slug.trim()) ? {} : { slug: "Use lower-case letters and digits joined by single hyphens, for example ocr-text-quality." }),
      ...(title.trim() === "" ? { title: "Enter a title." } : {}),
      ...(followUp.trim() === "" || NUMBER.test(followUp.trim()) ? {} : { followUp: "Enter an experiment number, for example 12." }),
    };
    setProblems(found);
    if (project === undefined || Object.keys(found).length > 0) return;
    try {
      const experiment = { slug: slug.trim(), title: title.trim(), category, size, follow_up: followUp };
      const done = await create.mutateAsync({ projectId: project.project_id, experiment });
      setCreated({ ...done, projectId: project.project_id });
      setSlug("");
      setTitle("");
      setFollowUp("");
    } catch (failure) {
      setProblems({ form: refusalLine(failure) });
    }
  }

  return (
    <Panel title="New experiment" description="Creates a folder named number, slug and today's date, with the files for its size. Its status starts as PLANNED.">
      <form aria-label="New experiment" onSubmit={(event) => void submit(event)} className="flex flex-col gap-3">
        {projects.length > 1 ? (
          <SelectField label="Project" value={project?.project_id ?? ""} onChange={setProjectId} options={projects.map((item) => ({ value: item.project_id, label: item.name }))} />
        ) : null}
        <div className="flex flex-wrap gap-3">
          <TextField label="Slug" dir="ltr" value={slug} placeholder="ocr-text-quality" error={problems.slug} onChange={setSlug} />
          <TextField label="Title" value={title} maxLength={200} error={problems.title} onChange={setTitle} />
        </div>
        <div className="flex flex-wrap gap-3">
          <SelectField label="Category" value={category} onChange={setCategory} options={CATEGORIES.map((value) => ({ value, label: value }))} />
          <SelectField label="Size" value={size} onChange={setSize} options={SIZES.map((value) => ({ value, label: value }))} />
          <TextField
            label="Follow-up of (optional)"
            inputMode="decimal"
            value={followUp}
            hint="The number of the experiment this one follows up."
            error={problems.followUp}
            onChange={setFollowUp}
          />
        </div>
        {problems.form ? (
          <p role="alert" className="text-meta text-status-error-label">
            {problems.form}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={create.isPending}>
            <FilePlus aria-hidden="true" />
            Create experiment
          </Button>
          <Button variant="outline" onClick={onCancel}>
            Close
          </Button>
        </div>
        {created !== null ? (
          <p role="status" className="text-meta text-muted-foreground">
            Created{" "}
            <a
              href={formatRoute({ area: "experiments", projectId: created.projectId, folder: created.folder })}
              className="font-mono text-code text-primary-label underline underline-offset-4 [overflow-wrap:anywhere]"
            >
              {created.folder}
            </a>
            . {created.message ?? indexOutcome(created.index)}
          </p>
        ) : null}
      </form>
    </Panel>
  );
}
