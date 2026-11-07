import { useId, useState } from "react";
import type { LlamacppRouterStatus } from "../api/llamacppRouter";
import { useSaveRouterModel } from "../api/llamacppRouterHooks";
import type { ModelDownloadStatus } from "../api/modelDownloads";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { NEEDS_CREDENTIALS } from "./llamacppRouterWords";
import { useScopes } from "./useScopes";

const ADD = "__add__";

export const SAVED_LINE = "Saved to the router list. Choose it in Settings > Chat if it should answer.";

/** The id of a new entry: the model name in lower case, with every other run of characters turned into a hyphen. */
function newId(model: string, taken: Set<string>): string {
  const base = model.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40).replace(/^-+|-+$/g, "");
  let id = base;
  for (let n = 2; taken.has(id); n += 1) id = `${base.slice(0, 40 - String(n).length - 1)}-${n}`;
  return id;
}

/**
 * Use this model, while OMRS runs the router. It adds the downloaded file as a
 * new list entry, or replaces the file of the entry the user picks (or of
 * `target`, for the "Get this model" action of one entry). It records the
 * file's SHA-256, keeps the preset of a replaced entry and sets no role
 * setting. The route needs the `credentials` scope, so a session without it
 * sees the refusal and no request goes out.
 */
export function LlamacppUseModel({ status, router, target }: { status: ModelDownloadStatus; router: LlamacppRouterStatus; target?: string }) {
  const id = useId();
  const save = useSaveRouterModel();
  const scopes = useScopes();
  const [choice, setChoice] = useState(target ?? ADD);
  const { file_path: file, sha256, model_value: model } = status;
  if (file === null || sha256 === null || model === null) return null;
  const hasCredentials = scopes.has("credentials");
  const entryId = choice === ADD ? newId(model, new Set(router.models.map((entry) => entry.id))) : choice;

  return (
    <div className="flex flex-col gap-2">
      {target === undefined ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={id}>Where to put this model</Label>
          <Select value={choice} onValueChange={setChoice}>
            <SelectTrigger id={id} className="max-w-md">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ADD}>Add as a new model</SelectItem>
              {router.models.map((entry) => (
                <SelectItem key={entry.id} value={entry.id}>
                  {`Replace ${entry.id} (${entry.model})`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" disabled={!hasCredentials || save.isPending} onClick={() => save.mutate({ id: entryId, change: { model, file, sha256 } })}>
          Use this model
        </Button>
        {scopes.known && !hasCredentials ? <p className="text-meta text-muted-foreground">{NEEDS_CREDENTIALS}</p> : null}
      </div>
      {save.isError ? <ErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
      {save.isSuccess ? (
        <p role="status" className="text-ui">
          {SAVED_LINE}
        </p>
      ) : null}
    </div>
  );
}
