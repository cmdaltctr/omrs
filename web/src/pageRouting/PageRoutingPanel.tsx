import { Fragment, useId, type ReactNode } from "react";
import { Card, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { PAGE_ROUTING_WORDS, PANEL_STEPS, TOP_KEYS, type PanelKey } from "./pageRoutingWords";

const META = "text-meta text-muted-foreground";

export interface PageRoutingPanelProps {
  /** Renders the row of one setting key. Settings and Studio each pass their own renderer. */
  renderRow: (key: PanelKey) => ReactNode;
  /** Renders the cut boxes of the local OCR backends, under their list in step 4. */
  renderCuts: () => ReactNode;
  /** Extra content at the foot of a step (1 to 5), such as the Install control in step 1 or the workers folder line in step 5. */
  renderExtra?: (step: number) => ReactNode;
  /** The `ocr_fallback_enabled` value the renderer shows. When false, the panel says that steps 2 to 5 have no effect. */
  ocrFallbackEnabled: boolean;
  /** One line under the title, for a host that needs to say what its rows mean (Studio explains Inherit). */
  description?: string;
}

function rows(keys: readonly PanelKey[], renderRow: (key: PanelKey) => ReactNode) {
  return keys.map((key) => <Fragment key={key}>{renderRow(key)}</Fragment>);
}

/**
 * The Page routing card: the rows that describe the whole flow, then five
 * numbered steps in the order a page meets them (change page-routing-panel,
 * design D1 and D6). It lays rows out and renders no control itself.
 */
export function PageRoutingPanel({ renderRow, renderCuts, renderExtra, ocrFallbackEnabled, description }: PageRoutingPanelProps) {
  const id = useId();
  return (
    <Card role="region" aria-labelledby={`${id}-title`}>
      <CardHeader>
        <CardTitle id={`${id}-title`}>{PAGE_ROUTING_WORDS.title}</CardTitle>
        {description === undefined ? null : <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <div className="flex min-w-0 flex-col">{rows(TOP_KEYS, renderRow)}</div>
      {PANEL_STEPS.map((step, index) => {
        const number = index + 1;
        return (
          <Fragment key={step.title}>
            {number === 2 && !ocrFallbackEnabled ? (
              <p role="note" className="rounded-control border border-border bg-muted px-3 py-2 text-meta">
                {PAGE_ROUTING_WORDS.ocrOff}
              </p>
            ) : null}
            <div data-slot="page-routing-step" className="flex min-w-0 flex-col gap-1 border-t border-border pt-3">
              <h4 className="flex items-center gap-2 text-ui font-semibold">
                <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-small border border-border text-meta tabular-nums">{number}</span>{" "}
                {step.title}
              </h4>
              <p className={META}>{step.intro}</p>
              {number === 2 ? <p className={META}>{PAGE_ROUTING_WORDS.fixedOrder}</p> : null}
              <div className="flex min-w-0 flex-col">
                {rows(step.keys, renderRow)}
                {number === 4 ? renderCuts() : null}
                {renderExtra?.(number)}
              </div>
            </div>
          </Fragment>
        );
      })}
    </Card>
  );
}
