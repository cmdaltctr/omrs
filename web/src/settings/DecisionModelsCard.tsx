import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { modelRuntimesQuery } from "../api/modelRuntimesHooks";
import { decisionModelsQuery } from "../api/routerMapsHooks";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { DecisionModelForm } from "./DecisionModelForm";
import { DecisionModelRow } from "./DecisionModelRow";
import { BLANK_DRAFT } from "./decisionModelWords";
import { DenseSettingRows } from "./SettingBox";

/** The add form's key in the open state. No entry name starts with `+`. */
const NEW = "+new";

/**
 * Settings › Providers › Decision models (ADR-110): the models a document
 * router asks whether a page keeps its text. Saves go to `omrs.jsonc`.
 */
export function DecisionModelsCard() {
  const api = useApi();
  const query = useQuery(decisionModelsQuery(api));
  const list = query.data;
  const managed = list?.models.some((item) => item.server === "managed") === true;
  // Read only when a managed entry exists. A failed read shows no runtime line.
  const runtimes = useQuery({ ...modelRuntimesQuery(api), enabled: managed });
  // The row or form open for editing: a listed name, NEW, or none.
  const [open, setOpen] = useState<string | null>(null);

  return (
    <Card role="region" aria-labelledby="decision-models" className="@container">
      <CardHeader>
        <CardTitle id="decision-models">Decision models</CardTitle>
        <CardDescription>A decision model answers yes or no about a page. A document router uses one to decide which pages go to OCR. A key field holds a reference only, never the key.</CardDescription>
      </CardHeader>
      {list === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading decision models.
          </p>
        )
      ) : (
        <>
          <DenseSettingRows>
            <div role="list" aria-label="Decision models" className="flex min-w-0 flex-col">
              {list.models.map((item) => (
                <DecisionModelRow
                  key={item.name}
                  item={item}
                  kinds={list.kinds}
                  runtime={runtimes.data?.find((runtime) => runtime.id === `decision-${item.name}`)}
                  editing={open === item.name}
                  onEdit={(editing) => setOpen(editing ? item.name : null)}
                />
              ))}
            </div>
          </DenseSettingRows>
          {list.models.length === 0 ? <p className="text-meta text-muted-foreground">No decision model is set.</p> : null}
          {open === NEW ? (
            <DecisionModelForm initial={BLANK_DRAFT} kinds={list.kinds} creating keySaved={false} onClose={() => setOpen(null)} />
          ) : (
            <div>
              <Button type="button" variant="outline" size="sm" onClick={() => setOpen(NEW)}>
                <Plus aria-hidden="true" />
                Add decision model
              </Button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
