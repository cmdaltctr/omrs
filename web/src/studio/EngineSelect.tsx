import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import type { JsonValue } from "../api/pipelines";
import { integrationsQuery } from "../api/queries";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import type { ParamField } from "./schema";

const INHERIT = "__inherit__";
const ENGINE_FIELDS = new Set(["ocr_engine_primary", "ocr_engine_fallback"]);
/** The local tier sits in the OCR engines group but is not a worker engine a step can name. */
const LOCAL_TIER = "local OCR tier";

/** True for the two OCR engine settings of the Read document step. */
export function isEngineField(field: ParamField): boolean {
  return ENGINE_FIELDS.has(field.name);
}

interface EngineSelectProps {
  field: ParamField;
  value: JsonValue | undefined;
  onChange: (value: JsonValue) => void;
  disabled?: boolean;
}

/**
 * The engine choice of a Read document step: Inherit and every engine of the
 * Integrations OCR engines group, each marked ready or not. An engine that is
 * not provisioned cannot be chosen, because admission would refuse the step.
 */
export function EngineSelect({ field, value, onChange, disabled }: EngineSelectProps) {
  const query = useQuery(integrationsQuery(useApi()));
  const engines = (query.data?.runtime?.ocr_engines ?? []).filter((engine) => engine.name !== LOCAL_TIER);
  const current = value == null ? INHERIT : String(value);
  const known = engines.some((engine) => engine.name === current);
  return (
    <Select value={current} disabled={disabled} onValueChange={(next) => onChange(next === INHERIT ? null : next)}>
      <SelectTrigger aria-label={`${field.label} value`}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={INHERIT}>Inherit</SelectItem>
        {engines.map((engine) => (
          <SelectItem key={engine.name} value={engine.name} disabled={engine.status !== "ready"}>
            {`${engine.name} (${engine.status === "ready" ? "ready" : "not provisioned"})`}
          </SelectItem>
        ))}
        {current !== INHERIT && !known ? <SelectItem value={current}>{`${current} (not found)`}</SelectItem> : null}
      </SelectContent>
    </Select>
  );
}
