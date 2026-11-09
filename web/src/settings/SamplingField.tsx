import { useId } from "react";
import type { ChatChoice, SamplingName, SamplingSetting } from "../api/settings";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { SOURCE } from "./ChoiceRow";

const SEED_MAX = 2147483647;
const TEMPERATURE_ERROR = "Temperature must be a number from 0 to 2.";
const SEED_ERROR = `Seed must be a whole number from 0 to ${SEED_MAX}.`;
const IGNORED: Record<SamplingName, string> = {
  temperature: "This provider ignores the temperature. Nothing is sent.",
  seed: "This provider ignores the seed. Nothing is sent.",
  allowed_hosts: "This provider ignores the host list. Only OpenRouter reads it.",
};

/** The saved sampling values, as the form edits them: text in the boxes, plus lock and ignored state. */
export interface SamplingState {
  temperature: string;
  seed: string;
  allowed_hosts: string;
  locked: SamplingName[];
  lockReason: string | null;
  ignored: SamplingName[];
}

/** The sampling state of a Chat or judge read. A server before the sampling change sends none of the fields. */
export function samplingState(settings: SamplingSetting): SamplingState {
  return {
    temperature: settings.temperature == null ? "" : String(settings.temperature),
    seed: settings.seed == null ? "" : String(settings.seed),
    allowed_hosts: settings.allowed_hosts ?? "",
    locked: settings.sampling_locked ?? [],
    lockReason: settings.sampling_lock_reason ?? null,
    ignored: settings.sampling_ignored ?? [],
  };
}

/** The typed values of the three boxes. */
export type SamplingValues = Pick<SamplingState, SamplingName>;

/** Why a typed value cannot be saved, by field. An empty box is fine: it removes the value. */
export function samplingErrors(values: SamplingValues): Partial<Record<SamplingName, string>> {
  const errors: Partial<Record<SamplingName, string>> = {};
  const temperature = values.temperature.trim();
  if (temperature !== "" && !(Number(temperature) >= 0 && Number(temperature) <= 2)) errors.temperature = TEMPERATURE_ERROR;
  const seed = values.seed.trim();
  if (seed !== "" && !(/^\d+$/.test(seed) && Number(seed) <= SEED_MAX)) errors.seed = SEED_ERROR;
  return errors;
}

/** The save fields that changed from the saved state. A locked value is left out: sending it gives 409. */
export function samplingChanges(values: SamplingValues, saved: SamplingState): Partial<ChatChoice> {
  const changes: Partial<ChatChoice> = {};
  const open = (name: SamplingName) => !saved.locked.includes(name) && values[name].trim() !== saved[name].trim();
  if (open("temperature")) changes.temperature = values.temperature.trim() === "" ? null : Number(values.temperature);
  if (open("seed")) changes.seed = values.seed.trim() === "" ? null : Number(values.seed);
  if (open("allowed_hosts")) changes.allowed_hosts = values.allowed_hosts.trim();
  return changes;
}

/** The saved values as read-only lines, with the lock reason when the environment sets one. */
export function SamplingLines({ settings }: { settings: SamplingSetting }) {
  const state = samplingState(settings);
  return (
    <div className="flex flex-col gap-1">
      <p className="text-ui">
        Temperature: <code dir="ltr" className="font-mono text-code">{state.temperature || "Library default"}</code>
      </p>
      <p className="text-ui">
        Seed: <code dir="ltr" className="font-mono text-code">{state.seed || "None sent"}</code>
      </p>
      <p className="text-ui">
        Allowed hosts: <code dir="ltr" className="font-mono text-code">{state.allowed_hosts || "Any host"}</code>
      </p>
      {state.locked.length > 0 ? <p className={SOURCE}>{state.lockReason ?? "Read-only here."}</p> : null}
    </div>
  );
}

interface SamplingFieldProps {
  values: SamplingValues;
  onChange: (values: SamplingValues) => void;
  state: SamplingState;
  /** True when the form still shows the saved provider, so the saved `ignored` list describes it. */
  sameProvider: boolean;
}

interface BoxProps {
  name: SamplingName;
  label: string;
  hint: string;
  props: SamplingFieldProps;
  error?: string;
  numeric?: { step: string; min: number; max: number };
}

function Box({ name, label, hint, props, error, numeric }: BoxProps) {
  const id = useId();
  const errorId = useId();
  const { values, onChange, state, sameProvider } = props;
  const locked = state.locked.includes(name);
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        dir="ltr"
        autoComplete="off"
        spellCheck={false}
        className="max-w-xs"
        readOnly={locked}
        aria-invalid={error !== undefined}
        aria-describedby={error !== undefined ? errorId : undefined}
        {...(numeric ? { type: "number", inputMode: name === "seed" ? "numeric" : "decimal", ...numeric } : {})}
        value={values[name]}
        onChange={(event) => onChange({ ...values, [name]: event.target.value })}
      />
      {error !== undefined ? (
        <p id={errorId} className="text-meta text-status-error-label">
          {error}
        </p>
      ) : (
        <p className={SOURCE}>{hint}</p>
      )}
      {sameProvider && state.ignored.includes(name) ? <p className={SOURCE}>{IGNORED[name]}</p> : null}
    </div>
  );
}

/** Temperature, Seed and Allowed hosts under the reasoning level. Empty boxes send nothing, so the request stays as it was. */
export function SamplingField(props: SamplingFieldProps) {
  const errors = samplingErrors(props.values);
  return (
    <div className="flex flex-col gap-3">
      <Box name="temperature" label="Temperature" hint="0 to 2. Empty keeps the library default (0.1 on OpenAI-style providers)." props={props} error={errors.temperature} numeric={{ step: "0.1", min: 0, max: 2 }} />
      <Box name="seed" label="Seed" hint="A whole number. Empty sends no seed." props={props} error={errors.seed} numeric={{ step: "1", min: 0, max: SEED_MAX }} />
      <Box name="allowed_hosts" label="Allowed hosts" hint="OpenRouter host slugs separated by commas, such as fireworks or deepinfra/fp8. Empty allows any host." props={props} />
      {props.state.locked.length > 0 ? <p className={SOURCE}>{props.state.lockReason ?? "Read-only here."}</p> : null}
    </div>
  );
}
