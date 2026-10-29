import type { UseQueryResult } from "@tanstack/react-query";
import type { ProviderModels } from "../api/settings";
import { ErrorNotice } from "../components/ErrorNotice";
import { isListed, type ListWords } from "./modelDownloadWords";

interface ModelListLineProps {
  query: UseQueryResult<ProviderModels>;
  /** The provider's own sentences, such as `OLLAMA_LIST_WORDS`. */
  words: ListWords;
  value: string;
}

/** Tells whether the provider's model list holds the new model. Shows nothing before the first read. */
export function ModelListLine({ query, words, value }: ModelListLineProps) {
  if (query.isError) return <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />;
  if (query.isFetching) return <p role="status" className="text-meta text-muted-foreground">Reading the model list.</p>;
  const list = query.data;
  if (list === undefined) return null;
  if (!list.reachable) return <p role="status" className="text-ui">{words.noAnswer}</p>;
  return (
    <p role="status" className="text-ui">
      {isListed(list.models, value) ? `${words.holder} lists ${value}.` : words.notListed}
    </p>
  );
}
