import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { decisionModelsQuery, documentRoutersQuery } from "../api/routerMapsHooks";
import type { DocumentReadingState } from "../api/settingsDocumentReading";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { READING_ROWS, readingChoices, ROUTER_COST } from "./documentReadingWords";
import { DocumentRouterForm } from "./DocumentRouterForm";
import { DocumentRouterRow } from "./DocumentRouterRow";
import { ReadingSettingRow } from "./ReadingSettingRow";
import { BLANK_ROUTER, TEMPLATE, templateDraft } from "./routerWords";

/** What is open: the edit form or rename field of a router, a new router (blank or from the template), or nothing. */
type Open = { router: string; part: "edit" | "rename" } | { router: null; part: "blank" | "template" } | null;

interface DocumentRoutersCardProps {
  state: DocumentReadingState;
  /** Called with the state the server returned after the host choice is saved. */
  onSaved: (state: DocumentReadingState) => void;
}

/**
 * Settings › Document reading › Router (ADR-110): the host router choice and
 * the named routers of `omrs.jsonc`. A router asks a decision model, page by
 * page, whether the page text can stay; a "no" sends that page to OCR.
 */
export function DocumentRoutersCard({ state, onSaved }: DocumentRoutersCardProps) {
  const api = useApi();
  const routers = useQuery(documentRoutersQuery(api));
  const models = useQuery(decisionModelsQuery(api));
  const [open, setOpen] = useState<Open>(null);
  const host = state.settings.find((setting) => setting.key === "document_router");
  const words = READING_ROWS.document_router;
  const list = routers.data?.routers ?? [];
  const modelList = models.data?.models ?? [];

  return (
    <Card role="region" aria-labelledby="reading-router" className="@container">
      <CardHeader>
        <CardTitle id="reading-router">Router</CardTitle>
        <CardDescription>{ROUTER_COST}</CardDescription>
      </CardHeader>
      {host !== undefined && words !== undefined ? (
        <ReadingSettingRow setting={host} words={words} choices={readingChoices(words.kind, list.map((item) => item.name))} options={[]} notes={[]} onSaved={onSaved} />
      ) : null}
      {routers.isError ? <ErrorNotice error={routers.error} onRetry={() => void routers.refetch()} /> : null}
      {models.isError ? <ErrorNotice error={models.error} onRetry={() => void models.refetch()} /> : null}
      {routers.isPending ? (
        <p role="status" className="text-meta text-muted-foreground">
          Loading routers.
        </p>
      ) : null}
      {routers.data !== undefined ? (
        <>
          <div role="list" aria-label="Routers" className="flex min-w-0 flex-col">
            {list.map((item) => (
              <DocumentRouterRow
                key={item.name}
                item={item}
                models={modelList}
                open={open?.router === item.name ? open.part : null}
                onOpen={(part) => setOpen(part === null ? null : { router: item.name, part })}
              />
            ))}
          </div>
          {list.length === 0 ? <p className="text-meta text-muted-foreground">No router is set.</p> : null}
          {open?.router === null ? (
            <DocumentRouterForm
              key={open.part}
              initial={open.part === "template" ? templateDraft(modelList) : BLANK_ROUTER}
              models={modelList}
              creating
              fromTemplate={open.part === "template"}
              onClose={() => setOpen(null)}
            />
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setOpen({ router: null, part: "blank" })}>
                <Plus aria-hidden="true" />
                New router
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setOpen({ router: null, part: "template" })}>
                {`New from template: ${TEMPLATE.label}`}
              </Button>
            </div>
          )}
        </>
      ) : null}
    </Card>
  );
}
