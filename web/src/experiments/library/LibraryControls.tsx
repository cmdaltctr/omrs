import type { Project } from "../../api/experimentLibrary";
import { SelectField, TextField } from "../fields";
import { ALL_PROJECTS, ANY, CATEGORIES, STATUSES, type LibraryFilters } from "./labels";

interface LibraryControlsProps {
  projects: readonly Project[];
  filters: LibraryFilters;
  onChange: (filters: LibraryFilters) => void;
}

/** The project picker, the status and category filters and the text search. */
export function LibraryControls({ projects, filters, onChange }: LibraryControlsProps) {
  const set = (patch: Partial<LibraryFilters>) => onChange({ ...filters, ...patch });
  return (
    <div role="search" aria-label="Filter experiments" className="flex flex-wrap items-end gap-3">
      <SelectField
        label="Project"
        value={filters.project}
        onChange={(project) => set({ project })}
        options={[{ value: ALL_PROJECTS, label: "All projects" }, ...projects.map((item) => ({ value: item.project_id, label: item.name }))]}
      />
      <SelectField
        label="Status"
        value={filters.status}
        onChange={(status) => set({ status })}
        options={[{ value: ANY, label: "Any status" }, ...STATUSES.map((status) => ({ value: status, label: status }))]}
      />
      <SelectField
        label="Category"
        value={filters.category}
        onChange={(category) => set({ category })}
        options={[{ value: ANY, label: "Any category" }, ...CATEGORIES.map((category) => ({ value: category, label: category }))]}
      />
      <TextField label="Search" type="search" value={filters.search} placeholder="Number, title or finding" onChange={(search) => set({ search })} />
    </div>
  );
}
