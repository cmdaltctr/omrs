import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import type { JsonValue } from "../api/pipelines";
import { documentReadingQuery } from "../api/queries";
import { CUT_WORDS } from "../settings/documentReadingWords";
import { LocalBackendCutInput } from "../settings/LocalBackendCutInput";
import type { ParamField } from "./schema";

/** The Read document option that holds the confidence cut of each local OCR backend. */
export const CUTS_OPTION = "ocr_local_cuts";

/** True for the cuts option of the Read document step. */
export function isCutsField(field: ParamField): boolean {
  return field.name === CUTS_OPTION;
}

/** The numbers of a map from backend name to cut. Anything else is no cut. */
function cutsOf(value: JsonValue | undefined): Record<string, number> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).filter((entry): entry is [string, number] => typeof entry[1] === "number"));
}

interface CutsParamProps {
  field: ParamField;
  value: JsonValue | undefined;
  /** The step's effective local OCR list: its own list, else the host list. */
  backends: string[];
  onChange: (value: JsonValue) => void;
  disabled?: boolean;
}

/**
 * The cuts of a Read document step: one input for each backend of the step's
 * effective list. An empty input inherits, and shows the host's cut or the
 * backend's default. A step entry replaces the host cut of its backend only.
 * No entry at all saves `null`. A box that holds a bad value drops its entry
 * from the draft, so a save never carries the last good prefix of the text.
 */
export function CutsParam({ field, value, backends, onChange, disabled = false }: CutsParamProps) {
  // The default cuts come with Settings > Document reading, as the backend names do.
  const reading = useQuery(documentReadingQuery(useApi())).data;
  const own = cutsOf(value);
  const host = cutsOf(field.inheritedValue);
  const placeholder = (name: string) => {
    const inherited = host[name];
    return inherited === undefined ? CUT_WORDS.defaultText(reading?.local_ocr_backends.find((option) => option.name === name)?.default_cut) : CUT_WORDS.hostText(inherited);
  };

  function set(name: string, cut: number | null) {
    if (cut === null && !(name in own)) return;
    const next = { ...own };
    if (cut === null) delete next[name];
    else next[name] = cut;
    onChange(Object.keys(next).length === 0 ? null : next);
  }

  return (
    <>
      {backends.length === 0 ? (
        <p className="text-meta text-muted-foreground">This step has no local OCR backend, so there is no cut to set.</p>
      ) : (
        <ul aria-label={field.label} className="flex min-w-0 flex-col gap-1.5">
          {backends.map((name) => (
            <li key={name} className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
              <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
                {name}
              </code>
              <LocalBackendCutInput backend={name} value={own[name] ?? null} placeholder={placeholder(name)} readOnly={disabled} onChange={(cut) => set(name, cut)} onInvalid={() => set(name, null)} />
            </li>
          ))}
        </ul>
      )}
      <p className="text-meta text-muted-foreground">{CUT_WORDS.stepHelp}</p>
    </>
  );
}
