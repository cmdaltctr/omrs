import type { ModelRuntime, ModelRuntimeState } from "../api/modelRuntimes";
import type { DecisionKindOption, DecisionModelItem, DecisionModelTest } from "../api/routerMaps";
import { useDeleteDecisionModel, useTestDecisionModel } from "../api/routerMapsHooks";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { DecisionModelForm } from "./DecisionModelForm";
import { draftOf, hasKeyReference, KEY_STATE_WORDS, KIND_LABELS, NOT_TESTED, NOT_YET_TESTED, TEST_WORDS } from "./decisionModelWords";
import { SaveErrorNotice } from "./SaveErrorNotice";
import { SettingBox } from "./SettingBox";

const META = "text-meta text-muted-foreground";
const CODE = "text-code font-mono [overflow-wrap:anywhere]";

const RUNTIME_WORDS: Record<ModelRuntimeState, string> = { running: "Running", starting: "Starting", stopped: "Stopped", failed: "Failed" };

interface DecisionModelRowProps {
  item: DecisionModelItem;
  kinds: DecisionKindOption[];
  /** The managed runtime of this entry, when the runtime list holds it. */
  runtime: ModelRuntime | undefined;
  editing: boolean;
  onEdit: (editing: boolean) => void;
}

/** One line with a label and a value in code. */
function Line({ label, value }: { label: string; value: string }) {
  return (
    <p className={META}>
      {`${label}: `}
      <code dir="ltr" className={CODE}>
        {value}
      </code>
    </p>
  );
}

/** The result of the last Test: a badge, the reason when it failed, then the check lines the server sent. */
function TestResult({ result }: { result: DecisionModelTest }) {
  const ok = result.result === "ok";
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={ok ? "success" : "error"}>{ok ? "Working" : "Not working"}</Badge>
        {ok ? null : <span className="text-ui">{TEST_WORDS[result.result]}</span>}
      </div>
      {[result.quantisation, result.projector, result.build].flatMap((line) => (line === null ? [] : [<p key={line} className={META}>{line}</p>]))}
    </div>
  );
}

/** One decision model: badges, model, key state, files and runtime of a managed entry, routers that use it; Test, Edit and Remove. */
export function DecisionModelRow({ item, kinds, runtime, editing, onEdit }: DecisionModelRowProps) {
  const test = useTestDecisionModel();
  const remove = useDeleteDecisionModel();
  const managed = item.server === "managed";
  const titleId = `decision-model-${item.name}`;

  return (
    <SettingBox role="listitem" aria-labelledby={titleId}>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <p id={titleId} className="text-ui font-semibold [overflow-wrap:anywhere]">
          {item.name}
        </p>
        <Badge variant="hue">{KIND_LABELS[item.kind]}</Badge>
        <Badge variant={item.hosted ? "warning" : "success"}>{item.hosted ? "Hosted" : "Local"}</Badge>
        {item.images ? <Badge variant="info">Images</Badge> : null}
        {item.not_yet_tested ? <Badge variant="warning">{NOT_YET_TESTED}</Badge> : null}
        {test.data === undefined ? <Badge>{NOT_TESTED}</Badge> : null}
      </div>
      <Line label="Model" value={item.model} />
      <Line label="Address" value={item.address} />
      <p className={META}>{KEY_STATE_WORDS[item.key_state]}</p>
      {managed && item.model_file !== null ? <Line label="Model file" value={item.model_file} /> : null}
      {managed && item.projector_file !== null ? <Line label="Projector file" value={item.projector_file} /> : null}
      {runtime !== undefined ? (
        <p className="text-ui">
          {`Runtime: ${RUNTIME_WORDS[runtime.state]}`}
          {runtime.reason_text !== null ? <span className={META}>{` ${runtime.reason_text}`}</span> : null}
        </p>
      ) : null}
      {item.used_by.length > 0 ? <p className={META}>{`Used by router: ${item.used_by.join(", ")}`}</p> : null}
      <div role="status">{test.data !== undefined ? <TestResult result={test.data} /> : null}</div>
      {editing ? (
        <DecisionModelForm initial={draftOf(item)} kinds={kinds} creating={false} keySaved={hasKeyReference(item.key_state)} onClose={() => onEdit(false)} />
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" aria-label={`Test ${item.name}`} disabled={test.isPending} onClick={() => test.mutate(item.name)}>
            {test.isPending ? "Testing" : "Test"}
          </Button>
          <Button type="button" variant="outline" size="sm" aria-label={`Edit ${item.name}`} onClick={() => onEdit(true)}>
            Edit
          </Button>
          <Button type="button" variant="outline" size="sm" aria-label={`Remove ${item.name}`} disabled={remove.isPending} onClick={() => remove.mutate(item.name)}>
            Remove
          </Button>
        </div>
      )}
      {test.isError ? <ErrorNotice error={test.error} onRetry={() => test.mutate(item.name)} /> : null}
      {remove.isError ? <SaveErrorNotice error={remove.error} onRetry={() => remove.reset()} /> : null}
    </SettingBox>
  );
}
