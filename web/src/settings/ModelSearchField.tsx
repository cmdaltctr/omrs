import { useEffect, useId, useState } from "react";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import type { ModelSearchResult } from "../api/modelDownloads";
import { REASON_SENTENCES, SEARCH_HINT } from "./modelDownloadWords";
import { useModelSearch } from "./useModelDownload";

/** How long the text must stay unchanged before a search goes out. */
export const SEARCH_PAUSE_MS = 400;
/** Fewer characters than this send no search. */
export const MIN_QUERY_LENGTH = 2;

const COUNT = new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 1 });

function useDebounced<T>(value: T, delay: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return settled;
}

interface ModelSearchFieldProps {
  provider: string;
  /** The id of the result in use, marked in the list. */
  selectedId: string | null;
  onChoose: (result: ModelSearchResult) => void;
}

/** The search box and the list of results. A search goes out 400 ms after the typing stops, and only from 2 characters. */
export function ModelSearchField({ provider, selectedId, onChoose }: ModelSearchFieldProps) {
  const inputId = useId();
  const [text, setText] = useState("");
  const settled = useDebounced(text.trim(), SEARCH_PAUSE_MS);
  const query = useModelSearch(provider, settled.length >= MIN_QUERY_LENGTH ? settled : null);
  const reply = query.data;

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={inputId}>Search for a model</Label>
      <Input id={inputId} dir="ltr" autoComplete="off" spellCheck={false} className="max-w-md" value={text} onChange={(event) => setText(event.target.value)} />
      {text.trim().length < MIN_QUERY_LENGTH ? <p className="text-meta text-muted-foreground">{SEARCH_HINT}</p> : null}
      {query.isError ? <ErrorNotice error={query.error} onRetry={() => void query.refetch()} /> : null}
      {reply?.reason === "network" ? <p role="status" className="text-ui">{REASON_SENTENCES.network}</p> : null}
      {reply !== undefined && reply.results.length === 0 && reply.reason === null ? (
        <p role="status" className="text-ui">
          No model matches that search.
        </p>
      ) : null}
      {reply !== undefined && reply.results.length > 0 ? (
        <ul aria-label="Search results" className="flex flex-col gap-1.5">
          {reply.results.map((result) => (
            <li key={result.id} className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                aria-pressed={result.id === selectedId}
                className="min-w-0 rounded-control border border-border px-2 py-1 text-start text-ui hover:border-border-hover aria-pressed:bg-selection"
                onClick={() => onChoose(result)}
              >
                <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
                  {result.id}
                </code>
              </button>
              {result.source === "ollama-library" ? <Badge>Ollama library</Badge> : null}
              {result.downloads !== null ? <span className="text-meta text-muted-foreground">{`${COUNT.format(result.downloads)} downloads`}</span> : null}
              {result.gated ? <Badge variant="warning">Gated</Badge> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
