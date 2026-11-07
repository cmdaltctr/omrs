import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import type { JsonValue } from "../api/pipelines";
import { documentRoutersQuery } from "../api/routerMapsHooks";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { readingChoices } from "../settings/documentReadingWords";
import type { ParamField } from "./schema";

const INHERIT = "__inherit__";

/** True for the router option of the Read document step. */
export function isRouterField(field: ParamField): boolean {
  return field.name === "document_router";
}

interface RouterParamProps {
  value: JsonValue | undefined;
  onChange: (value: JsonValue) => void;
  disabled?: boolean;
  /** The words of the Inherit choice. Without it the choice reads "Inherit". */
  inheritLabel?: string;
}

/**
 * The router choice of a Read document step: Inherit, "No router" (saved as
 * `none`, so the step runs without the host router) and the routers that
 * Settings defines. A saved name that Settings no longer defines stays listed,
 * so the select does not go blank.
 */
export function RouterParam({ value, onChange, disabled = false, inheritLabel = "Inherit" }: RouterParamProps) {
  const routers = useQuery(documentRoutersQuery(useApi())).data?.routers ?? [];
  const choices = readingChoices("router", routers.map((router) => router.name));
  const current = value == null ? INHERIT : String(value);
  const known = current === INHERIT || choices.some((choice) => choice.value === current);
  return (
    <Select value={current} disabled={disabled} onValueChange={(next) => onChange(next === INHERIT ? null : next)}>
      <SelectTrigger aria-label="Router value">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={INHERIT}>{inheritLabel}</SelectItem>
        {choices.map((choice) => (
          <SelectItem key={choice.value} value={choice.value}>
            {choice.label}
          </SelectItem>
        ))}
        {known ? null : <SelectItem value={current}>{`${current} (not found)`}</SelectItem>}
      </SelectContent>
    </Select>
  );
}
