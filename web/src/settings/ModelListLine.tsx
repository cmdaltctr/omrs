import type { UseQueryResult } from "@tanstack/react-query";
import type { ProviderModels } from "../api/settings";
import { ErrorNotice } from "../components/ErrorNotice";
import { isListed, NO_ANSWER_LINE, NOT_LISTED_LINE } from "./modelDownloadWords";

interface ModelListLineProps {
  query: UseQueryResult<ProviderModels>;
  /** The provider's name for itself, such as `Ollama` or `Your server`. */
  holder: string;
  value: string;
}

/** Tells whether the provider's model list holds the new model. Shows nothing before the first read. */
export function ModelListLine({ query, holder, value }: ModelListLineProps) {
  if (query.isError) return <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />;
  if (query.isFetching) return <p role="status" className="text-meta text-muted-foreground">Reading the model list.</p>;
  const list = query.data;
  if (list === undefined) return null;
  if (!list.reachable) return <p role="status" className="text-ui">{NO_ANSWER_LINE}</p>;
  return (
    <p role="status" className="text-ui">
      {isListed(list.models, value) ? `${holder} lists ${value}.` : NOT_LISTED_LINE}
    </p>
  );
}
