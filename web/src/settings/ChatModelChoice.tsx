import { useId, useState } from "react";
import type { ChatSettings } from "../api/settings";
import { useLlamacppRouter } from "../api/llamacppRouterHooks";
import { useSetChatSettings } from "../api/settingsMutations";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { SaveErrorNotice } from "./SaveErrorNotice";
import { MODEL_STATE_NAMES } from "./llamacppRouterWords";
import { RouterGetModel } from "./RouterGetModel";

/** True when Chat runs on llama.cpp and no Chat model is chosen yet. */
export function needsChatModel(settings: ChatSettings): boolean {
  return settings.provider === "llamacpp" && (settings.model ?? "") === "";
}

/**
 * "Choose a Chat model": a picker of the router list entries that can answer
 * (an embedding entry cannot), Get this model for an entry that has no file,
 * and a button that saves the pick as `answer.model`. It never picks the
 * classification model for the user.
 */
export function ChatModelChoice({ settings }: { settings: ChatSettings }) {
  const id = useId();
  const router = useLlamacppRouter().data;
  const save = useSetChatSettings();
  const [picked, setPicked] = useState("");
  if (router === undefined) return null;
  const entries = router.models.filter((entry) => entry.preset.embeddings !== true);
  const entry = entries.find((candidate) => candidate.model === picked);
  const locked = settings.locked;

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <h4 className="text-ui font-semibold">Choose a Chat model</h4>
      <p className="text-meta text-muted-foreground">Chat uses llama.cpp, and no Chat model is chosen yet. Pick one of the models on the router.</p>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={id}>Chat model to use</Label>
        <Select value={picked} onValueChange={setPicked} disabled={locked}>
          <SelectTrigger id={id} className="max-w-md">
            <SelectValue placeholder="Choose a model" />
          </SelectTrigger>
          <SelectContent>
            {entries.map((candidate) => (
              <SelectItem key={candidate.id} value={candidate.model}>
                {candidate.file === null ? `${candidate.model} (${MODEL_STATE_NAMES["not-downloaded"]})` : candidate.model}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {locked ? <p className="text-meta text-muted-foreground">{settings.lock_reason ?? "Read-only here."}</p> : null}
      </div>
      {entry !== undefined ? <RouterGetModel entry={entry} router={router} /> : null}
      <div>
        <Button type="button" size="sm" disabled={locked || entry === undefined || save.isPending} onClick={() => save.mutate({ provider: "llamacpp", model: picked })}>
          Use as Chat model
        </Button>
      </div>
      {save.isError ? <SaveErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
    </div>
  );
}
