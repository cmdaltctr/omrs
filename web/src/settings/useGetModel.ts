/**
 * "Get this model" for a router list entry. It reads the file list of the
 * entry's repository, takes the revision and the quantisation file set the
 * entry names, and starts the one download job. A refusal is one plain line
 * from the fixed table, never text from Hugging Face.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError } from "../api/client";
import { useApi } from "../api/ApiProvider";
import { modelFilesQuery } from "../api/modelDownloads";
import { reasonFromBody, REASON_SENTENCES } from "./modelDownloadWords";
import { useStartModelDownload } from "./useModelDownload";

/** Splits `org/name:QUANT`. Returns `null` for a model name without a quantisation tag. */
export function splitModel(model: string): { repo: string; label: string } | null {
  const at = model.lastIndexOf(":");
  return at < 1 || at === model.length - 1 ? null : { repo: model.slice(0, at), label: model.slice(at + 1) };
}

export function useGetModel() {
  const api = useApi();
  const queryClient = useQueryClient();
  const start = useStartModelDownload();
  const [problem, setProblem] = useState<string | null>(null);
  const [reading, setReading] = useState(false);

  async function get(model: string) {
    setProblem(null);
    const parts = splitModel(model);
    if (parts === null) return setProblem(REASON_SENTENCES["not-found"]);
    setReading(true);
    try {
      const files = await queryClient.fetchQuery(modelFilesQuery(api, "llamacpp", parts.repo));
      const label = files.entries.find((entry) => entry.label === parts.label);
      if (files.revision === null) return setProblem(REASON_SENTENCES.network);
      if (label === undefined) return setProblem(REASON_SENTENCES["not-found"]);
      await start.mutateAsync({ provider: "llamacpp", repo: parts.repo, revision: files.revision, label: parts.label });
    } catch (error) {
      const reason = error instanceof ApiError ? reasonFromBody(error.body) : null;
      setProblem(reason === null ? REASON_SENTENCES.failed : REASON_SENTENCES[reason]);
    } finally {
      setReading(false);
    }
  }

  return { get, pending: reading || start.isPending, problem };
}
