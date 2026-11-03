import { useQuery } from "@tanstack/react-query";
import { useId } from "react";
import { useApi } from "../api/ApiProvider";
import type { JsonValue } from "../api/pipelines";
import { integrationsQuery } from "../api/queries";
import { engineOptions, LIST_WORDS, readerListWarning, readerOptions, type ListKind } from "../settings/documentReadingWords";
import { OrderedListControl, type ListOption } from "../settings/OrderedListControl";
import type { ParamField } from "./schema";

/** The Read document lists, and the single-value options each one replaces. */
const LIST_KINDS: Record<string, ListKind> = { pdf_readers: "readers", ocr_engines: "engines" };
const SUPERSEDED: Record<string, string> = { pdf_reader: "pdf_readers", ocr_engine_primary: "ocr_engines", ocr_engine_fallback: "ocr_engines" };
/** The local tier sits in the OCR engines group but is not a worker engine a step can name. */
const LOCAL_TIER = "local OCR tier";

/** True for the two list options of the Read document step. */
export function isListField(field: ParamField): boolean {
  return field.kind === "stringList" && field.name in LIST_KINDS;
}

/**
 * True for a single-value option that a list option replaces, when the step does not set it.
 * The step then shows only the list. A saved graph that still sets the old option keeps its control,
 * because a step may not set both forms.
 */
export function isHiddenOldOption(field: ParamField, fields: readonly ParamField[], value: JsonValue | undefined): boolean {
  const list = SUPERSEDED[field.name];
  return list !== undefined && value == null && fields.some((other) => other.name === list);
}

interface ListParamProps {
  field: ParamField;
  value: JsonValue | undefined;
  onChange: (value: JsonValue) => void;
  disabled?: boolean;
}

const names = (value: JsonValue | undefined): string[] => (Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string") : []);

/**
 * A Read document list option: Inherit, or the step's own ordered list in the same control
 * as Settings. Setting a list starts from the host list, so the step begins as a copy of what it inherits.
 */
export function ListParam({ field, value, onChange, disabled = false }: ListParamProps) {
  const group = useId();
  const kind = LIST_KINDS[field.name]!;
  const words = LIST_WORDS[kind];
  const data = useQuery(integrationsQuery(useApi())).data;
  const options: ListOption[] =
    kind === "readers"
      ? readerOptions((data?.pdf_readers ?? []).map(({ name, installed }) => ({ name, available: installed, reason: null })))
      : engineOptions((data?.runtime?.ocr_engines ?? []).filter((engine) => engine.name !== LOCAL_TIER).map(({ name, status, reason }) => ({ name, available: status === "ready", reason })));
  const own = value == null ? null : names(value);
  const warning = kind === "readers" && own !== null ? readerListWarning(own) : null;

  function setOwn() {
    const host = names(field.inheritedValue);
    const start = host.length > 0 ? host : [options.find((option) => !option.disabled && option.note === null)?.value ?? ""].filter(Boolean);
    if (start.length > 0) onChange(start);
  }

  return (
    <>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <label className="flex items-center gap-2 text-ui">
          <input type="radio" name={group} checked={own === null} disabled={disabled} className="size-4 accent-primary" onChange={() => onChange(null)} />
          Inherit
        </label>
        <label className="flex items-center gap-2 text-ui">
          <input type="radio" name={group} checked={own !== null} disabled={disabled} className="size-4 accent-primary" onChange={setOwn} />
          Set list
        </label>
      </div>
      {own !== null ? (
        <OrderedListControl label={field.label} noun={words.noun} value={own} options={options} positionNote={words.position} disabled={disabled} onChange={onChange} />
      ) : null}
      {warning !== null ? <p className="text-meta text-muted-foreground">{warning}</p> : null}
    </>
  );
}
