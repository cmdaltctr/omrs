import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useApi } from "../api/ApiProvider";
import type { JsonValue } from "../api/pipelines";
import { documentReadingQuery } from "../api/queries";
import { PageRoutingPanel } from "../pageRouting/PageRoutingPanel";
import { PANEL_STEPS, TOP_KEYS, type PanelKey } from "../pageRouting/pageRoutingWords";
import { READING_ROWS } from "../settings/documentReadingWords";
import { CUTS_OPTION } from "./CutsParam";
import { replacedOptions } from "./ListParam";
import type { ParamFieldProps } from "./ParamField";
import { inheritLabel, READ_STEP_INTRO } from "./readStepWords";
import type { ParamField } from "./schema";

/** The Read document options the panel shows: its rows, the cuts and the old single-value options of its lists. */
const PANEL_FIELDS: ReadonlySet<string> = new Set([...TOP_KEYS, ...PANEL_STEPS.flatMap((step) => step.keys), CUTS_OPTION, ...PANEL_STEPS.flatMap((step) => step.keys).flatMap(replacedOptions)]);

/** True for an option that the Page routing panel shows, so the generic list of step options skips it. */
export function isPanelField(field: ParamField): boolean {
  return PANEL_FIELDS.has(field.name);
}

interface ReadStepRoutingProps {
  fields: readonly ParamField[];
  /** The step's own values. An option the step does not set inherits. */
  params: Record<string, JsonValue> | undefined;
  /** Renders the control of one option, with the draft wiring of the step. */
  renderField: (field: ParamField, extra?: Partial<ParamFieldProps>) => ReactNode;
}

/**
 * The Page routing panel of a Read document step (change page-routing-panel,
 * design D6). The panel lays the rows out. Each row is the step's own control
 * for the option, with an Inherit choice that names the Settings value and its
 * source, read from Settings > Document reading.
 */
export function ReadStepRouting({ fields, params, renderField }: ReadStepRoutingProps) {
  const reading = useQuery(documentReadingQuery(useApi())).data;
  const field = (name: string) => fields.find((candidate) => candidate.name === name);
  const setting = (key: string) => reading?.settings.find((row) => row.key === key);

  function renderRow(key: PanelKey) {
    const own = field(key);
    const words = READING_ROWS[key];
    if (own === undefined || words === undefined) return null;
    // An old single-value option shows beside its list only while the step still sets it.
    const old = replacedOptions(key)
      .map(field)
      .filter((option): option is ParamField => option !== undefined && params?.[option.name] != null);
    return (
      <>
        {renderField(own, { inheritLabel: inheritLabel(setting(key), words.kind), help: words.help })}
        {old.map((option) => renderField(option))}
      </>
    );
  }

  const cuts = field(CUTS_OPTION);
  const fallback = params?.ocr_fallback_enabled ?? setting("ocr_fallback_enabled")?.value;
  return <PageRoutingPanel description={READ_STEP_INTRO} renderRow={renderRow} renderCuts={() => (cuts === undefined ? null : renderField(cuts))} ocrFallbackEnabled={fallback !== false} />;
}
