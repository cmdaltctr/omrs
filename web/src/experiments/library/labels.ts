/** Badge colours, counts, filters and wording for the experiment library. Copy is British English. */
import type { Experiment, Finding, IndexOutcome } from "../../api/experimentLibrary";

/** The seven record statuses, in the order the status filter lists them. */
export const STATUSES = ["PLANNED", "ACTIVE", "PASS", "FAIL", "INCONCLUSIVE", "MEASURED", "SUPERSEDED"] as const;

export const CATEGORIES = ["retrieval", "ingestion", "runtime", "generation", "graph", "review"] as const;

export const SIZES = ["Quick", "Standard", "Confirmatory"] as const;

export type StatusVariant = "success" | "error" | "warning" | "info" | "neutral";

const STATUS_VARIANTS: Record<string, StatusVariant> = {
  PASS: "success",
  FAIL: "error",
  INCONCLUSIVE: "warning",
  ACTIVE: "warning",
  PLANNED: "info",
  MEASURED: "info",
  SUPERSEDED: "neutral",
};

/** Design D8. An unknown status is neutral, so nothing reads as a pass by mistake. */
export function statusVariant(status: string): StatusVariant {
  return STATUS_VARIANTS[status] ?? "neutral";
}

export const SEVERITY_VARIANTS: Record<Finding["severity"], StatusVariant> = { error: "error", warning: "warning", info: "info" };

export interface FindingCounts {
  errors: number;
  warnings: number;
}

export function findingCounts(findings: readonly Finding[]): FindingCounts {
  return {
    errors: findings.filter((finding) => finding.severity === "error").length,
    warnings: findings.filter((finding) => finding.severity === "warning").length,
  };
}

export function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

export interface LibraryFilters {
  /** A project id, or `ALL_PROJECTS`. */
  project: string;
  /** A status, or `ANY`. */
  status: string;
  /** A category, or `ANY`. */
  category: string;
  search: string;
}

export const ALL_PROJECTS = "*";
export const ANY = "*";
export const NO_FILTERS: LibraryFilters = { project: ALL_PROJECTS, status: ANY, category: ANY, search: "" };

/** Status and category must match exactly. The search looks in the number, title and finding, ignoring case. */
export function matches(experiment: Experiment, filters: LibraryFilters): boolean {
  if (filters.status !== ANY && experiment.status !== filters.status) return false;
  if (filters.category !== ANY && experiment.category !== filters.category) return false;
  const needle = filters.search.trim().toLowerCase();
  if (needle === "") return true;
  return [experiment.number, experiment.title, experiment.finding].some((text) => text.toLowerCase().includes(needle));
}

const INDEX_OUTCOMES: Record<IndexOutcome, string> = {
  written: "The index in EXP_README.md is updated.",
  "no-markers": "EXP_README.md has no index markers, so the index is not changed.",
  "no-readme": "The project has no EXP_README.md, so no index is written.",
};

export function indexOutcome(index: IndexOutcome): string {
  return INDEX_OUTCOMES[index] ?? "";
}

/** A byte count for people: bytes, KiB or MiB. */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return plural(bytes, "byte");
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}
