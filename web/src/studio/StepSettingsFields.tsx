import type { ReactNode } from "react";
import type { EffectiveControl, JsonValue, OperationDescriptor } from "../api/pipelines";
import { isCutsField } from "./CutsParam";
import { setEnabled, setParam, type Draft } from "./graph";
import { isHiddenOldOption, replacedOptions } from "./ListParam";
import { ParamField, type ParamFieldProps } from "./ParamField";
import { isPanelField, ReadStepRouting } from "./ReadStepRouting";
import { paramFields, type ParamField as Field } from "./schema";
import { controlFor, valueNote } from "./stepSummary";

interface StepSettingsFieldsProps {
  draft: Draft;
  nodeId: string;
  operation: OperationDescriptor;
  /** Effective control values from the latest check, keyed by node id. */
  controls: Record<string, EffectiveControl[]>;
  onChange: (change: (draft: Draft) => Draft) => void;
  readOnly?: boolean;
  /** Shown between the bypass switch and the parameters, for example the embedding model. */
  children?: ReactNode;
}

/** The operation whose OCR options show in the Page routing panel. */
const READ_OPERATION = "read.document";

const names = (value: JsonValue | undefined): string[] => (Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string") : []);

export function Check({ checked, onChange, disabled, children }: { checked: boolean; onChange: (checked: boolean) => void; disabled: boolean; children: string }) {
  return (
    <label className="flex items-center gap-2 text-ui">
      <input type="checkbox" checked={checked} disabled={disabled} className="size-4 accent-primary" onChange={(event) => onChange(event.target.checked)} />
      {children}
    </label>
  );
}

/**
 * The editable settings of one step: the bypass switch when the operation has
 * one, and one control for each parameter. Step settings and the card settings
 * panel both render it, so a control behaves the same in both places.
 */
export function StepSettingsFields({ draft, nodeId, operation, controls, onChange, readOnly = false, children }: StepSettingsFieldsProps) {
  const node = draft.graph.nodes.find((candidate) => candidate.id === nodeId);
  if (!node) return null;
  const fields = paramFields(operation);
  // The cuts option sets one cut for each backend of the list the step reads with.
  const own = node.params?.ocr_local_backends;
  const backends = names(own == null ? fields.find((field) => field.name === "ocr_local_backends")?.inheritedValue : own);
  const panel = operation.operation_id === READ_OPERATION;

  /** One control of the step, wired to the draft. A set list replaces its old options in the same update: a step may not set both forms. */
  const renderField = (field: Field, extra: Partial<ParamFieldProps> = {}) => (
    <ParamField
      key={`${nodeId}:${field.name}`}
      field={field}
      disabled={readOnly}
      backends={isCutsField(field) ? backends : undefined}
      value={node.params?.[field.name]}
      note={valueNote(field, node, controlFor(field, controls[nodeId]), draft.graph)}
      onChange={(value) =>
        onChange((current) => {
          const next = setParam(current, nodeId, field.name, value);
          if (value == null) return next;
          return replacedOptions(field.name).reduce((draft, old) => setParam(draft, nodeId, old, null), next);
        })
      }
      {...extra}
    />
  );
  return (
    <>
      {operation.bypass && (
        <>
          <Check disabled={readOnly} checked={node.enabled === false} onChange={(checked) => onChange((current) => setEnabled(current, nodeId, !checked))}>
            Bypass this step
          </Check>
          <p className="text-meta text-muted-foreground">
            A bypassed node passes its <code className="font-mono text-code">{operation.bypass.input_port}</code> input through unchanged.
          </p>
        </>
      )}
      {children}
      {fields.filter((field) => !(panel && isPanelField(field)) && !isHiddenOldOption(field, fields, node.params?.[field.name])).map((field) => renderField(field))}
      {panel ? <ReadStepRouting fields={fields} params={node.params} renderField={renderField} /> : null}
    </>
  );
}
