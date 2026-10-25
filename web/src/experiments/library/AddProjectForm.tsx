import { FolderPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { Project } from "../../api/experimentLibrary";
import { useAddExperimentProject } from "../../api/experimentLibraryMutations";
import { Button } from "../../components/ui/button";
import { TextField } from "../fields";
import { Panel } from "../Panel";
import { refusalLine } from "./refusal";

/** Adds a project: a folder on this machine that holds an `experiments/` directory. */
export function AddProjectForm({ onAdded, onCancel }: { onAdded: (project: Project) => void; onCancel: () => void }) {
  const add = useAddExperimentProject();
  const [path, setPath] = useState("");
  const [name, setName] = useState("");
  const [problems, setProblems] = useState<{ path?: string; name?: string }>({});

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = {
      ...(path.trim() === "" ? { path: "Enter the folder path." } : {}),
      ...(name.trim() === "" ? { name: "Enter a name." } : {}),
    };
    setProblems(found);
    if (Object.keys(found).length > 0) return;
    try {
      onAdded(await add.mutateAsync({ path: path.trim(), name: name.trim() }));
    } catch (failure) {
      setProblems({ path: refusalLine(failure) });
    }
  }

  return (
    <Panel title="Add a project" description="A project is a folder that holds an experiments directory. The app reads its files and changes nothing until you create an experiment.">
      <form aria-label="Add a project" onSubmit={(event) => void submit(event)} className="flex flex-col gap-3">
        <TextField
          label="Folder path"
          dir="ltr"
          value={path}
          placeholder="/work/project"
          hint="The full path of the folder that holds experiments/."
          error={problems.path}
          onChange={setPath}
        />
        <TextField label="Name" value={name} maxLength={80} error={problems.name} onChange={setName} />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={add.isPending}>
            <FolderPlus aria-hidden="true" />
            Add project
          </Button>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
    </Panel>
  );
}
