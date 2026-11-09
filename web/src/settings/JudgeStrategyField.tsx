import type { JudgeSettings } from "../api/settings";
import { useSetJudgeStrategy } from "../api/settingsMutations";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { judgeLabel } from "../studio/labels";
import { SOURCE } from "./ChoiceRow";
import { SaveErrorNotice } from "./SaveErrorNotice";

const HELP = "How each cited claim is checked. A profile can pick its own judge type in Studio.";

/**
 * The claim-judge strategy (`answer.verify_judge`). The options are the server's
 * registered strategies; a change saves at once and keeps the provider and model.
 * A strategy that the environment sets shows read-only with the reason.
 */
export function JudgeStrategyField({ judge }: { judge: JudgeSettings }) {
  const save = useSetJudgeStrategy();
  if (judge.judge === undefined) return null;
  const current = judge.judge;
  const names = judge.judges ?? [current];
  if (judge.judge_locked) {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-ui">{`Judge type: ${judgeLabel(current)}`}</p>
        <p className={SOURCE}>{judge.judge_lock_reason ?? "Read-only here."}</p>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor="judge-strategy">Judge type</Label>
      <Select value={current} disabled={save.isPending} onValueChange={(next) => next !== current && save.mutate({ judge: next })}>
        <SelectTrigger id="judge-strategy" aria-label="Judge type">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(names.includes(current) ? names : [...names, current]).map((name) => (
            <SelectItem key={name} value={name}>
              {judgeLabel(name)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className={SOURCE}>{HELP}</p>
      {save.isError ? <SaveErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
    </div>
  );
}
